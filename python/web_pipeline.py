"""Asynchronous browser adaptation of Indra's OCR pipeline.

The algorithms follow the pinned Apache-2.0 upstream in vendor/indra/indra_ocr;
inference calls yield to the browser event loop instead of blocking a worker.
Synchronous helpers remain inherited from upstream.
"""
from __future__ import annotations

import time
import numpy as np
from indra_ocr.pipeline import (
    OrtOCR, Page, Line, ADAPTIVE_MIN_H, ADAPTIVE_MAX_SIDE, ADAPTIVE_TARGET_H,
    MIN_CONF, ORIENT_MIN, DESKEW_MIN, SPLIT_GAP, CELL_GAP,
    orient_input, estimate_skew, rotate_page, unrotate_box,
)
from indra_ocr.det_post import decode, page_to_input
from indra_ocr.layout_post import page_blocks, page_markdown
from indra_ocr.line_mask import crop_lines
from indra_ocr.math import MATH_MIN_CONF
from indra_ocr.order_post import BLOCK_CLASSES, decode_blocks_order, decode_order, line_features, order_xycut
from indra_ocr.rec_preproc import PAD_X, pad_batch, width_batches
from indra_ocr.textlayer import pdf_order_coherent
from web_math import WebMathReader


class WebOCR(OrtOCR):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.math is not None:
            self.math = WebMathReader(self.math)

    async def _detect_at(self, gray: np.ndarray, long_side: int):
        x, s = page_to_input(gray, long_side)
        return decode((await self.det.run(None, {"x": x[None, None]}))[0][0]), s

    async def detect(self, gray: np.ndarray) -> np.ndarray:
        boxes, s = (await self._detect_at(gray, self.long_side))
        if self.adaptive and len(boxes) >= 8:
            med_h = float(np.median(boxes[:, 3] - boxes[:, 1]))
            if med_h < ADAPTIVE_MIN_H:
                ls = (
                    int(
                        min(
                            ADAPTIVE_MAX_SIDE,
                            self.long_side * ADAPTIVE_TARGET_H / max(med_h, 1.0),
                        )
                    )
                    // 32
                    * 32
                )
                if ls > self.long_side:
                    boxes, s = (await self._detect_at(gray, ls))
        if len(boxes):
            boxes[:, :4] /= s
            h, w = gray.shape
            boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
            boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
        return boxes

    async def recognize(
        self, gray: np.ndarray, boxes: np.ndarray, batch: int = 64
    ) -> list[tuple[str, float, list]]:
        """(text, confidence, tokens) per line; tokens = [(token id, page x)],
        x from the CTC peak's timestep mapped back through the crop.  A line
        under MIN_CONF comes back empty."""
        # CenterMask first when the model folder has mask.onnx (same step as training)
        crops = crop_lines(gray, boxes[:, :4], self.height, self.mask)
        out: list = [("", 0.0, [])] * len(crops)
        groups = [(self.rec, self.vocab, list(range(len(crops))), False)]
        if self.script is not None and crops:
            hanzi = (await self.hanzi_lines(crops, batch))
            groups = [
                (
                    self.rec,
                    self.vocab,
                    [j for j, h in enumerate(hanzi) if not h],
                    False,
                ),
                (
                    self.rec_cjk,
                    self.vocab_cjk,
                    [j for j, h in enumerate(hanzi) if h],
                    True,
                ),
            ]
        for sess, vocab, sel, as_chars in groups:
            for part in width_batches([crops[j].shape[1] for j in sel], batch):
                idx = [sel[i] for i in part]
                arr, widths = pad_batch([crops[j] for j in idx])
                best, pmax, lengths = (await sess.run(None, {"x": arr, "widths": widths}))
                stride = arr.shape[-1] / max(best.shape[1], 1)
                for k, j in enumerate(idx):
                    n = int(lengths[k])
                    seq, pm = best[k, :n], pmax[k, :n]
                    keep = (seq != 0) & np.concatenate([[True], seq[1:] != seq[:-1]])
                    x0, y0, x1, y1 = (float(v) for v in boxes[j, :4])
                    h = max(1.0, y1 - y0)
                    ix0 = np.floor(x0 - PAD_X * h)
                    cw = np.ceil(x1 + PAD_X * h) - ix0
                    f = cw / crops[j].shape[1]
                    t = np.nonzero(keep)[0]
                    xs = (ix0 + (t + 0.5) * stride * f).tolist()
                    ids = seq[t].tolist()
                    # The CJK recognizer's ids mean nothing in self.vocab: its tokens
                    # are characters, like the text-layer tokens.
                    toks = (
                        list(zip([vocab.chars[i - 1] for i in ids], xs))
                        if as_chars
                        else list(zip(ids, xs))
                    )
                    conf = float(pm[keep].mean()) if keep.any() else 0.0
                    out[j] = (
                        (vocab.decode(seq[keep].tolist()), conf, toks)
                        if conf >= MIN_CONF
                        else ("", conf, [])
                    )
        if getattr(self, "math", None) is not None and crops:
            math = [j for j, f in enumerate((await self.math.flags(crops))) if f]
            if math:
                for j, (text, conf) in zip(math, (await self.math.read(gray, boxes[math]))):
                    # Only a confident reading with math replaces the line (one
                    # token holds the whole line: it is never split).
                    if "$" in text and conf >= MATH_MIN_CONF:
                        xc = float(boxes[j, 0] + boxes[j, 2]) / 2
                        out[j] = (text, 1.0, [(text, xc)])
        return out

    async def hanzi_lines(self, crops: list, batch: int = 64) -> list[bool]:
        """Per line crop: does it hold Chinese characters (script.onnx)?"""
        out = [False] * len(crops)
        for idx in width_batches([c.shape[1] for c in crops], batch):
            arr, widths = pad_batch([crops[j] for j in idx])
            p = (await self.script.run(None, {"x": arr, "widths": widths}))[0]
            for k, j in enumerate(idx):
                out[j] = bool(p[k] > 0.5)
        return out

    async def reading_order(
        self, boxes: np.ndarray, texts: list[str], wh: tuple[int, int]
    ) -> tuple[list[int], tuple | None, np.ndarray | None]:
        """Reading order, (cls logits, same-block logits, table logits) when the
        order model has layout heads, and the pairwise order logits."""
        if len(boxes) < 2 or self.order is None:
            order = order_xycut(boxes[:, :4]) if len(boxes) else []
            return order, None, None
        f = line_features(boxes[:, :4], wh, texts)[None]
        outs = (await self.order.run(
            None, {"feats": f, "mask": np.ones((1, len(boxes)), bool)}
        ))
        if len(outs) >= 3:
            # Layout heads: blocks from the same-block head, lines inside a block by
            # geometry, blocks by the order head (exact page order 0.68 -> 0.81 on eval).
            cls, same = outs[1][0], outs[2][0]
            # same row / column / cell logits, when asked for
            tab = outs[3][0] if len(outs) > 3 and self.table_heads else None
            order = decode_blocks_order(outs[0][0], same, boxes[:, :4], cls)
            return order, (cls, same, tab), outs[0][0]
        return decode_order(outs[0][0]), None, outs[0][0]

    async def orientation(self, gray: np.ndarray) -> int:
        """Quarter turns (counter-clockwise) the page content is turned by, from
        orient.onnx: 0 without the model or when no turn is more likely than ORIENT_MIN."""
        if self.orient is None:
            return 0
        p = (await self.orient.run(None, {"x": orient_input(gray)[None, None]}))[0][0]
        k = int(p.argmax())
        return k if p[k] > ORIENT_MIN else 0

    async def upright(
        self, gray: np.ndarray, turn: bool = True
    ) -> tuple[np.ndarray, int, float]:
        """The page turned upright (orient.onnx) and straightened (estimate_skew):
        (page, quarter turns undone, degrees of skew undone)."""
        k = (await self.orientation(gray)) if turn else 0
        if k:
            gray = np.ascontiguousarray(np.rot90(gray, -k))
        a = estimate_skew(gray)
        if abs(a) >= DESKEW_MIN:
            gray = rotate_page(gray, a)
        else:
            a = 0.0
        return gray, k, a

    async def __call__(self, gray: np.ndarray, turn: bool = True) -> Page:
        """OCR of a page image.  turn=False: the page is known to be upright (no
        orient.onnx)."""
        t = {}
        t0 = time.perf_counter()
        gray, k, skew = (await self.upright(gray, turn))
        t["orient_ms"] = 1000 * (time.perf_counter() - t0)
        t0 = time.perf_counter()
        boxes = (await self.detect(gray))
        t["det_ms"] = 1000 * (time.perf_counter() - t0)
        t0 = time.perf_counter()
        rec = (await self.recognize(gray, boxes))
        t["rec_ms"] = 1000 * (time.perf_counter() - t0)
        page = (await self.assemble((gray.shape[1], gray.shape[0]), boxes, rec, t))
        page.rotation, page.skew = 90 * k, round(skew, 2)
        if skew:  # boxes back on the page as turned, before the deskew
            wh = (gray.shape[1], gray.shape[0])
            for ln in page.lines:
                ln.box = unrotate_box(ln.box, skew, wh)
            for b in page.blocks:
                b["bbox"] = unrotate_box(b["bbox"], skew, wh)
        return page

    async def assemble(
        self, wh, boxes: np.ndarray, rec: list, t: dict, content_order: bool = False
    ) -> Page:
        """Lines -> split at wide gaps -> reading order -> markdown.

        ``rec`` holds (text, confidence, tokens) per detected line.  With
        ``content_order`` and text-layer tokens (char, x, content index) on every
        line, the PDF content order is kept when it is coherent."""
        t0 = time.perf_counter()
        # Text-layer labels split a line at wide gaps; do the same (SPLIT_GAP).
        nb, nrec = [], []
        cuts = self.gutter_cuts(boxes, rec) if len(boxes) else []
        for b, (text, conf, toks), at in zip(boxes, rec, cuts):
            for bx, tx, tk in self.split_line(b, toks, SPLIT_GAP, at):
                nb.append(bx)
                nrec.append((tx, conf, tk))
        boxes = np.array(nb, np.float32).reshape(-1, 4)
        rec = nrec
        texts = [r[0] for r in rec]
        order, layout, logits = (await self.reading_order(boxes, texts, wh))
        if layout is not None and layout[2] is not None:
            # The table heads learned one line per cell, but the detector can join
            # cells: split table lines into cells, then run the order model again.
            table_cls = BLOCK_CLASSES.index("Table")
            is_table = layout[0].argmax(-1) == table_cls
            if is_table.any():
                nb, nrec = [], []
                for i, (b, r) in enumerate(zip(boxes, rec)):
                    parts = (
                        self.split_line(b, r[2], CELL_GAP)
                        if is_table[i]
                        else [(b, r[0], r[2])]
                    )
                    for bx, tx, tk in parts:
                        nb.append(bx)
                        nrec.append((tx, r[1], tk))
                if len(nb) != len(boxes):
                    boxes = np.array(nb, np.float32).reshape(-1, 4)
                    rec = nrec
                    texts = [r[0] for r in rec]
                    order, layout, logits = (await self.reading_order(boxes, texts, wh))
        note = "order=model"
        if content_order and len(boxes) > 1:
            keys = [
                min((tk[2] for tk in r[2] if len(tk) > 2), default=None) for r in rec
            ]
            if all(k is not None for k in keys):
                pdf = sorted(range(len(keys)), key=lambda i: keys[i])
                ok = pdf_order_coherent(
                    boxes[pdf, :4],
                    None if logits is None else logits[np.ix_(pdf, pdf)],
                )
                if ok:
                    order, note = pdf, "order=pdf"
        t["order_ms"] = 1000 * (time.perf_counter() - t0)
        t["total_ms"] = sum(v for k, v in t.items() if k != "total_ms")
        lines = [
            Line(
                [round(float(v), 1) for v in boxes[i, :4]],
                rec[i][0],
                round(rec[i][1], 4),
            )
            for i in order
        ]
        md, blocks = None, []
        if layout is not None:
            blocks = page_blocks(boxes[:, :4], texts, order, layout[0], layout[1])
            # Inside tables, labels split cells at smaller gaps (CELL_GAP).
            cells = {
                i: [
                    (bx, tx)
                    for bx, tx, _ in self.split_line(boxes[i], rec[i][2], CELL_GAP)
                ]
                for i in range(len(boxes))
            }
            md = page_markdown(
                boxes[:, :4],
                texts,
                order,
                layout[0],
                layout[1],
                keep_furniture=self.furniture,
                cells=cells,
                tab=layout[2],
            )
        elif len(boxes) < 2:
            md = "\n".join(texts)
        return Page(lines, t, md, note=note, blocks=blocks)
