"""ONNX Runtime Python surface used by Indra → onnxruntime-web WASM worker."""
import numpy as np
from pathlib import Path
from types import SimpleNamespace
from pyodide.ffi import to_js
from js import Object
from indra_bridge import inference, input_names, output_names


class SessionOptions:
    pass


class RunOptions:
    """Configuration surface for upstream helpers and their tests.

    CUDA arena settings have no effect on the browser's WASM/WebGPU sessions.
    """
    def __init__(self):
        self._config = {}

    def add_run_config_entry(self, key, value):
        self._config[key] = value

    def get_run_config_entry(self, key):
        if key not in self._config:
            raise RuntimeError(f"Run option is not configured: {key}")
        return self._config[key]


GraphOptimizationLevel = SimpleNamespace(ORT_ENABLE_ALL=99)


class InferenceSession:
    def __init__(self, path, sess_options=None, providers=None):
        self.name = Path(path).name
        if not input_names.has(self.name):
            raise RuntimeError(f"ONNX model is not loaded: {self.name}")

    def get_inputs(self):
        return [SimpleNamespace(name=n) for n in input_names.get(self.name).to_py()]

    def get_outputs(self):
        return [SimpleNamespace(name=n) for n in output_names.get(self.name).to_py()]

    async def run(self, output_names, feed, run_options=None):
        # Transfer raw contiguous bytes, including int64 and bool. Never round
        # integers through JSON/JavaScript Number (which only has 53 bits).
        wire = {}
        for key, value in feed.items():
            arr = np.ascontiguousarray(value) if value.ndim else value
            wire[key] = {"type": "bool" if arr.dtype == np.bool_ else str(arr.dtype),
                         "dims": list(arr.shape), "data": arr.view(np.uint8).reshape(-1)
                         if arr.ndim else np.frombuffer(arr.tobytes(), np.uint8)}
        result = await inference(self.name, to_js(wire, dict_converter=Object.fromEntries),
                                 to_js(output_names))
        return [np.frombuffer(t.data.to_py(), dtype=np.dtype(t.type if t.type != "bool" else "bool"))
                .reshape(t.dims.to_py()).copy() for t in result]
