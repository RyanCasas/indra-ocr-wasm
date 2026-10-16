import numpy as np
import pytest

from indra_ocr.document import MAX_PAGE_PIXELS, Converter
from indra_ocr.pipeline import InputError, Page, is_pdf, read_images


class StubOCR:
    """Counts pages; fails on pages that are all black."""

    vocab = vocab_cjk = None

    def __init__(self):
        self.seen = []

    def __call__(self, gray, turn=True):
        self.seen.append(gray.shape)
        if gray.max() == 0:
            raise RuntimeError("stub failure")
        return Page([])


def _pdf(path, sizes):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument.new()
    for w, h in sizes:
        doc.new_page(w, h)
    doc.save(str(path))
    return path


def test_file_type_comes_from_the_bytes(tmp_path):
    import cv2

    pdf = _pdf(tmp_path / "no_extension", [(200, 300)])
    png = tmp_path / "image_named.pdf"
    cv2.imwrite(str(tmp_path / "x.png"), np.full((50, 40), 255, np.uint8))
    (tmp_path / "x.png").rename(png)
    assert is_pdf(pdf) and not is_pdf(png)
    conv = Converter(StubOCR(), mode="ocr")
    assert [p.source for _, p in conv.convert(pdf)] == ["ocr"]
    assert len(list(conv.convert(png))) == 1


def test_every_tiff_frame_is_a_page(tmp_path):
    from PIL import Image

    frames = [Image.new("L", (60, 80), v) for v in (255, 200, 255)]
    path = tmp_path / "three.tiff"
    frames[0].save(path, save_all=True, append_images=frames[1:])
    assert len(read_images(path)) == 3


def test_unreadable_files_raise_input_error(tmp_path):
    conv = Converter(StubOCR())
    for name, data in (
        ("garbage.pdf", b"%PDF-1.4 broken"),
        ("empty.png", b""),
        ("text.txt", b"hello"),
    ):
        (tmp_path / name).write_bytes(data)
        with pytest.raises(InputError):
            list(conv.convert(tmp_path / name))
    with pytest.raises(InputError, match="no such file"):
        list(conv.convert(tmp_path / "missing.pdf"))


def test_password_protected_pdf(tmp_path):
    pikepdf = pytest.importorskip("pikepdf")
    src = _pdf(tmp_path / "plain.pdf", [(200, 300)])
    locked = tmp_path / "locked.pdf"
    pikepdf.open(src).save(
        locked, encryption=pikepdf.Encryption(user="pw", owner="owner")
    )
    conv = Converter(StubOCR(), mode="ocr")
    with pytest.raises(InputError, match="password"):
        list(conv.convert(locked))
    assert len(list(conv.convert(locked, password="pw"))) == 1


def test_a_failing_page_does_not_end_the_document(tmp_path):
    from PIL import Image

    frames = [
        Image.new("L", (60, 80), v) for v in (255, 0, 255)
    ]  # page 2 makes the stub fail
    path = tmp_path / "pages.tiff"
    frames[0].save(path, save_all=True, append_images=frames[1:])
    pages = [p for _, p in Converter(StubOCR()).convert(path)]
    assert [p.source for p in pages] == ["ocr", "error", "ocr"]
    assert "stub failure" in pages[1].note
    assert pages[1].markdown == "" and pages[1].timings["total_ms"] == 0.0


def test_huge_pages_render_below_the_pixel_cap(tmp_path):
    import pypdfium2 as pdfium

    pdf = _pdf(tmp_path / "poster.pdf", [(14400, 14400), (612, 792)])
    conv = Converter(StubOCR(), mode="ocr")
    doc = pdfium.PdfDocument(str(pdf))
    big, letter = conv.page_scale(doc[0]), conv.page_scale(doc[1])
    assert (14400 * big) ** 2 <= MAX_PAGE_PIXELS * 1.01 and letter == pytest.approx(
        200 / 72
    )
    list(conv.convert(pdf))
    assert conv.ocr.seen[0][0] * conv.ocr.seen[0][1] <= MAX_PAGE_PIXELS * 1.01


def test_parallel_plan_has_one_unit_per_page(tmp_path):
    import cv2

    from indra_ocr.parallel import _plan, usable_cores

    pdf = _pdf(tmp_path / "five.pdf", [(200, 300)] * 5)
    png = tmp_path / "scan.png"
    cv2.imwrite(str(png), np.full((50, 40), 255, np.uint8))
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 broken")
    plan = _plan([pdf, tmp_path / "missing.pdf", bad, png], max_pages=3, password=None)
    assert [u[1] for u in plan[0]] == [0, 1, 2]  # max_pages caps the units
    assert isinstance(plan[1], InputError) and isinstance(plan[2], InputError)
    assert plan[3] == [(str(png), None, 3)]  # an image file is one unit
    assert usable_cores() >= 1


def test_model_errors_are_one_clear_message(tmp_path, monkeypatch, capsys):
    import huggingface_hub

    from indra_ocr import ModelError
    from indra_ocr.cli import main
    from indra_ocr.models import model_dir

    with pytest.raises(ModelError, match="lacks det.onnx"):
        model_dir(tmp_path)

    def offline(*a, **k):
        raise ConnectionError("network is unreachable")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", offline)
    monkeypatch.delenv("INDRA_OCR_MODEL_DIR", raising=False)
    with pytest.raises(ModelError, match="network is unreachable"):
        model_dir(None)
    img = tmp_path / "a.png"
    import cv2

    cv2.imwrite(str(img), np.full((50, 40), 255, np.uint8))
    assert main([str(img)]) == 1
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith(
        "indra-ocr: could not download the models"
    )


def test_version_flag(capsys):
    from indra_ocr import __version__
    from indra_ocr.cli import main

    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.strip() == f"indra-ocr {__version__}"


def test_cached_models_are_checked_once_a_day(tmp_path, monkeypatch):
    import os
    import time

    import huggingface_hub
    from huggingface_hub import constants

    from indra_ocr import models

    monkeypatch.delenv("INDRA_OCR_MODEL_DIR", raising=False)
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path))
    calls = []
    state = {"cached": False, "online": True}

    def fake(repo, local_files_only=False, **kw):
        calls.append("local" if local_files_only else "hub")
        if local_files_only and not state["cached"]:
            raise FileNotFoundError("not cached")
        if not local_files_only and not state["online"]:
            raise ConnectionError("offline")
        state["cached"] = True
        return str(tmp_path / "snap")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake)
    models.model_dir(None)  # first run: downloads
    assert calls == ["local", "hub"]
    calls.clear()
    models.model_dir(None)  # checked under a day ago: cache only
    assert calls == ["local"]
    stamp = models._check_stamp(models.HF_REVISION)
    old = time.time() - models.CHECK_EVERY_S - 60
    os.utime(stamp, (old, old))
    calls.clear()
    models.model_dir(None)  # a day later: checks the Hub again
    assert calls == ["local", "hub"]
    os.utime(stamp, (old, old))
    state["online"] = False
    assert models.model_dir(None) == tmp_path / "snap"  # offline: the cached models
