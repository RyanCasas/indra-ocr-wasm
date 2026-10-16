"""Asynchronous browser adaptation of Indra's document converter.

The algorithms follow the pinned Apache-2.0 upstream in vendor/indra/indra_ocr;
inference calls yield to the browser event loop instead of blocking a worker.
Synchronous helpers remain inherited from upstream.
"""
from __future__ import annotations

import time
from pathlib import Path
from indra_ocr.document import Converter, CHECK_DPI, readable, _render, assign_runs
from indra_ocr.pipeline import InputError, Page, is_pdf, read_images
from indra_ocr.textlayer import BROKEN_FONT_MAP, read_text_layer


class WebConverter(Converter):
    async def pdf_page(self, pdf_path: str, doc, index: int) -> Page:
        page = doc[index]
        t: dict = {}
        note = "mode=ocr"
        if self.mode != "ocr":
            t0 = time.perf_counter()
            s = CHECK_DPI / 72.0
            tl = read_text_layer(page, _render(page, s), s)
            t["text_ms"] = 1000 * (time.perf_counter() - t0)
            # A layer the recognizer cannot read beats OCR, unless its codes are junk.
            unreadable = tl.reason != BROKEN_FONT_MAP and not readable(
                self.ocr, tl.lines
            )
            if tl.lines and (tl.trusted or self.mode == "text" or unreadable):
                return (await self._text_page(page, tl, t))
            note = tl.reason
            # A layer with a broken font map still places its glyphs: when most
            # run upright, the page is upright (orient.onnx is not asked).
            st = tl.stats
            turn = not (
                tl.reason == BROKEN_FONT_MAP and st["rotated"] < 0.5 * st["chars"]
            )
        else:
            turn = True
        t0 = time.perf_counter()
        gray = _render(page, self.page_scale(page))
        t["render_ms"] = 1000 * (time.perf_counter() - t0)
        out = (await self.ocr(gray, turn))
        out.timings = {**t, **out.timings}
        out.timings["total_ms"] = sum(
            v for k, v in out.timings.items() if k != "total_ms"
        )
        out.note = f"{note}; {out.note}"
        return out

    async def _text_page(self, page, tl, t: dict) -> Page:
        k = self.page_scale(page)
        t0 = time.perf_counter()
        gray = _render(page, k)
        t["render_ms"] = 1000 * (time.perf_counter() - t0)
        t0 = time.perf_counter()
        boxes = (await self.ocr.detect(gray))
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
        source = "text"
        if empty and self.image_ocr and readable(self.ocr, tl.lines):
            t0 = time.perf_counter()
            for i, r in zip(empty, (await self.ocr.recognize(gray, boxes[empty]))):
                if r[0].strip():
                    rec[i] = r
                    source = "hybrid"
            t["rec_ms"] = 1000 * (time.perf_counter() - t0)
        if getattr(self.ocr, "math", None) is not None:
            t0 = time.perf_counter()
            (await self._read_math(gray, boxes, rec))
            t["math_ms"] = 1000 * (time.perf_counter() - t0)
        keep = [i for i, r in enumerate(rec) if r is not None]
        out = (await self.ocr.assemble(
            (gray.shape[1], gray.shape[0]),
            boxes[keep].reshape(-1, boxes.shape[1]),
            [rec[i] for i in keep],
            t,
            content_order=self.pdf_order,
        ))
        out.source = source
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
            and len(r[2][0]) > 2
        ]
        if not idx:
            return
        crops = crop_lines(gray, boxes[idx, :4], self.ocr.height, None)
        math = [i for i, f in zip(idx, (await self.ocr.math.flags(crops))) if f]
        if not math:
            return
        from indra_ocr.math import MATH_MIN_CONF

        for i, (text, conf) in zip(math, (await self.ocr.math.read(gray, boxes[math]))):
            # A reading without math, or not confident, leaves the layer's text.
            if "$" in text and conf >= MATH_MIN_CONF:
                first = min(tk[2] for tk in rec[i][2])
                xc = float(boxes[i, 0] + boxes[i, 2]) / 2
                rec[i] = (text, 1.0, [(text, xc, first)])

    async def convert(
        self, path: str | Path, max_pages: int = 0, password: str | None = None
    ):
        """Yield (page index, Page) for a PDF or an image file (the file's bytes
        decide which).  A page that fails yields an empty Page whose ``source``
        is "error" and whose ``note`` says why; a file that cannot be opened
        raises InputError."""
        path = Path(path)
        if not path.is_file():
            raise InputError(f"{path}: no such file")
        if not is_pdf(path):
            for i, gray in enumerate(read_images(path)[: max_pages or None]):
                yield i, (await self._safe(lambda: self.ocr(gray)))
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
                yield i, (await self._safe(lambda: self.pdf_page(str(path), doc, i)))
        finally:
            doc.close()

    @staticmethod
    async def _safe(read) -> Page:
        try:
            return (await read())
        except Exception as e:  # noqa: BLE001  (one bad page must not end the document)
            return Page(
                [],
                {"total_ms": 0.0},
                markdown="",
                source="error",
                note=f"{type(e).__name__}: {e}",
            )
