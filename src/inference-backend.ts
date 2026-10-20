/** A model can permanently fall back without disabling acceleration for other models. */
export class InferenceBackend<S extends { release(): Promise<void> }> {
  private session?: S;
  private accelerated = false;
  constructor(private create: (gpu: boolean) => Promise<S>, private preferGpu: boolean,
    private report: (message: string) => void, private allowCpuFallback = true) {}

  async load(): Promise<S> {
    if (this.session) return this.session;
    if (this.preferGpu) {
      try {
        this.session = await this.create(true);
        this.accelerated = true;
        this.report('WebGPU enabled (unsupported operations use WASM)');
        return this.session;
      } catch (error) {
        if (!this.allowCpuFallback) throw error;
        this.report(`WebGPU initialization failed; using WASM: ${String(error)}`);
        this.preferGpu = false;
      }
    }
    this.session = await this.create(false);
    return this.session;
  }

  async run<T>(operation: (session: S) => Promise<T>): Promise<T> {
    const session = await this.load();
    try { return await operation(session); }
    catch (error) {
      if (!this.accelerated || !this.allowCpuFallback) throw error;
      this.accelerated = false;
      this.preferGpu = false;
      this.session = undefined;
      this.report(`WebGPU inference failed; retrying with WASM: ${String(error)}`);
      try { await session.release(); } catch { /* A lost device may reject release. */ }
      return operation(await this.load());
    }
  }
}
