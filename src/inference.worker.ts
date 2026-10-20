import * as ort from 'onnxruntime-web/webgpu';
import { InferenceBackend } from './inference-backend';
import { copyTensors, type TensorWire } from './protocol';

const sessions = new Map<string, InferenceBackend<ort.InferenceSession>>();
self.onmessage = async ({ data }) => {
  if (data.kind === 'init') {
    try {
      ort.env.wasm.wasmPaths = data.runtimeURL;
      ort.env.wasm.numThreads = 1;
      ort.env.wasm.proxy = false;
      let preferGpu = false;
      if (data.backend !== 'wasm') {
        try {
          const gpu = (navigator as Navigator & { gpu?: { requestAdapter(): Promise<unknown> } }).gpu;
          preferGpu = !!(await gpu?.requestAdapter());
        } catch { /* Adapter requests can fail even when the API is exposed. */ }
        if (!preferGpu) self.postMessage({ kind: 'progress', message: 'WebGPU adapter unavailable; using WASM' });
      }
      for (const name of data.models as string[]) {
        const url = new URL(name, data.modelURL).href;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Model download (${res.status}): ${name}`);
        const bytes = await res.arrayBuffer();
        const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
          .map(n => n.toString(16).padStart(2, '0')).join('');
        if (data.sha256[name] !== hash) throw new Error(`Model checksum mismatch: ${name}`);
        const mathModel = name.startsWith('math');
        if (mathModel) self.postMessage({ kind: 'progress', message: `${name}: using CPU/WASM for math` });
        const backend = new InferenceBackend(
          gpu => ort.InferenceSession.create(bytes, {
            executionProviders: gpu ? ['webgpu', 'wasm'] : ['wasm'], enableCpuMemArena: false,
          }), preferGpu && !mathModel, message => self.postMessage({ kind: 'progress', message: `${name}: ${message}` }));
        await backend.load();
        sessions.set(name, backend);
      }
      const metadata = await Promise.all([...sessions].map(async ([name, s]) => {
        const session = await s.load();
        return { name, inputs: session.inputNames, outputs: session.outputNames };
      }));
      self.postMessage({ kind: 'ready',
        inputs: Object.fromEntries(metadata.map(s => [s.name, s.inputs])),
        outputs: Object.fromEntries(metadata.map(s => [s.name, s.outputs])) });
    } catch (e) { self.postMessage({ kind: 'error', error: String(e) }); }
  } else if (data.kind === 'run') {
    try {
      const backend = sessions.get(data.model);
      if (!backend) throw new Error(`Model not loaded: ${data.model}`);
      const feed: Record<string, ort.Tensor> = {};
      const arrays = { float32: Float32Array, float64: Float64Array, int64: BigInt64Array,
        int32: Int32Array, uint8: Uint8Array, bool: Uint8Array };
      for (const [key, t] of Object.entries(data.feed) as [string, TensorWire][]) {
        const ArrayType = arrays[t.type as keyof typeof arrays];
        if (!ArrayType) throw new Error(`Unsupported tensor dtype: ${t.type}`);
        feed[key] = new ort.Tensor(t.type as ort.Tensor.Type,
          new ArrayType(t.data.buffer as ArrayBuffer, t.data.byteOffset, t.data.byteLength / ArrayType.BYTES_PER_ELEMENT), t.dims);
      }
      let result: ort.InferenceSession.ReturnType | undefined;
      try {
        result = await backend.run(session => data.outputs ? session.run(feed, data.outputs) : session.run(feed));
        const names = data.outputs ?? (await backend.load()).outputNames;
        const tensors = copyTensors(names.map((key: string) => ({ type: result![key].type,
          dims: [...result![key].dims], data: result![key].data as ArrayBufferView })), data.responseBytes);
        self.postMessage({ kind: 'result', id: data.id, tensors },
          { transfer: tensors.map(tensor => tensor.data.buffer as ArrayBuffer) });
      } finally {
        Object.values(feed).forEach(t => t.dispose());
        if (result) Object.values(result).forEach(t => t.dispose());
      }
    } catch (e) {
      self.postMessage({ kind: 'error', id: data.id, error: e instanceof Error ? e.stack : String(e) });
    }
  }
};
