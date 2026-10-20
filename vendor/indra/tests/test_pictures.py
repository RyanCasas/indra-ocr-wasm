import numpy as np

from indra_ocr.layout_post import page_markdown
from indra_ocr.pipeline import picture_boxes


def test_picture_boxes_from_the_picture_channel():
    logit = np.full((100, 80), -6.0, np.float32)
    logit[10:50, 20:60] = 4.0  # a picture
    logit[90:92, 2:4] = 4.0  # a speck: under the minimum area
    boxes = picture_boxes(
        logit, 0.5, (400, 320)
    )  # input scale 0.5: map px -> 4 page px
    assert boxes.shape == (1, 4)
    assert np.allclose(boxes[0], [80, 40, 240, 200])


def test_picture_placeholder_sits_before_the_block_below_it():
    boxes = np.array([[0, 0, 100, 10], [0, 200, 100, 210]], np.float32)
    cls = np.zeros((2, 10), np.float32)
    cls[:, 0] = 5.0  # Text
    same = np.full((2, 2), -5.0, np.float32)
    md = page_markdown(
        boxes,
        ["above", "below"],
        [0, 1],
        cls,
        same,
        pictures=np.array([[0, 50, 100, 150]]),
    )
    assert md.split("\n\n") == ["above", "![](picture-0)", "below"]
