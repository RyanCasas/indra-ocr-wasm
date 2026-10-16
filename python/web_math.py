"""Asynchronous browser adaptation of Indra's math reader.

The algorithms follow the pinned Apache-2.0 upstream in vendor/indra/indra_ocr;
inference calls yield to the browser event loop instead of blocking a worker.
Synchronous helpers remain inherited from upstream.
"""
from __future__ import annotations

import numpy as np
from indra_ocr.math import MathReader, MATH_MIN, MATH_MIN_CONF, EARLY_STOP_MARGIN, BOS, EOS, N_SPECIAL, detokenize
from indra_ocr.line_mask import crop_lines
from indra_ocr.rec_preproc import pad_batch, width_batches


class WebMathReader(MathReader):
    def __init__(self, reader: MathReader):
        # Reuse the sessions and metadata already configured by OrtOCR.
        self.__dict__.update(vars(reader))

    async def flags(self, crops: list, batch: int = 64) -> list[bool]:
        """Per line crop (the recognizer's crop): does it hold math?"""
        out = [False] * len(crops)
        for idx in width_batches([c.shape[1] for c in crops], batch):
            arr, widths = pad_batch([crops[j] for j in idx])
            p = (await self.cls.run(None, {"x": arr, "widths": widths}))[0]
            for k, j in enumerate(idx):
                out[j] = bool(p[k] > MATH_MIN)
        return out

    async def read(
        self, gray: np.ndarray, boxes: np.ndarray, batch: int = 64
    ) -> list[tuple[str, float]]:
        """(text with inline LaTeX, mean token probability) for each box."""
        crops = crop_lines(gray, boxes[:, :4], self.height, None)
        out = [("", 0.0)] * len(crops)
        # Few, wide batches: each batch is one decoding loop of up to max_tokens
        # steps, and a step costs about the same for 8 lines as for 40.
        widths = [c.shape[1] for c in crops]
        for idx in width_batches(widths, batch, max_ratio=4.0, max_area=16 * 64 * 640):
            arr, widths = pad_batch([crops[j] for j in idx])
            mem, mask = (await self.enc.run(None, {"x": arr, "widths": widths}))
            feed = {"memory": mem, "mask": mask}
            names = self.inputs["math_dec_init.onnx"]
            ck, cv = (await self.init.run(None, {k: v for k, v in feed.items() if k in names}))
            B = len(idx)
            sk = np.zeros((self.layers, B, self.heads, 0, self.head_dim), np.float32)
            sv = sk
            tok = np.full(B, BOS, np.int64)
            step_in = self.inputs["math_dec_step.onnx"]
            seqs: list[list[int]] = [[] for _ in range(B)]
            probs: list[list[float]] = [[] for _ in range(B)]
            done = np.zeros(B, bool)
            for t in range(self.max_tokens - 1):
                feed = {
                    "token": tok,
                    "pos": np.array(t, np.int64),
                    "self_k": sk,
                    "self_v": sv,
                    "cross_k": ck,
                    "cross_v": cv,
                    "mask": mask,
                }
                logits, sk, sv = (await self.step.run(
                    None, {k: v for k, v in feed.items() if k in step_in}
                ))
                tok = logits.argmax(-1).astype(np.int64)
                e = np.exp(logits - logits.max(-1, keepdims=True))
                top = 1.0 / e.sum(-1)  # softmax probability of the argmax token
                for b in range(B):
                    if not done[b]:
                        probs[b].append(float(top[b]))
                        if tok[b] == EOS:
                            done[b] = True
                        elif (
                            len(probs[b]) >= 8
                            and np.mean(probs[b]) < MATH_MIN_CONF - EARLY_STOP_MARGIN
                        ):
                            done[b] = True  # rejected: keeps a low mean probability
                        elif tok[b] >= N_SPECIAL:
                            seqs[b].append(int(tok[b]))
                if done.all():
                    break
            for k, j in enumerate(idx):
                text = detokenize([self.itos[i] for i in seqs[k]])
                out[j] = (text, float(np.mean(probs[k])) if probs[k] else 0.0)
        return out
