import cv2
import numpy as np

from indra_ocr.pipeline import estimate_skew, rotate_page


def _text_page():
    """A page of dark text-like rows (bars broken into words)."""
    rng = np.random.default_rng(0)
    g = np.full((1400, 1000), 255, np.uint8)
    for y in range(120, 1300, 42):
        x = 80
        while x < 900:
            w = int(rng.integers(30, 110))
            cv2.rectangle(g, (x, y), (min(x + w, 920), y + 16), 30, -1)
            x += w + int(rng.integers(12, 24))
    return g


def test_seven_degrees_is_straightened():
    g = _text_page()
    for tilt in (7.0, -7.0, 12.0, 30.0, -40.0):
        tilted = rotate_page(g, tilt)
        assert abs(estimate_skew(tilted) + tilt) < 0.5
