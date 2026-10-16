import { RESPONSE_BYTES, type TensorWire } from './protocol';

type Pending = {
  resolve: (tensors: TensorWire[]) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};

/** Request IDs keep late replies from a timed-out inference out of later calls. */
export class InferenceClient {
  private pending = new Map<number, Pending>();
  private nextId = 1;
  private failure?: Error;

  constructor(private worker: Worker, private timeoutMs = 120_000,
    private responseBytes = RESPONSE_BYTES, onProgress?: (message: string) => void) {
    worker.onmessage = ({ data }) => {
      if (data.kind === 'progress') { onProgress?.(data.message); return; }
      const request = this.pending.get(data.id);
      if (!request) return;
      this.pending.delete(data.id);
      clearTimeout(request.timer);
      if (data.kind === 'error') request.reject(new Error(data.error));
      else request.resolve(data.tensors);
    };
    worker.onerror = event => this.fail(new Error(event.message || 'ONNX worker failed'));
    worker.onmessageerror = () => this.fail(new Error('ONNX worker message could not be decoded'));
  }

  run(model: string, feed: unknown, outputs: unknown): Promise<TensorWire[]> {
    if (this.failure) return Promise.reject(this.failure);
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`ONNX inference timed out after ${this.timeoutMs} ms`));
      }, this.timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      try {
        this.worker.postMessage({ kind: 'run', id, model, feed, outputs, responseBytes: this.responseBytes });
      } catch (error) {
        this.pending.delete(id);
        clearTimeout(timer);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  private fail(error: Error) {
    this.failure = error;
    for (const request of this.pending.values()) {
      clearTimeout(request.timer);
      request.reject(error);
    }
    this.pending.clear();
  }

  dispose() {
    this.fail(new Error('ONNX worker disposed'));
    this.worker.terminate();
  }
}
