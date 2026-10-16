import { loadPyodide, type PyodideInterface } from 'pyodide';
import { createPdfium } from './pdfium';
import { receive, RESPONSE_BYTES } from './protocol';

let py: PyodideInterface;
let inferenceWorker: Worker;
let response: SharedArrayBuffer;
let timeoutMs = 120_000;
let sequence = Promise.resolve();

function progress(message: string) { self.postMessage({ kind: 'progress', message }); }
async function get(url: string): Promise<Uint8Array> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed (${res.status}): ${url}`);
  return new Uint8Array(await res.arrayBuffer());
}
async function init(options: any) {
  response = new SharedArrayBuffer(options.responseBytes ?? RESPONSE_BYTES);
  timeoutMs = options.inferenceTimeoutMs ?? timeoutMs;
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
  // JSON metadata and file presence markers: ONNX weights stay in the ORT worker.
  const modelManifest = JSON.parse(new TextDecoder().decode(await get(new URL('manifest.json', options.modelURL).href)));
  const files: string[] = modelManifest.files.filter((f: string) => options.math || !f.startsWith('math'));
  for (const name of files) py.FS.writeFile(`/models/${name}`, name.endsWith('.json')
    ? await get(new URL(name, options.modelURL).href) : new Uint8Array());
  const required = ['det.onnx', 'rec.onnx', 'order.onnx', 'orient.onnx', 'script.onnx', 'rec_cjk.onnx', 'meta.json'];
  if (options.math) required.push('mathcls.onnx', 'math_enc.onnx', 'math_dec_init.onnx', 'math_dec_step.onnx', 'math_meta.json');
  for (const name of required) if (!files.includes(name)) throw new Error(`Model manifest lacks ${name}`);
  progress('Loading PDFium and ONNX models');
  const pdfium = await createPdfium(new URL('pdfium.wasm', runtimeURL).href);
  inferenceWorker = new Worker(new URL('./inference.worker.js', import.meta.url), { type: 'module' });
  const inputs = await new Promise<Record<string, string[]>>((resolve, reject) => {
    inferenceWorker.onerror = e => reject(new Error(e.message));
    inferenceWorker.onmessage = ({ data }) => data.kind === 'ready' ? resolve(data.inputs) : reject(new Error(data.error));
    inferenceWorker.postMessage({ kind: 'init', runtimeURL: new URL('ort/', runtimeURL).href,
      modelURL: options.modelURL, sha256: modelManifest.sha256, models: files.filter(f => f.endsWith('.onnx')) });
  });
  // The runtime worker blocks, while the independent inference worker resolves
  // ORT's promises. No blocking Atomics.wait ever runs on the browser UI thread.
  py.registerJsModule('indra_bridge', {
    pdfium, input_names: new Map(Object.entries(inputs)),
    inference(model: string, feed: unknown, outputs: unknown) {
      const state = new Int32Array(response, 0, 4);
      Atomics.store(state, 0, 0);
      inferenceWorker.postMessage({ kind: 'run', model, feed, outputs, buffer: response });
      if (Atomics.wait(state, 0, 0, timeoutMs) === 'timed-out') {
        // A late response must never be mistaken for the next request's output.
        response = new SharedArrayBuffer(response.byteLength);
        throw new Error(`ONNX inference timed out after ${timeoutMs} ms`);
      }
      try { return receive(response); }
      catch (e) { self.postMessage({kind: 'stderr', message: e instanceof Error ? e.stack : String(e)}); throw e; }
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
      try { result = JSON.parse(entry.convert(path, JSON.stringify(data.options))); }
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
