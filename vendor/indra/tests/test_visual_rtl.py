"""A text layer whose right-to-left letters are stored in visual order (issue #11:
Chrome-printed Arabic script) is not trusted, so the page goes to OCR."""

import numpy as np

from indra_ocr import textlayer
from indra_ocr.textlayer import VISUAL_RTL, TextLine, read_text_layer, visual_rtl_frac

WORD = "مرحبا بالعالم في هذا الملف"


def _run(text: str, visual: bool, y: float = 100.0) -> TextLine:
    """A run of ``text`` (logical order), its glyphs placed right to left as a
    renderer draws them; ``visual`` stores them left to right instead."""
    chars, x = [], 500.0
    for c in text:
        chars.append((c, (x - 8, y, x, y + 12)))
        x -= 8
    if visual:
        chars = chars[::-1]
    return TextLine((x, y, 500.0, y + 12), "".join(c for c, _ in chars), chars)


def test_logical_order_steps_right_to_left():
    pairs, share = visual_rtl_frac([_run(WORD, visual=False)])
    assert pairs > 15 and share == 0.0


def test_visual_order_steps_left_to_right():
    pairs, share = visual_rtl_frac([_run(WORD, visual=True)])
    assert pairs > 15 and share == 1.0


def test_latin_runs_do_not_count():
    run = TextLine((0, 0, 100, 12), "Hello", [(c, (8 * i, 0, 8 * i + 8, 12)) for i, c in enumerate("Hello")])
    assert visual_rtl_frac([run]) == (0, 0.0)


def _layer(monkeypatch, visual: bool):
    runs = [_run(WORD, visual, y=100 + 20 * k) for k in range(3)]
    monkeypatch.setattr(textlayer, "invisible_text_frac", lambda page: 0.0)
    monkeypatch.setattr(
        textlayer, "extract_runs", lambda page, turn=0, frame=None: (runs, {"chars": 60, "bad": 0})
    )

    class Page:
        def get_size(self):
            return 612.0, 792.0

    gray = np.zeros((792, 612), np.uint8)  # ink everywhere: the ink check passes
    return read_text_layer(Page(), gray, 1.0)


def test_a_visual_order_layer_is_not_trusted(monkeypatch):
    tl = _layer(monkeypatch, visual=True)
    assert not tl.trusted and tl.reason == VISUAL_RTL


def test_a_logical_order_layer_is_trusted(monkeypatch):
    tl = _layer(monkeypatch, visual=False)
    assert tl.trusted and tl.reason == ""
