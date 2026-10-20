"""A table set sideways on a portrait page: the text layer reads turned upright."""

import ctypes

import pypdfium2 as pdfium
import pypdfium2.raw as R
import pytest

from indra_ocr.textlayer import extract_runs, page_turn

LINES = ["Table 2 Baseline characteristics", "Age 54 years", "Women 61 percent"]


def _sideways_pdf(path, rotate=0):
    doc = pdfium.PdfDocument.new()
    page = doc.new_page(612, 792)
    page.set_rotation(rotate)
    for i, t in enumerate(LINES):
        obj = R.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", ctypes.c_float(12.0))
        R.FPDFText_SetText(obj, (ctypes.c_ushort * (len(t) + 1))(*map(ord, t), 0))
        # Baselines run bottom to top: the content is turned a quarter turn
        # counter-clockwise, as a landscape table on a portrait page.
        R.FPDFPageObj_Transform(obj, 0, 1, -1, 0, 100 + 30 * i, 100)
        R.FPDFPage_InsertObject(page.raw, obj)
    R.FPDFPage_GenerateContent(page.raw)
    doc.save(str(path))


def test_sideways_page_reads_turned(tmp_path):
    _sideways_pdf(tmp_path / "s.pdf")
    page = pdfium.PdfDocument(str(tmp_path / "s.pdf"))[0]
    runs, st = extract_runs(page)
    assert st["quarters"][1] == st["chars"]  # nothing upright
    assert all(r.quarter == 1 for r in runs)  # every run a quarter turn away
    assert page_turn(st) == 1
    runs, st = extract_runs(page, 1)
    assert [r.text for r in runs] == LINES and not any(r.quarter for r in runs)
    # Boxes are in the turned frame: 792 wide, 612 high; the first line is on top.
    assert all(0 <= r.bbox[0] < r.bbox[2] <= 792 and r.bbox[3] <= 612 for r in runs)
    assert runs[0].bbox[1] < runs[1].bbox[1] < runs[2].bbox[1]


def test_upright_page_is_not_turned(tmp_path):
    doc = pdfium.PdfDocument.new()
    page = doc.new_page(612, 792)
    obj = R.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", ctypes.c_float(12.0))
    t = "Upright text"
    R.FPDFText_SetText(obj, (ctypes.c_ushort * (len(t) + 1))(*map(ord, t), 0))
    R.FPDFPageObj_Transform(obj, 1, 0, 0, 1, 72, 700)
    R.FPDFPage_InsertObject(page.raw, obj)
    R.FPDFPage_GenerateContent(page.raw)
    doc.save(str(tmp_path / "u.pdf"))
    runs, st = extract_runs(pdfium.PdfDocument(str(tmp_path / "u.pdf"))[0])
    assert [r.text for r in runs] == [t] and page_turn(st) == 0


def test_a_sideways_label_on_an_upright_page_is_its_own_run(tmp_path):
    doc = pdfium.PdfDocument.new()
    page = doc.new_page(612, 792)
    for t, m in [
        ("Upright body text", (1, 0, 0, 1, 72, 700)),
        ("Axis label", (0, 1, -1, 0, 40, 300)),
    ]:
        obj = R.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", ctypes.c_float(12.0))
        R.FPDFText_SetText(obj, (ctypes.c_ushort * (len(t) + 1))(*map(ord, t), 0))
        R.FPDFPageObj_Transform(obj, *m)
        R.FPDFPage_InsertObject(page.raw, obj)
    R.FPDFPage_GenerateContent(page.raw)
    doc.save(str(tmp_path / "m.pdf"))
    runs, st = extract_runs(pdfium.PdfDocument(str(tmp_path / "m.pdf"))[0])
    assert page_turn(st) == 0
    assert [(r.text, r.quarter) for r in runs] == [
        ("Upright body text", 0),
        ("Axis label", 1),
    ]
    side = runs[1].bbox
    assert (
        side[3] - side[1] > side[2] - side[0]
    )  # a tall box: the label runs up the page


def test_surrogate_pairs_join_into_one_character():
    from indra_ocr.textlayer import code_point

    assert code_point(0xD835, 0xDC64) == (
        "\U0001d464",
        True,
    )  # math italic w (issue #3)
    assert code_point(0x61) == ("a", False)
    assert code_point(0xD835, 0x62) == ("\ufffd", False)  # a lone high surrogate
    assert code_point(0xDC64) == ("\ufffd", False)  # a lone low surrogate


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
@pytest.mark.parametrize("sideways", [False, True])
def test_the_turn_counts_the_pages_rotate(tmp_path, rotate, sideways):
    """/Rotate turns the page clockwise for display, so content set a quarter turn
    counter-clockwise (``sideways``) on a /Rotate 90 page shows upright: turn 0."""
    path = tmp_path / "r.pdf"
    if sideways:
        _sideways_pdf(path, rotate)
    else:
        doc = pdfium.PdfDocument.new()
        page = doc.new_page(612, 792)
        page.set_rotation(rotate)
        obj = R.FPDFPageObj_NewTextObj(doc.raw, b"Helvetica", ctypes.c_float(12.0))
        R.FPDFText_SetText(
            obj, (ctypes.c_ushort * (len(LINES[0]) + 1))(*map(ord, LINES[0]), 0)
        )
        R.FPDFPageObj_Transform(obj, 1, 0, 0, 1, 72, 700)
        R.FPDFPage_InsertObject(page.raw, obj)
        R.FPDFPage_GenerateContent(page.raw)
        doc.save(str(path))
    _, st = extract_runs(pdfium.PdfDocument(str(path))[0])
    assert page_turn(st) == (int(sideways) - rotate // 90) % 4


def _two_font_lines(path, rotate):
    """Two lines, each of a plain and an italic font run, on a page shown turned
    by /Rotate (the text itself is upright on the unrotated page)."""
    doc = pdfium.PdfDocument.new()
    page = doc.new_page(612, 792)
    page.set_rotation(rotate)
    for t, font, x, y in [
        ("programs to launch our latest initiative, ", b"Helvetica", 72, 700),
        ("One Million", b"Helvetica-Oblique", 272, 700),
        ("Black Women", b"Helvetica-Oblique", 72, 686),
        (". In the first two years", b"Helvetica", 132, 686),
    ]:
        obj = R.FPDFPageObj_NewTextObj(doc.raw, font, ctypes.c_float(10.0))
        R.FPDFText_SetText(obj, (ctypes.c_ushort * (len(t) + 1))(*map(ord, t), 0))
        R.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, y)
        R.FPDFPage_InsertObject(page.raw, obj)
    R.FPDFPage_GenerateContent(page.raw)
    doc.save(str(path))


def test_a_page_turned_by_rotate_reads_without_it(tmp_path):
    """On a /Rotate 180 page, pdfium joins a line's font runs out of order in the
    displayed frame; read without /Rotate (as Converter.pdf_page does when /Rotate
    alone turns the text), the lines come out in order."""
    _two_font_lines(tmp_path / "t.pdf", 180)
    page = pdfium.PdfDocument(str(tmp_path / "t.pdf"))[0]
    _, st = extract_runs(page)
    k = page_turn(st)
    assert k == 2 and (page.get_rotation() + 90 * k) % 360 == 0
    turned, _ = extract_runs(page, k)
    assert [r.text for r in turned] != [
        "programs to launch our latest initiative, One Million",
        "Black Women. In the first two years",
    ]  # pdfium's order in the turned frame (the bug this works around)
    page.set_rotation(0)
    runs, st = extract_runs(page)
    assert page_turn(st) == 0
    assert [r.text for r in runs] == [
        "programs to launch our latest initiative, One Million",
        "Black Women. In the first two years",
    ]
