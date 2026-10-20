"""Lines without text of their own: leader runs and lone list bullets."""

import numpy as np

from indra_ocr.pipeline import tidy_lines


def rec(*texts):
    return [(t, 0.9, []) for t in texts]


def test_leader_runs_go_and_other_marks_stay():
    boxes = np.array(
        [
            [0, 0, 100, 10],  # a label with leaders: text, stays
            [0, 20, 30, 30],  # "......": a leader run
            [0, 40, 12, 50],  # "- -": two short dashes, square box: stays
            [0, 60, 10, 70],  # "-": a table cell dash, square box: stays
            [0, 80, 60, 90],  # ".": a dotted rule read as one dot (wide box)
            [0, 100, 8, 110],  # ".": a speck
            [0, 120, 80, 130],  # "-": a dashed rule (wide box)
            [0, 140, 30, 150],  # "( )": a checkbox: stays
        ],
        np.float32,
    )
    texts = ("Name ........", "......", "- -", "-", ".", ".", "-", "( )")
    b, r = tidy_lines(boxes, rec(*texts))
    assert [x[0] for x in r] == ["Name ........", "- -", "-", "( )"]
    assert len(b) == 4


def test_a_lone_bullet_joins_its_item():
    boxes = np.array([[10, 0, 18, 12], [24, 0, 200, 12], [10, 30, 18, 42]], np.float32)
    b, r = tidy_lines(boxes, rec("•", "First item", "•"))
    assert [x[0] for x in r] == ["• First item", "•"]  # the second bullet has no item
    assert b[0].tolist() == [10, 0, 200, 12]


def test_a_dash_next_to_a_cell_is_not_a_bullet():
    boxes = np.array([[10, 0, 18, 12], [24, 0, 60, 12]], np.float32)
    b, r = tidy_lines(boxes, rec("-", "5.0"))
    assert [x[0] for x in r] == ["-", "5.0"]


def test_a_numbered_marker_joins_its_item_with_its_tokens():
    # "1." cut off a hanging-indent item by a gutter, 2 line heights away
    boxes = np.array([[10, 0, 22, 12], [46, 0, 200, 12]], np.float32)
    r = [
        ("1.", 0.9, [("1", 13.0, 0), (".", 19.0, 1)]),
        ("First item", 0.9, [("F", 49.0, 3), ("i", 55.0, 4)]),
    ]
    b, out = tidy_lines(boxes, r, space=0)
    assert [x[0] for x in out] == ["1. First item"]
    assert [tk[0] for tk in out[0][2]] == ["1", ".", " ", "F", "i"]
    assert b[0].tolist() == [10, 0, 200, 12]


def test_a_marker_far_from_the_next_cell_stays():
    boxes = np.array([[10, 0, 22, 12], [60, 0, 200, 12]], np.float32)
    b, r = tidy_lines(boxes, rec("2)", "Next column"))
    assert [x[0] for x in r] == ["2)", "Next column"]
