"""Browser entry point; all OCR and document logic lives in vendor/indra."""
import json
from dataclasses import asdict
from pathlib import Path
import indra_ocr

_converter = None


def configure(options):
    global _converter
    _converter = indra_ocr.load(path="/models", threads=1, **json.loads(options))


def convert(path, options):
    if _converter is None:
        raise RuntimeError("Indra is not initialized")
    return json.dumps([{"page": i, **asdict(page), "text": page.text}
                       for i, page in _converter.convert(path, **json.loads(options))],
                      ensure_ascii=False, allow_nan=False)


def run_tests():
    import pytest
    return pytest.main(["/upstream/tests", "/browser-tests", "-ra", "--tb=short",
                        "-p", "no:cacheprovider"])
