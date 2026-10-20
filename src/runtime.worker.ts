import { loadPyodide, type PyodideInterface } from 'pyodide';
import { createPdfium } from './pdfium';
import { InferenceClient } from './inference-client';

let py: PyodideInterface;
let inferenceWorker: Worker;
let inference: InferenceClient;
let sequence = Promise.resolve();

function progress(message: string) { self.postMessage({ kind: 'progress', message }); }
async function get(url: string): Promise<Uint8Array<ArrayBuffer>> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed (${res.status}): ${url}`);
  return new Uint8Array(await res.arrayBuffer());
}
async function init(options: any) {
  const runtimeURL = options.runtimeURL;
  progress('Loading Python, NumPy and OpenCV WebAssembly');
  py = await loadPyodide({ indexURL: new URL('pyodide/', runtimeURL).href,
    stdout: (message: string) => self.postMessage({ kind: 'stdout', message }),
    stderr: (message: string) => self.postMessage({ kind: 'stderr', message }) });
  await py.loadPackage(['numpy', 'opencv-python']);
  const manifest = JSON.parse(new TextDecoder().decode(await get(new URL('python/manifest.json', runtimeURL).href)));
  for (const name of manifest.files as string[]) {
    const path = `/app/${name}`;
    py.FS.mkdirTree(path.slice(0, path.lastIndexOf('/')));
    py.FS.writeFile(path, await get(new URL(`python/${name}`, runtimeURL).href));
  }
  py.FS.mkdirTree('/models');
  // Metadata and n-gram tables live in Python; ONNX weights stay in the ORT worker.
  const modelManifest = JSON.parse(new TextDecoder().decode(await get(new URL('manifest.json', options.modelURL).href)));
  const files: string[] = modelManifest.files.filter((f: string) => options.math || !f.startsWith('math'));
  for (const name of files) {
    let bytes = new Uint8Array();
    if (name.endsWith('.json') || name.endsWith('.npz')) {
      bytes = await get(new URL(name, options.modelURL).href);
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
        .map(n => n.toString(16).padStart(2, '0')).join('');
      if (modelManifest.sha256[name] !== hash) throw new Error(`Model checksum mismatch: ${name}`);
    }
    py.FS.writeFile(`/models/${name}`, bytes);
  }
  const required = ['det.onnx', 'rec.onnx', 'order.onnx', 'orient.onnx', 'script.onnx',
    'rec_cjk.onnx', 'rec_rtl.onnx', 'rec_world.onnx', 'meta.json', 'lm.npz', 'lm_cjk.npz', 'lm_world.npz'];
  if (options.math) required.push('mathcls.onnx', 'math_enc.onnx', 'math_dec_init.onnx', 'math_dec_step.onnx', 'math_meta.json');
  for (const name of required) if (!files.includes(name)) throw new Error(`Model manifest lacks ${name}`);
  progress('Loading PDFium and ONNX models');
  const pdfium = await createPdfium(new URL('pdfium.wasm', runtimeURL).href);
  inferenceWorker = new Worker(new URL('./inference.worker.js', import.meta.url), { type: 'module' });
  const metadata = await new Promise<{ inputs: Record<string, string[]>; outputs: Record<string, string[]> }>((resolve, reject) => {
    inferenceWorker.onerror = e => reject(new Error(e.message));
    inferenceWorker.onmessage = ({ data }) => {
      if (data.kind === 'progress') { progress(data.message); return; }
      if (data.kind === 'ready') resolve(data);
      else reject(new Error(data.error));
    };
    inferenceWorker.postMessage({ kind: 'init', backend: options.backend, runtimeURL: new URL('ort/', runtimeURL).href,
      modelURL: options.modelURL, sha256: modelManifest.sha256, models: files.filter(f => f.endsWith('.onnx')) });
  });
  inference = new InferenceClient(inferenceWorker, options.inferenceTimeoutMs, options.responseBytes, progress);
  // Python yields at inference calls, allowing ordinary worker messages to
  // resolve the promise. No shared memory or synchronous waits are needed.
  py.registerJsModule('indra_bridge', {
    pdfium, input_names: new Map(Object.entries(metadata.inputs)),
    output_names: new Map(Object.entries(metadata.outputs)),
    inference(model: string, feed: unknown, outputs: unknown) {
      return inference.run(model, feed, outputs);
    },
  });
  py.runPython("import sys; sys.path.insert(0, '/app')");
  const entry = py.pyimport('browser_entry');
  try {
    entry.configure(JSON.stringify({ mode: options.mode ?? 'auto', dpi: options.dpi ?? 200,
      pdf_order: options.pdfOrder ?? true, image_ocr: options.imageOcr ?? true,
      furniture: options.furniture ?? false, math: options.math ?? false }));
  } finally { entry.destroy(); }
  return { upstream: manifest.upstream, models: modelManifest.revision };
}

async function handle(data: any) {
  try {
    let result;
    if (data.kind === 'init') result = await init(data.options);
    else if (data.kind === 'convert') {
      const path = `/input-${data.id}`; // content sniffing, never trust a file extension
      py.FS.writeFile(path, new Uint8Array(data.bytes));
      const entry = py.pyimport('browser_entry');
      try { result = JSON.parse(await entry.convert(path, JSON.stringify(data.options))); }
      finally { entry.destroy(); py.FS.unlink(path); }
    } else if (data.kind === 'test') {
      // Test-only dependencies never load while converting user documents.
      await py.loadPackage(['pillow', 'pytest']);
      for (const file of data.files) {
        py.FS.mkdirTree(file.path.slice(0, file.path.lastIndexOf('/')));
        py.FS.writeFile(file.path, await get(file.url));
      }
      const entry = py.pyimport('browser_entry');
      try { result = entry.run_tests(); } finally { entry.destroy(); }
    } else if (data.kind === 'dispose') {
      inference?.dispose();
      inferenceWorker?.terminate();
      self.close();
      return;
    } else throw new Error(`Unknown request: ${data.kind}`);
    self.postMessage({ kind: 'result', id: data.id, result });
  } catch (e) {
    self.postMessage({ kind: 'error', id: data.id, error: e instanceof Error ? e.message : String(e) });
  }
}
self.onmessage = ({ data }) => { sequence = sequence.then(() => handle(data)); };
