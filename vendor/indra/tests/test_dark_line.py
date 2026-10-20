import numpy as np

from indra_ocr.rec_preproc import crop_line


def page(bg: int, ink: int) -> np.ndarray:
    g = np.full((100, 400), bg, np.uint8)
    g[40:60, 20:380:12] = ink  # one line of strokes
    return g


def test_light_text_on_dark_ground_reads_as_dark_text():
    box = (10, 35, 390, 65)
    for window in (1, 3):
        dark = crop_line(page(15, 240), box, 32, window=window)
        light = crop_line(page(240, 15), box, 32, window=window)
        assert np.abs(dark - light).mean() < 0.05
        assert np.median(light) < 0.2


def test_dark_text_on_a_shadowed_ground_is_not_inverted():
    box = (10, 35, 390, 65)
    shadow = crop_line(page(110, 20), box, 32)
    # not inverted: the ground keeps its ink value 1 - 110/255 (inverted: 0.43)
    assert abs(np.median(shadow) - (1 - 110 / 255)) < 0.02


def test_percentiles_match_numpy():
    from indra_ocr.rec_preproc import _percentiles

    rng = np.random.default_rng(0)
    for n in (1, 2, 3, 7, 50, 999, 4096):
        for hi in (2, 30, 256):
            b = rng.integers(0, hi, size=n).astype(np.uint8)
            assert np.allclose(_percentiles(b), np.percentile(b, (2, 50, 98)), rtol=0, atol=1e-9)
