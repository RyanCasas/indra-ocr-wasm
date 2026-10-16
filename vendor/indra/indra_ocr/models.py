"""Model files: a local folder, or a download from the Hugging Face repo."""

from __future__ import annotations

import os
import time
from pathlib import Path

HF_REPO = "datalab-to/indra-ocr"
# Model set this package version was built and tested against (a tag in HF_REPO).
HF_REVISION = "v3.1.1"
FILES = ("det.onnx", "rec.onnx", "order.onnx", "meta.json")
# A cached model folder is checked against the Hub at most this often (a moved
# tag or a fixed file arrives within a day; no network on the other runs).
CHECK_EVERY_S = 24 * 3600


class ModelError(OSError):
    """The models are not available: a download failed (no network, no access)
    or a local model folder lacks files."""


MATH_FILES = (
    "mathcls.onnx",
    "math_enc.onnx",
    "math_dec_init.onnx",
    "math_dec_step.onnx",
    "math_meta.json",
)


def model_dir(
    path: str | Path | None = None, revision: str | None = None, math: bool = False
) -> Path:
    """Folder with det.onnx, rec.onnx, order.onnx and meta.json (and, with
    ``math``, the math models, which are downloaded only then).

    Order of lookup: ``path``, the INDRA_OCR_MODEL_DIR environment variable, then
    a download of ``HF_REPO``.  Downloads are cached by huggingface_hub."""
    path = path or os.environ.get("INDRA_OCR_MODEL_DIR")
    if path:
        p = Path(path).expanduser()
        missing = [f for f in FILES[:2] + FILES[3:] if not (p / f).exists()]
        if math:
            missing += [f for f in MATH_FILES if not (p / f).exists()]
        if missing:
            raise ModelError(f"the model folder {p} lacks {', '.join(missing)}")
        return p
    from huggingface_hub import snapshot_download

    rev = revision or HF_REVISION
    # config.json is the file the Hub counts downloads by: it is requested with
    # the models on the first download and on each daily check.
    kw = dict(
        revision=rev,
        allow_patterns=[
            "*.onnx",
            "meta.json",
            "config.json",
            *(MATH_FILES if math else ()),
        ],
        ignore_patterns=[] if math else list(MATH_FILES),
    )
    try:
        cached = Path(snapshot_download(HF_REPO, local_files_only=True, **kw))
    except Exception:  # noqa: BLE001  (not cached yet)
        cached = None
    stamp = _check_stamp(rev)
    if cached is not None and _age(stamp) < CHECK_EVERY_S:
        return cached
    try:
        p = Path(snapshot_download(HF_REPO, **kw))
        _touch(stamp)
        return p
    except Exception as e:  # noqa: BLE001  (network, access, disk: one clear message)
        if cached is not None:  # offline or the Hub is down: keep the cached models
            return cached
        reason = (str(e).strip().splitlines() or [type(e).__name__])[0]
        raise ModelError(
            f"could not download the models from Hugging Face ({HF_REPO}, {rev}): "
            f"{type(e).__name__}: {reason[:200]}. Check the network connection, or "
            "point at a local model folder with --model-dir or INDRA_OCR_MODEL_DIR."
        ) from e


def _check_stamp(rev: str) -> Path:
    """The file whose modification time records the last check of ``rev``."""
    from huggingface_hub import constants

    name = f".indra_ocr_checked--{HF_REPO.replace('/', '--')}--{rev}"
    return Path(constants.HF_HUB_CACHE) / name


def _age(stamp: Path) -> float:
    try:
        return time.time() - stamp.stat().st_mtime
    except OSError:
        return float("inf")


def _touch(stamp: Path) -> None:
    try:
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
    except OSError:  # a read-only cache: check again next time
        pass
