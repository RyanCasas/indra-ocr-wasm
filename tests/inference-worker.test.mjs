import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const sessions = [];
globalThis.indraTestSessions = sessions;
const { outputFiles } = await build({ entryPoints: ['src/inference.worker.ts'], bundle: true,
  write: false, format: 'esm', platform: 'node', plugins: [{
    name: 'mock-ort', setup(build) {
      build.onResolve({ filter: /^onnxruntime-web\/webgpu$/ }, () => ({ path: 'ort', namespace: 'mock' }));
      build.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: `
        export const env = { wasm: {} };
        export class Tensor { constructor() { throw new Error('Unexpected inference during initialization test'); } }
        export const InferenceSession = { create: async (bytes, options) => {
          globalThis.indraTestSessions.push({ model: new TextDecoder().decode(bytes), options });
          return { inputNames: ['input'], release: async () => {} };
        } };
      ` }));
    },
  }] });
const models = ['det.onnx', 'rec.onnx', 'order.onnx', 'orient.onnx', 'script.onnx', 'rec_cjk.onnx',
  'mathcls.onnx', 'math_enc.onnx', 'math_dec_init.onnx', 'math_dec_step.onnx'];
const sha256 = {};
for (const model of models) sha256[model] = Buffer.from(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(model))).toString('hex');
const messages = [];
globalThis.self = { postMessage: message => messages.push(message) };
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { gpu: { requestAdapter: async () => ({}) } } });
globalThis.fetch = async url => ({ ok: true, arrayBuffer: async () => new TextEncoder().encode(new URL(url).pathname.slice(1)).buffer });
await import('data:text/javascript;base64,' + Buffer.from(outputFiles[0].contents).toString('base64'));

for (const backend of ['auto', 'wasm']) {
  test(`${backend}: math always uses CPU while other models follow the selected backend`, async () => {
    sessions.length = 0; messages.length = 0;
    await self.onmessage({ data: { kind: 'init', backend, models, sha256,
      runtimeURL: 'https://example.test/runtime/', modelURL: 'https://example.test/' } });
    assert.equal(messages.at(-1).kind, 'ready', JSON.stringify(messages.at(-1)));
    assert.equal(sessions.length, models.length);
    for (const { model, options } of sessions) {
      assert.deepEqual(options.executionProviders,
        backend === 'auto' && !model.startsWith('math') ? ['webgpu', 'wasm'] : ['wasm'], model);
    }
    assert.equal(messages.filter(m => m.message?.includes('using CPU/WASM for math')).length, 4);
  });
}
