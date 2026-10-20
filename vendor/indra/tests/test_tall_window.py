import numpy as np

from indra_ocr.line_mask import crop_lines
from indra_ocr.rec_preproc import crop_line


def test_tall_window_keeps_the_line_scale():
    rng = np.random.default_rng(0)
    gray = (rng.random((600, 900)) * 255).astype(np.uint8)
    box = (100.0, 280.0, 700.0, 310.0)
    one = crop_line(gray, box, 32)
    tall = crop_line(gray, box, 32, window=3)
    assert tall.shape == (96, one.shape[1])
    assert np.abs(tall[32:64] - one).mean() < 0.15


def test_tall_window_is_never_masked():
    gray = np.full((200, 400), 255, np.uint8)
    out = crop_lines(gray, [(10, 50, 300, 70)], 32, sess=object(), window=3)
    assert out[0].shape[0] == 96
