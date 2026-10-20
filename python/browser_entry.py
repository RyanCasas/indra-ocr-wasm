"""Browser entry point for the asynchronous WASM pipeline."""
import json
from dataclasses import asdict
from web_document import WebConverter
from web_pipeline import WebOCR

_converter = None


def configure(options):
    global _converter
    config = json.loads(options)
    # Accepted by older browser callers; upstream 1.1 uses model reading order.
    config.pop("pdf_order", None)
    ocr = WebOCR("/models", threads=1, furniture=config.pop("furniture", False),
                 math=config.pop("math", False))
    _converter = WebConverter(ocr, **config)


async def convert(path, options):
    if _converter is None:
        raise RuntimeError("Indra is not initialized")
    return json.dumps([{"page": i, **asdict(page), "text": page.text}
                       async for i, page in _converter.convert(path, **json.loads(options))],
                      ensure_ascii=False, allow_nan=False)


def run_tests():
    import pytest
    return pytest.main(["/upstream/tests", "/browser-tests", "-ra", "--tb=short",
                        "-p", "no:cacheprovider"])
