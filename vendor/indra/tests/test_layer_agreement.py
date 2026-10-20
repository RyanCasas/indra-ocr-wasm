"""The text-layer script check: a layer that stores Latin codes for another script (legacy Hindi
fonts such as Kruti Dev) is not trusted, and OCR reads the page."""

from indra_ocr.document import latin_share, layer_agrees


def test_latin_share():
    assert latin_share("dk;kZy; izkpk;Z] jktdh; egkfo|ky;") == 1.0  # Kruti Dev codes
    assert latin_share("कार्यालय प्राचार्य, राजकीय महाविद्यालय") == 0.0
    assert 0.3 < latin_share("PDF फ़ाइल") < 0.6


def test_the_page_fails_only_when_almost_no_line_agrees():
    assert not layer_agrees([False, False, False, False, False, False])  # a legacy font
    assert not layer_agrees([False, False, False, False, True])  # one line of five: a Latin title
    assert layer_agrees([True, False, False, False])  # a quarter of the lines agree
    assert layer_agrees([True] * 6)
    assert layer_agrees([])  # nothing checked: keep the layer
