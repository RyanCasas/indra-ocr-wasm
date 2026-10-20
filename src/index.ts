export interface IndraOptions {
  /** Directory produced by npm run assets (default: /runtime/). */
  runtimeURL?: string | URL;
  /** Versioned weights directory with manifest.json (default: /models/). */
  modelURL?: string | URL;
  /** auto: prefer WebGPU, keep math on CPU, and recover on WASM.
   * webgpu: request WebGPU for all models including math; fail if unavailable.
   * wasm: force CPU. Unsupported GPU operators can still use WASM. Default: auto. */
  backend?: 'auto' | 'webgpu' | 'wasm';
  mode?: 'auto' | 'ocr' | 'text';
  dpi?: number;
  /** @deprecated Upstream 1.1 always determines reading order from layout; this option is ignored. */
  pdfOrder?: boolean;
  imageOcr?: boolean;
  furniture?: boolean;
  /** Enable math recognition (default: false). Backend selection also applies to math. */
  math?: boolean;
  /** Maximum total tensor bytes per ONNX response (default: 64 MiB). */
  responseBytes?: number;
  inferenceTimeoutMs?: number;
  onProgress?: (message: string) => void;
  onLog?: (message: string, stream: 'stdout' | 'stderr') => void;
}
export interface ConvertOptions { maxPages?: number; password?: string }
export interface Line { box: number[]; text: string; conf: number }
export interface Block { label: string; bbox: number[]; text: string }
export interface Page {
  page: number;
  text: string;
  markdown: string | null;
  lines: Line[];
  blocks: Block[];
  source: 'ocr' | 'text' | 'hybrid' | 'error';
  note: string;
  rotation: number;
  skew: number;
  /** True for pages set in vertical columns; boxes remain in the input frame. */
  vertical: boolean;
  timings: Record<string, number>;
}
export type Input = Blob | ArrayBuffer | Uint8Array;
type Pending = { resolve: (result: any) => void; reject: (reason: Error) => void };

export class Indra {
  private worker: Worker;
  private pending = new Map<number, Pending>();
  private nextId = 1;
  private disposed = false;
  readonly versions: { upstream: string; models: string };

  private constructor(worker: Worker, options: IndraOptions) {
    this.worker = worker;
    this.versions = { upstream: '', models: '' };
    worker.onmessage = ({ data }) => {
      if (data.kind === 'progress') { options.onProgress?.(data.message); return; }
      if (data.kind === 'stdout' || data.kind === 'stderr') { options.onLog?.(data.message, data.kind); return; }
      const request = this.pending.get(data.id);
      if (!request) return;
      this.pending.delete(data.id);
      if (data.kind === 'error') request.reject(new Error(data.error));
      else request.resolve(data.result);
    };
    worker.onerror = e => { this.fail(new Error(e.message || 'Indra worker failed')); this.dispose(); };
    worker.onmessageerror = () => { this.fail(new Error('Indra worker message could not be decoded')); this.dispose(); };
  }

  static async create(options: IndraOptions = {}): Promise<Indra> {
    if (options.backend !== undefined && !['auto', 'webgpu', 'wasm'].includes(options.backend)) throw new TypeError('Invalid backend');
    if (options.mode !== undefined && !['auto', 'ocr', 'text'].includes(options.mode)) throw new TypeError('Invalid mode');
    if (options.dpi !== undefined && (!Number.isFinite(options.dpi) || options.dpi <= 0)) throw new TypeError('dpi must be positive');
    if (options.responseBytes !== undefined && (!Number.isSafeInteger(options.responseBytes) || options.responseBytes < 1024)) throw new TypeError('responseBytes must be an integer >= 1024');
    if (options.inferenceTimeoutMs !== undefined && (!Number.isFinite(options.inferenceTimeoutMs) || options.inferenceTimeoutMs <= 0)) throw new TypeError('inferenceTimeoutMs must be positive');
    const worker = new Worker(new URL('./runtime.worker.js', import.meta.url), { type: 'module' });
    const client = new Indra(worker, options);
    const { onProgress, onLog, runtimeURL, modelURL, ...config } = options;
    const directory = (url: string | URL) => {
      const resolved = new URL(url, globalThis.location.href);
      if (!resolved.pathname.endsWith('/')) resolved.pathname += '/';
      return resolved.href;
    };
    try {
      Object.assign(client.versions, await client.request('init', { options: { ...config,
        runtimeURL: directory(runtimeURL ?? '/runtime/'), modelURL: directory(modelURL ?? '/models/') } }));
      return client;
    } catch (e) { client.dispose(); throw e; }
  }

  /** Input bytes stay in this browser. Invalid files reject; per-page errors
   * are returned with source="error", exactly as Indra's Converter does. */
  async convert(input: Input, options: ConvertOptions = {}): Promise<Page[]> {
    if (this.disposed) throw new Error('Indra has been disposed');
    if (options.maxPages !== undefined && (!Number.isSafeInteger(options.maxPages) || options.maxPages < 0)) throw new TypeError('maxPages must be a nonnegative integer');
    if (options.password !== undefined && typeof options.password !== 'string') throw new TypeError('password must be a string');
    // Always copy buffers, so callers retain ownership (including sliced views).
    const bytes = input instanceof Blob ? await input.arrayBuffer()
      : input instanceof Uint8Array ? input.slice().buffer : input.slice(0);
    return this.request('convert', { bytes, options: {
      max_pages: options.maxPages ?? 0, password: options.password ?? null,
    } }, [bytes]);
  }

  /** Files and pages retain input order. One instance serializes conversions. */
  async convertMany(inputs: Iterable<Input>, options: ConvertOptions = {}) {
    const results: ({ pages: Page[] } | { error: Error })[] = [];
    for (const input of inputs) {
      try { results.push({ pages: await this.convert(input, options) }); }
      catch (e) { results.push({ error: e instanceof Error ? e : new Error(String(e)) }); }
    }
    return results;
  }

  /** @internal Runs unmodified upstream tests inside the production WASM worker. */
  runTests(files: { path: string; url: string }[]): Promise<number> {
    return this.request('test', { files });
  }

  /** Terminates the runtime and its nested inference worker, cancels pending work. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.worker.postMessage({ kind: 'dispose' });
    this.worker.terminate();
    this.fail(new Error('Indra has been disposed'));
  }
  private fail(error: Error) {
    for (const request of this.pending.values()) request.reject(error);
    this.pending.clear();
  }
  private request(kind: string, data: object, transfer: Transferable[] = []): Promise<any> {
    if (this.disposed) return Promise.reject(new Error('Indra has been disposed'));
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      try { this.worker.postMessage({ id, kind, ...data }, transfer); }
      catch (e) { this.pending.delete(id); reject(e); }
    });
  }
}
export const createIndra = (options?: IndraOptions) => Indra.create(options);
