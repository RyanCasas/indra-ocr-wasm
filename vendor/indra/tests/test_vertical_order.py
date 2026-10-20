"""Reading order on a vertical page read turned: tiers become side-by-side columns."""

import numpy as np

from indra_ocr.order_post import xycut_blocks


def _tier(x0: float, n: int) -> list[list[float]]:
    # n turned columns (lines 20 px high, 12 px apart), 300 px long
    return [[x0, 40.0 + 32 * i, x0 + 300, 60.0 + 32 * i] for i in range(n)]


def test_tiers_are_read_one_after_the_other():
    # Two tiers 40 px apart (2 line heights) whose lines sit on the same rows.
    # Row by row would interleave them; XY-cut reads the left tier first.
    left, right = _tier(0, 5), _tier(340, 5)
    boxes = np.array([b for pair in zip(left, right) for b in pair], np.float32)
    blocks = xycut_blocks(boxes)
    assert len(blocks) == 2
    assert blocks[0] == [0, 2, 4, 6, 8]
    assert blocks[1] == [1, 3, 5, 7, 9]


def test_line_spacing_does_not_cut_a_block():
    blocks = xycut_blocks(np.array(_tier(0, 6), np.float32))
    assert blocks == [[0, 1, 2, 3, 4, 5]]


def test_a_wide_row_gap_starts_a_new_block():
    # an article break: 60 px (3 line heights) between line 2 and line 3
    boxes = np.array(
        _tier(0, 3) + [[0, 196 + 32 * i, 300, 216 + 32 * i] for i in range(2)],
        np.float32,
    )
    assert xycut_blocks(boxes) == [[0, 1, 2], [3, 4]]
