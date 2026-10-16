"""Browser host boundary: model downloads belong to the JS asset loader.

Indra's path-based model validation and error handling remain unchanged. This
small import-compatible boundary also allows the original mocked cache tests.
"""
from types import SimpleNamespace
constants = SimpleNamespace(HF_HUB_CACHE="/cache/huggingface")


def snapshot_download(*args, **kwargs):
    raise OSError("Use createIndra({ modelURL }) to load browser models")
