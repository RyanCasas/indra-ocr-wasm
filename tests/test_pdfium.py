"""Real WASM PDFium adapter checks supplementing upstream's native-only tests."""
from pathlib import Path
import numpy as np
import pytest
import pypdfium2 as pdfium
from indra_ocr.document import Converter
from indra_ocr.pipeline import InputError, Page
from indra_ocr.textlayer import _device_affine, extract_runs, invisible_text_frac


def test_password_pdf_opens_and_rejects_wrong_password():
    class OCR:
        def __call__(self, gray, turn=True):
            assert gray.ndim == 2 and gray.max() == 255
            return Page([])
    converter = Converter(OCR(), mode="ocr", dpi=40)
    for password in (None, "wrong"):
        with pytest.raises(InputError, match="password"):
            list(converter.convert('/fixtures/locked.pdf', password=password))
    assert len(list(converter.convert('/fixtures/locked.pdf', password="pw"))) == 2


@pytest.mark.parametrize("name", ["digital.pdf", "rotated.pdf", "cropped.pdf", "invisible.pdf"])
def test_native_pdfium_character_geometry(name):
    import json
    from dataclasses import asdict
    expected = json.loads(Path('/fixtures/pdfium.json').read_text())[name]
    with pdfium.PdfDocument('/fixtures/' + name) as doc:
        page = doc[0]
        assert page.get_size() == pytest.approx(expected['size'])
        assert _device_affine(page) == pytest.approx(np.array(expected['affine']), abs=0.001)
        runs, stats = extract_runs(page)
        assert stats == expected['stats']
        assert invisible_text_frac(page) == expected['invisible']
        assert len(runs) == len(expected['runs'])
        for run, ref in zip(runs, expected['runs']):
            assert run.text == ref['text']
            assert run.bbox == pytest.approx(ref['bbox'], abs=0.001)
            for (c, box), (rc, rbox) in zip(run.chars, ref['chars']):
                assert c == rc
                assert box == pytest.approx(rbox, abs=0.001)
        assert page.render(scale=0.5, grayscale=True).to_numpy().ndim == 2
