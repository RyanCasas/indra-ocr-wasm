"""Asynchronous browser adaptation of Indra document.

Algorithms follow the pinned upstream; inference calls yield to the browser
event loop. Synchronous helpers are inherited from the unmodified vendor copy.
"""

from __future__ import annotations
import time
from pathlib import Path
import numpy as np
from indra_ocr.pipeline import InputError, Page, is_pdf, read_images
from indra_ocr.textlayer import (
    BROKEN_FONT_MAP,
    page_turn,
    read_text_layer,
    vertical_layout,
)
from indra_ocr.document import (
    Converter,
    CHECK_DPI,
    AGREE_LINES,
    LATIN_CODES,
    NOT_THE_PAGE,
    latin_share,
    layer_agrees,
    readable,
    _covered,
    _render,
    assign_runs,
)


class WebConverter(Converter):
    async def pdf_page(self, pdf_path: str, doc, index: int) -> Page:
        page = doc[index]
        t: dict = {}
        note = "mode=ocr"
        if self.mode != "ocr":
            t0 = time.perf_counter()
            s = CHECK_DPI / 72.0
            check = _render(page, s)
            tl = read_text_layer(page, check, s)
            k = page_turn(tl.stats)
            rot = page.get_rotation()
            if k and (rot + 90 * k) % 360 == 0:
                page.set_rotation(0)
                upright = _render(page, s)
                tl = read_text_layer(page, upright, s)
                if tl.lines and (tl.trusted or self.mode == "text"):
                    tl.stats["turn"] = k
                    t["text_ms"] = 1000 * (time.perf_counter() - t0)
                    out = await self._text_page(page, tl, t, check=self.mode == "auto")
                    if out is not None:
                        return out
                page.set_rotation(rot)
                tl = read_text_layer(
                    page, np.ascontiguousarray(np.rot90(check, -k)), s, k
                )
            elif k:
                tl = read_text_layer(
                    page, np.ascontiguousarray(np.rot90(check, -k)), s, k
                )
            elif vertical_layout(tl.stats):
                tl = read_text_layer(
                    page, np.ascontiguousarray(np.rot90(check, 1)), s, 0, 3
                )
                tl.stats["vertical"] = True
            t["text_ms"] = 1000 * (time.perf_counter() - t0)
            unreadable = tl.reason != BROKEN_FONT_MAP and (
                not readable(self.ocr, tl.lines)
            )
            note = tl.reason
            if tl.lines and (tl.trusted or self.mode == "text" or unreadable):
                out = await self._text_page(
                    page,
                    tl,
                    t,
                    check=self.mode == "auto" and tl.trusted and (not unreadable),
                )
                if out is not None:
                    return out
                note = NOT_THE_PAGE
            st = tl.stats
            turn = not (
                tl.reason == BROKEN_FONT_MAP and st["rotated"] < 0.5 * st["chars"]
            )
        else:
            turn = True
        t0 = time.perf_counter()
        gray = _render(page, self.page_scale(page))
        t["render_ms"] = 1000 * (time.perf_counter() - t0)
        out = await self.ocr(gray, turn)
        out.timings = {**t, **out.timings}
        out.timings["total_ms"] = sum(
            (v for k, v in out.timings.items() if k != "total_ms")
        )
        out.note = f"{note}; {out.note}"
        return out

    async def _text_page(self, page, tl, t: dict, check: bool = False) -> Page | None:
        """The page from its text layer.  check: first compare the script of up to
        AGREE_LINES of the layer's lines with the script the line classifier sees
        in their images; when they do not match (layer_agrees), return None, so OCR
        reads the page."""
        k = self.page_scale(page)
        turn = tl.stats.get("turn", 0)
        frame = tl.stats.get("frame", turn)
        vertical = bool(tl.stats.get("vertical"))
        t0 = time.perf_counter()
        gray = _render(page, k)
        if frame:
            gray = np.ascontiguousarray(np.rot90(gray, -frame))
        t["render_ms"] = 1000 * (time.perf_counter() - t0)
        t0 = time.perf_counter()
        boxes = await self.ocr.detect(gray)
        t["det_ms"] = 1000 * (time.perf_counter() - t0)
        toks, lost = assign_runs(tl.lines, boxes[:, :4], k)
        rec: list = [None] * len(boxes)
        empty = []
        for i, tk in enumerate(toks):
            text = self.ocr._decode(tk) if tk else ""
            if text:
                rec[i] = (text, 1.0, tk)
            else:
                empty.append(i)
        if check:
            t0 = time.perf_counter()
            full = [
                i
                for i, r in enumerate(rec)
                if r and sum((c.isalpha() for c in r[0])) >= 4
            ]
            pick = full[:: max(1, len(full) // AGREE_LINES)][:AGREE_LINES]
            if pick:
                groups, sure = await self.ocr.box_groups(gray, boxes[pick])
                agree = [
                    not (latin_share(rec[i][0]) >= LATIN_CODES and g != "base" and s)
                    for i, g, s in zip(pick, groups, sure)
                ]
                t["check_ms"] = 1000 * (time.perf_counter() - t0)
                if not layer_agrees(agree):
                    return None
        source = "text"
        side = [r for r in tl.rotated if r.text.strip()]
        side_boxes = np.array([[v * k for v in r.bbox] for r in side], np.float32)
        if len(side) and empty:
            empty = [i for i in empty if not _covered(boxes[i, :4], side_boxes)]
        if empty and self.image_ocr and readable(self.ocr, tl.lines):
            t0 = time.perf_counter()
            for i, r in zip(
                empty, await self.ocr.recognize(gray, boxes[empty], vertical=vertical)
            ):
                if r[0].strip():
                    rec[i] = r
                    source = "hybrid"
            t["rec_ms"] = 1000 * (time.perf_counter() - t0)
        if getattr(self.ocr, "math", None) is not None:
            t0 = time.perf_counter()
            await self._read_math(gray, boxes, rec)
            t["math_ms"] = 1000 * (time.perf_counter() - t0)
        keep = [i for i, r in enumerate(rec) if r is not None]
        kept_boxes = boxes[keep].reshape(-1, boxes.shape[1])
        kept_rec = [rec[i] for i in keep]
        if len(side):
            extra = np.zeros((len(side), boxes.shape[1]), np.float32)
            extra[:, :4] = side_boxes
            if boxes.shape[1] > 4:
                extra[:, 4] = 1.0
            kept_boxes = np.concatenate([kept_boxes, extra])
            for r, b in zip(side, side_boxes):
                cx = float(b[0] + b[2]) / 2
                kept_rec.append((r.text, 1.0, [(c, cx, r.seq) for c in r.text]))
        out = await self.ocr.assemble(
            (gray.shape[1], gray.shape[0]), kept_boxes, kept_rec, t, vertical=vertical
        )
        out.source = source
        out.rotation = 90 * turn
        if vertical:
            W = gray.shape[0]

            def back(b):
                return [W - b[3], b[0], W - b[1], b[2]]

            for ln in out.lines:
                ln.box = back(ln.box)
            for b in out.blocks:
                b["bbox"] = back(b["bbox"])
            out.vertical = True
        out.note += f"; {lost} chars outside detected lines" if lost else ""
        return out

    async def _read_math(self, gray, boxes, rec: list) -> None:
        """Text-layer lines that hold math (the classifier, on their crops) are read
        by MathRec instead: the layer has the symbols but not the LaTeX.  The line
        keeps its place in the PDF content order (its first character's index)."""
        from indra_ocr.line_mask import crop_lines

        idx = [
            i
            for i, r in enumerate(rec)
            if r is not None
            and r[2]
            and isinstance(r[2][0][0], str)
            and (len(r[2][0]) > 2)
        ]
        if not idx:
            return
        crops = crop_lines(gray, boxes[idx, :4], self.ocr.height, None)
        math = [i for i, f in zip(idx, await self.ocr.math.flags(crops)) if f]
        if not math:
            return
        from indra_ocr.math import MATH_MIN_CONF

        for i, (text, conf) in zip(math, await self.ocr.math.read(gray, boxes[math])):
            if "$" in text and conf >= MATH_MIN_CONF:
                first = min((tk[2] for tk in rec[i][2]))
                xc = float(boxes[i, 0] + boxes[i, 2]) / 2
                rec[i] = (text, 1.0, [(text, xc, first)])

    async def convert(
        self, path: str | Path, max_pages: int = 0, password: str | None = None
    ):
        """Yield (page index, Page) for a PDF or an image file (the file's bytes
        decide which).  A page that fails yields an empty Page whose ``source``
        is "error" and whose ``note`` says why; a file that cannot be opened
        raises InputError.  max_pages: 0 reads every page; a negative value
        raises ValueError."""
        if max_pages < 0:
            raise ValueError(
                f"max_pages must be 0 (all pages) or more, not {max_pages}"
            )
        path = Path(path)
        if not path.is_file():
            raise InputError(f"{path}: no such file")
        if not is_pdf(path):
            for i, gray in enumerate(read_images(path)[: max_pages or None]):
                yield (i, await self._safe(lambda: self.ocr(gray)))
            return
        import pypdfium2 as pdfium

        try:
            doc = pdfium.PdfDocument(str(path), password=password)
        except pdfium.PdfiumError as e:
            locked = "password" in str(e).lower()
            raise InputError(
                f"{path}: password-protected PDF (pass password=, or --password)"
                if locked
                else f"{path}: cannot open the PDF ({e})"
            ) from e
        try:
            n = len(doc) if not max_pages else min(len(doc), max_pages)
            for i in range(n):
                yield (i, await self._safe(lambda: self.pdf_page(str(path), doc, i)))
        finally:
            doc.close()

    @staticmethod
    async def _safe(read) -> Page:
        try:
            return await read()
        except Exception as e:
            return Page(
                [],
                {"total_ms": 0.0},
                markdown="",
                source="error",
                note=f"{type(e).__name__}: {e}",
            )
