import * as ort from 'onnxruntime-web/wasm';
import { publish, type TensorWire } from './protocol';

const sessions = new Map<string, ort.InferenceSession>();
self.onmessage = async ({ data }) => {
  if (data.kind === 'init') {
    try {
      ort.env.wasm.wasmPaths = data.runtimeURL;
      ort.env.wasm.numThreads = 1;
      ort.env.wasm.proxy = false;
      for (const name of data.models as string[]) {
        const url = new URL(name, data.modelURL).href;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Model download (${res.status}): ${name}`);
        const bytes = await res.arrayBuffer();
        const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
          .map(n => n.toString(16).padStart(2, '0')).join('');
        if (data.sha256[name] !== hash) throw new Error(`Model checksum mismatch: ${name}`);
        const session = await ort.InferenceSession.create(bytes,
          { executionProviders: ['wasm'], enableCpuMemArena: false });
        sessions.set(name, session);
      }
      self.postMessage({ kind: 'ready', inputs: Object.fromEntries(
        [...sessions].map(([name, s]) => [name, s.inputNames])) });
    } catch (e) { self.postMessage({ kind: 'error', error: String(e) }); }
  } else if (data.kind === 'run') {
    try {
      const session = sessions.get(data.model);
      if (!session) throw new Error(`Model not loaded: ${data.model}`);
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
        result = await session.run(feed);
        const names = data.outputs ?? session.outputNames;
        publish(data.buffer, names.map((key: string) => ({ type: result![key].type,
          dims: [...result![key].dims], data: result![key].data as ArrayBufferView })));
      } finally {
        Object.values(feed).forEach(t => t.dispose());
        if (result) Object.values(result).forEach(t => t.dispose());
      }
    } catch (e) { publish(data.buffer, new Error(e instanceof Error ? e.stack : String(e))); }
  }
};
