"""Asynchronous browser adaptation of Indra pipeline.

Algorithms follow the pinned upstream; inference calls yield to the browser
event loop. Synchronous helpers are inherited from the unmodified vendor copy.
"""

from __future__ import annotations
import time
import numpy as np
from indra_ocr.det_post import decode, page_to_input
from indra_ocr.layout_post import page_blocks, page_markdown
from indra_ocr.line_mask import crop_lines, line_darkness
from indra_ocr.math import MATH_MIN_CONF
from indra_ocr.order_post import (
    BLOCK_CLASSES,
    GRID_LABELS,
    decode_blocks_order,
    decode_order,
    line_features,
    order_xycut,
    xycut_blocks,
)
from indra_ocr.rec_preproc import PAD_X, pad_batch, width_batches
from indra_ocr.rtl import is_rtl
from indra_ocr.pipeline import (
    OrtOCR,
    ADAPTIVE_MIN_H,
    ADAPTIVE_TARGET_H,
    SPLIT_GAP,
    CELL_GAP,
    ADAPTIVE_MAX_SIDE,
    ORIENT_MIN,
    VERTICAL,
    MIN_CONF,
    LM_BEAM,
    LM_CAND_FLOOR,
    OUT_GREEDY,
    OUT_LM,
    GROUPS,
    ROUTE_SURE,
    DESKEW_MIN,
    estimate_skew,
    preview,
    picture_boxes,
    rotate_page,
    unrotate_box,
    orient_input,
    Line,
    Page,
    tidy_lines,
)
from web_math import WebMathReader


class WebOCR(OrtOCR):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.math is not None:
            self.math = WebMathReader(self.math)

    async def _detect_at(self, gray: np.ndarray, long_side: int):
        x, s = page_to_input(gray, long_side)
        out = (await self.det.run(None, {"x": x[None, None]}))[0][0]
        self._pic = (out[3], s) if out.shape[0] > 3 else None
        return (decode(out), s)

    async def detect(self, gray: np.ndarray) -> np.ndarray:
        boxes, s = await self._detect_at(gray, self.long_side)
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
                    boxes, s = await self._detect_at(gray, ls)
        if len(boxes):
            boxes[:, :4] /= s
            h, w = gray.shape
            boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, w)
            boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, h)
        return boxes

    async def detect_all(self, gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Text-line boxes and picture boxes [P, 4] (pixels; none from a
        det.onnx without the picture channel)."""
        self._pic = None
        boxes = await self.detect(gray)
        pic = getattr(self, "_pic", None)
        if pic is None:
            return (boxes, np.zeros((0, 4), np.float32))
        return (boxes, picture_boxes(*pic, gray.shape))

    async def recognize(
        self,
        gray: np.ndarray,
        boxes: np.ndarray,
        batch: int = 64,
        vertical: bool = False,
    ) -> list[tuple[str, float, list]]:
        """(text, confidence, tokens) per line; tokens = [(token id, page x)],
        x from the CTC peak's timestep mapped back through the crop.  A line
        under MIN_CONF comes back empty.  vertical: the page is a vertical one
        turned a quarter turn (every line to the CJK recognizer)."""
        pool = getattr(self, "pool", None)
        window = getattr(self, "window", 1)
        dark = line_darkness(gray, boxes[:, :4], pool) if window > 1 else None
        crops = crop_lines(
            gray, boxes[:, :4], self.height, self.mask, pool=pool, dark=dark
        )
        tall = (
            crop_lines(
                gray, boxes[:, :4], self.height, window=window, pool=pool, dark=dark
            )
            if window > 1
            else crops
        )
        out: list = [("", 0.0, [])] * len(crops)
        groups = [(self.rec, self.vocab, list(range(len(crops))), False)]
        if vertical and "cjk" in self.groups:
            sess, vocab = self.groups["cjk"]
            groups = [(sess, vocab, list(range(len(crops))), True)]
        elif self.script is not None and crops:
            names, sure = await self.line_groups(crops, batch)
            groups = [
                (
                    self.rec,
                    self.vocab,
                    [j for j, g in enumerate(names) if g == "base" or not sure[j]],
                    False,
                )
            ] + [
                (sess, vocab, [j for j, g in enumerate(names) if g == name], True)
                for name, (sess, vocab) in self.groups.items()
            ]
        best_conf = [-1.0] * len(crops)
        for sess, vocab, sel, as_chars in groups:
            for part in width_batches([crops[j].shape[1] for j in sel], batch):
                idx = [sel[i] for i in part]
                src = tall if sess is self.rec else crops
                arr, widths = pad_batch([src[j] for j in idx])
                lm = getattr(self, "lms", {}).get(id(sess))
                use_lm = lm is not None
                res = await sess.run(
                    OUT_GREEDY + (OUT_LM if use_lm else []),
                    {"x": arr, "widths": widths},
                )
                best, pmax, lengths = res[:3]
                stride = arr.shape[-1] / max(best.shape[1], 1)
                for k, j in enumerate(idx):
                    n = int(lengths[k])
                    seq, pm = (best[k, :n], pmax[k, :n])
                    keep = (seq != 0) & np.concatenate([[True], seq[1:] != seq[:-1]])
                    x0, y0, x1, y1 = (float(v) for v in boxes[j, :4])
                    h = max(1.0, y1 - y0)
                    ix0 = np.floor(x0 - PAD_X * h)
                    cw = np.ceil(x1 + PAD_X * h) - ix0
                    f = cw / crops[j].shape[1]
                    t = np.nonzero(keep)[0]
                    ids = seq[t].tolist()
                    conf = float(pm[keep].mean()) if keep.any() else 0.0
                    if use_lm and MIN_CONF <= conf < lm[3]:
                        from indra_ocr.lm import beam_search

                        ids, steps = beam_search(
                            res[3][k, :n],
                            res[4][k, :n],
                            res[5][k, :n],
                            lm[0],
                            lm[1],
                            lm[2],
                            LM_BEAM,
                            cand_floor=LM_CAND_FLOOR,
                        )
                        t = np.array(steps, np.int64)
                    xs = (ix0 + (t + 0.5) * stride * f).tolist()
                    toks = (
                        list(zip([vocab.chars[i - 1] for i in ids], xs))
                        if as_chars
                        else list(zip(ids, xs))
                    )
                    if conf <= best_conf[j]:
                        continue
                    best_conf[j] = conf
                    out[j] = (
                        (vocab.decode(ids), conf, toks)
                        if conf >= MIN_CONF
                        else ("", conf, [])
                    )
        if getattr(self, "math", None) is not None and crops:
            math = [j for j, f in enumerate(await self.math.flags(crops)) if f]
            if math:
                for j, (text, conf) in zip(
                    math, await self.math.read(gray, boxes[math])
                ):
                    if "$" in text and conf >= MATH_MIN_CONF:
                        xc = float(boxes[j, 0] + boxes[j, 2]) / 2
                        out[j] = (text, 1.0, [(text, xc)])
        return out

    async def box_groups(
        self, gray: np.ndarray, boxes: np.ndarray
    ) -> tuple[list[str], list[bool]]:
        """line_groups for line boxes on the page (crops as recognize makes them);
        every line is "base" when the model folder has no script.onnx."""
        if self.script is None or not len(boxes):
            return (["base"] * len(boxes), [False] * len(boxes))
        pool = getattr(self, "pool", None)
        window = getattr(self, "window", 1)
        dark = line_darkness(gray, boxes[:, :4], pool) if window > 1 else None
        crops = crop_lines(
            gray, boxes[:, :4], self.height, self.mask, pool=pool, dark=dark
        )
        return await self.line_groups(crops)

    async def line_groups(
        self, crops: list, batch: int = 64
    ) -> tuple[list[str], list[bool]]:
        """Per line crop, the group whose recognizer reads it (script.onnx), and
        whether the classifier is sure of it (probability over ROUTE_SURE); a
        group without its recognizer goes to base."""
        out = ["base"] * len(crops)
        sure = [True] * len(crops)
        for idx in width_batches([c.shape[1] for c in crops], batch):
            arr, widths = pad_batch([crops[j] for j in idx])
            p = (await self.script.run(None, {"x": arr, "widths": widths}))[0]
            for k, j in enumerate(idx):
                g = (
                    ("cjk" if p[k] > 0.5 else "base")
                    if p.ndim == 1
                    else getattr(self, "script_groups", GROUPS)[int(p[k].argmax())]
                )
                pk = (
                    max(float(p[k]), 1.0 - float(p[k]))
                    if p.ndim == 1
                    else float(p[k].max())
                )
                out[j] = g if g in self.groups else "base"
                sure[j] = pk > ROUTE_SURE
        return (out, sure)

    async def reading_order(
        self, boxes: np.ndarray, texts: list[str], wh: tuple[int, int]
    ) -> tuple[list[int], tuple | None, np.ndarray | None]:
        """Reading order, (cls logits, same-block logits, table logits) when the
        order model has layout heads, and the pairwise order logits."""
        if len(boxes) < 2 or self.order is None:
            order = order_xycut(boxes[:, :4]) if len(boxes) else []
            return (order, None, None)
        f = line_features(boxes[:, :4], wh, texts)[None]
        outs = await self.order.run(
            None, {"feats": f, "mask": np.ones((1, len(boxes)), bool)}
        )
        if len(outs) >= 3:
            cls, same = (outs[1][0], outs[2][0])
            tab = outs[3][0] if len(outs) > 3 and self.table_heads else None
            order = decode_blocks_order(outs[0][0], same, boxes[:, :4], cls)
            return (order, (cls, same, tab), outs[0][0])
        return (decode_order(outs[0][0]), None, outs[0][0])

    async def orientation_probs(self, gray: np.ndarray) -> np.ndarray | None:
        """orient.onnx class probabilities for the page (None without the model)."""
        if self.orient is None:
            return None
        return (await self.orient.run(None, {"x": orient_input(gray)[None, None]}))[0][
            0
        ]

    async def orientation(self, gray: np.ndarray) -> int:
        """Quarter turns (counter-clockwise) the page content is turned by, from
        orient.onnx: 0 without the model or when no turn is more likely than
        ORIENT_MIN; VERTICAL for a page set in vertical columns."""
        p = await self.orientation_probs(gray)
        if p is None:
            return 0
        k = int(p.argmax())
        return k if p[k] > ORIENT_MIN else 0

    async def upright(
        self, gray: np.ndarray, turn: bool = True, k: int | None = None
    ) -> tuple[np.ndarray, int, float]:
        """The page turned upright (``k`` quarter turns, or orient.onnx's choice)
        and straightened (estimate_skew): (page, quarter turns undone, degrees of
        skew undone)."""
        a = estimate_skew(gray, pool=getattr(self, "pool", None))
        if k is None:
            k = (
                await self.orientation(
                    rotate_page(gray, a) if abs(a) >= DESKEW_MIN else gray
                )
                if turn
                else 0
            )
        return self._turn(gray, k, a)

    async def __call__(self, gray: np.ndarray, turn: bool = True) -> Page:
        """OCR of a page image.  turn=False: the page is known to be upright (no
        orient.onnx)."""
        t0 = time.perf_counter()
        small = preview(gray)
        a = estimate_skew(small, pool=getattr(self, "pool", None))
        k = (
            await self.orientation(
                rotate_page(small, a) if abs(a) >= DESKEW_MIN else small
            )
            if turn
            else 0
        )
        orient_ms = 1000 * (time.perf_counter() - t0)
        page = await self._read(gray, k, a, small)
        page.timings["orient_ms"] += orient_ms
        return page

    async def _read(
        self, gray: np.ndarray, k: int, a: float, small: np.ndarray | None = None
    ) -> Page:
        t = {}
        t0 = time.perf_counter()
        gray, k, skew = self._turn(gray, k, a, small)
        t["orient_ms"] = 1000 * (time.perf_counter() - t0)
        t0 = time.perf_counter()
        boxes, pictures = await self.detect_all(gray)
        t["det_ms"] = 1000 * (time.perf_counter() - t0)
        t0 = time.perf_counter()
        vertical = k == VERTICAL
        rec = await self.recognize(gray, boxes, vertical=vertical)
        t["rec_ms"] = 1000 * (time.perf_counter() - t0)
        page = await self.assemble(
            (gray.shape[1], gray.shape[0]),
            boxes,
            rec,
            t,
            vertical=vertical,
            pictures=None if vertical else pictures,
        )
        page.rotation, page.skew = (0 if vertical else 90 * k, round(skew, 2))
        page.vertical = vertical
        if skew:
            wh = (gray.shape[1], gray.shape[0])
            for ln in page.lines:
                ln.box = unrotate_box(ln.box, skew, wh)
            for b in page.blocks:
                b["bbox"] = unrotate_box(b["bbox"], skew, wh)
        if vertical:
            W = gray.shape[0]

            def back(b):
                return [W - b[3], b[0], W - b[1], b[2]]

            for ln in page.lines:
                ln.box = back(ln.box)
            for b in page.blocks:
                b["bbox"] = back(b["bbox"])
        return page

    async def assemble(
        self,
        wh,
        boxes: np.ndarray,
        rec: list,
        t: dict,
        vertical: bool = False,
        pictures: np.ndarray | None = None,
    ) -> Page:
        """Lines -> split at wide gaps -> reading order -> markdown.

        ``rec`` holds (text, confidence, tokens) per detected line.  ``vertical``:
        the page is a vertical page turned a quarter turn (see ``upright``)."""
        t0 = time.perf_counter()
        letters = [c for r in rec for c in r[0] if c.isalpha()]
        n_rtl = sum((is_rtl(c) for c in letters))
        self._page_rtl = n_rtl > len(letters) - n_rtl
        width = float(wh[0])

        def geo(b: np.ndarray) -> np.ndarray:
            if not self._page_rtl:
                return b
            m = np.array(b, np.float32).copy()
            m[..., 0], m[..., 2] = (width - b[..., 2], width - b[..., 0])
            return m

        nb, nrec = ([], [])
        cuts = self.gutter_cuts(boxes, rec) if len(boxes) else []
        for b, (text, conf, toks), at in zip(boxes, rec, cuts):
            for bx, tx, tk in self.split_line(b, toks, SPLIT_GAP, at):
                nb.append(bx)
                nrec.append((tx, conf, tk))
        boxes, rec = tidy_lines(
            np.array(nb, np.float32).reshape(-1, 4),
            nrec,
            self._page_rtl,
            self.vocab.index.get(" "),
        )
        texts = [r[0] for r in rec]
        order, layout, _ = await self.reading_order(geo(boxes), texts, wh)
        if vertical and layout is not None:
            blocks = xycut_blocks(boxes[:, :4])
            order = [i for b in blocks for i in b]
            same = np.full((len(boxes), len(boxes)), -1.0, np.float32)
            for b in blocks:
                same[np.ix_(b, b)] = 1.0
            cls = layout[0].copy()
            for c in GRID_LABELS:
                cls[:, BLOCK_CLASSES.index(c)] = -10000.0
            layout = (cls, same, None)
        elif layout is not None and layout[2] is not None:
            table_cls = BLOCK_CLASSES.index("Table")
            is_table = layout[0].argmax(-1) == table_cls
            if is_table.any():
                nb, nrec = ([], [])
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
                    order, layout, _ = await self.reading_order(geo(boxes), texts, wh)
        note = "order=xycut" if vertical else "order=model"
        t["order_ms"] = 1000 * (time.perf_counter() - t0)
        t["total_ms"] = sum((v for k, v in t.items() if k != "total_ms"))
        lines = [
            Line(
                [round(float(v), 1) for v in boxes[i, :4]],
                rec[i][0],
                round(rec[i][1], 4),
            )
            for i in order
        ]
        md, blocks = (None, [])
        if layout is not None:
            blocks = page_blocks(geo(boxes[:, :4]), texts, order, layout[0], layout[1])
            for b in blocks:
                b["bbox"] = [round(float(v), 1) for v in geo(np.array(b["bbox"]))]
            cells = {
                i: [
                    (list(geo(np.array(bx, np.float32))), tx)
                    for bx, tx, _ in self.split_line(boxes[i], rec[i][2], CELL_GAP)
                ]
                for i in range(len(boxes))
            }
            has_pics = pictures is not None and len(pictures)
            md = page_markdown(
                geo(boxes[:, :4]),
                texts,
                order,
                layout[0],
                layout[1],
                keep_furniture=self.furniture,
                cells=cells,
                tab=layout[2],
                pictures=geo(pictures) if has_pics else None,
            )
            if has_pics:
                for p in pictures:
                    cy = (p[1] + p[3]) / 2
                    at = next(
                        (
                            j
                            for j, b in enumerate(blocks)
                            if (b["bbox"][1] + b["bbox"][3]) / 2 > cy
                            and min(p[2], b["bbox"][2]) > max(p[0], b["bbox"][0])
                        ),
                        len(blocks),
                    )
                    blocks.insert(
                        at,
                        {
                            "label": "Picture",
                            "bbox": [round(float(v), 1) for v in p[:4]],
                            "text": "",
                        },
                    )
        elif len(boxes) < 2:
            md = "\n".join(texts)
        return Page(lines, t, md, note=note, blocks=blocks)
