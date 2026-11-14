"""Asynchronous regressions using real browser ONNX sessions."""
import numpy as np
from indra_ocr.rec_preproc import pad_batch


async def check_narrow_crops(ocr):
    # Feed the crop directly: detection may discard an isolated letter. These
    # widths used to pool down to zero columns in the script classifier.
    for width in (8, 22, 31):
        crop = np.zeros((ocr.height, width), np.float32)
        crop[5:-5, width // 2] = 1
        groups, sure = await ocr.line_groups([crop])
        assert len(groups) == len(sure) == 1
        arr, widths = pad_batch([crop])
        # Exercise the new optional run_options argument over the real bridge.
        result = await ocr.script.run(None, {"x": arr, "widths": widths}, run_options=None)
        assert result[0].shape[0] == 1 and np.isfinite(result[0]).all()
    print("Narrow-crop browser inference passed (8, 22, 31 px)")
