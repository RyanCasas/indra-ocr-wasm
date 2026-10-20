import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const sessions = [];
globalThis.indraTestSessions = sessions;
const runs = [];
globalThis.indraTestRuns = runs;
const { outputFiles } = await build({ entryPoints: ['src/inference.worker.ts'], bundle: true,
  write: false, format: 'esm', platform: 'node', plugins: [{
    name: 'mock-ort', setup(build) {
      build.onResolve({ filter: /^onnxruntime-web\/webgpu$/ }, () => ({ path: 'ort', namespace: 'mock' }));
      build.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: `
        export const env = { wasm: {} };
        export class Tensor {
          constructor(type, data, dims) { Object.assign(this, { type, data, dims }); }
          dispose() {}
        }
        export const InferenceSession = { create: async (bytes, options) => {
          globalThis.indraTestSessions.push({ model: new TextDecoder().decode(bytes), options });
          const outputNames = ['ids', 'conf', 'lengths', 'blank', 'topv', 'topi'];
          return { inputNames: ['input'], outputNames, release: async () => {},
            run: async (feed, outputs = outputNames) => {
              globalThis.indraTestRuns.push(outputs);
              return Object.fromEntries(outputs.map(name => [name, new Tensor('float32', new Float32Array([1]), [1])]));
            } };
        } };
      ` }));
    },
  }] });
const models = ['det.onnx', 'rec.onnx', 'order.onnx', 'orient.onnx', 'script.onnx', 'rec_cjk.onnx', 'rec_rtl.onnx', 'rec_world.onnx',
  'mathcls.onnx', 'math_enc.onnx', 'math_dec_init.onnx', 'math_dec_step.onnx'];
const sha256 = {};
for (const model of models) sha256[model] = Buffer.from(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(model))).toString('hex');
const messages = [];
globalThis.self = { postMessage: message => messages.push(message) };
Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { gpu: { requestAdapter: async () => ({}) } } });
globalThis.fetch = async url => ({ ok: true, arrayBuffer: async () => new TextEncoder().encode(new URL(url).pathname.slice(1)).buffer });
await import('data:text/javascript;base64,' + Buffer.from(outputFiles[0].contents).toString('base64'));

for (const backend of ['auto', 'wasm', 'webgpu']) {
  test(`${backend}: math follows explicit backend selection and uses CPU in auto mode`, async () => {
    sessions.length = 0; messages.length = 0;
    await self.onmessage({ data: { kind: 'init', backend, models, sha256,
      runtimeURL: 'https://example.test/runtime/', modelURL: 'https://example.test/' } });
    assert.equal(messages.at(-1).kind, 'ready', JSON.stringify(messages.at(-1)));
    assert.equal(sessions.length, models.length);
    assert.deepEqual(messages.at(-1).outputs['rec.onnx'], ['ids', 'conf', 'lengths', 'blank', 'topv', 'topi']);
    for (const { model, options } of sessions) {
      assert.deepEqual(options.executionProviders,
        backend === 'webgpu' || backend === 'auto' && !model.startsWith('math') ? ['webgpu', 'wasm'] : ['wasm'], model);
    }
    assert.equal(messages.filter(m => m.message?.includes('using CPU/WASM for math')).length, backend === 'webgpu' ? 0 : 4);
  });
}

test('explicit GPU rejects an unavailable adapter while auto selects CPU', async () => {
  const requestAdapter = navigator.gpu.requestAdapter;
  navigator.gpu.requestAdapter = async () => null;
  try {
    for (const backend of ['webgpu', 'auto']) {
      sessions.length = 0; messages.length = 0;
      await self.onmessage({ data: { kind: 'init', backend, models, sha256,
        runtimeURL: 'https://example.test/runtime/', modelURL: 'https://example.test/' } });
      if (backend === 'webgpu') {
        assert.equal(sessions.length, 0);
        assert.equal(messages.at(-1).kind, 'error');
        assert.match(messages.at(-1).error, /WebGPU was requested but no adapter is available/);
      } else {
        assert.equal(messages.at(-1).kind, 'ready');
        assert.ok(sessions.every(s => s.options.executionProviders.join() === 'wasm'));
      }
    }
  } finally { navigator.gpu.requestAdapter = requestAdapter; }
});

test('recognizer requests fetch only the selected outputs in the requested order', async () => {
  messages.length = 0; runs.length = 0;
  const outputs = ['lengths', 'ids'];
  await self.onmessage({ data: { kind: 'run', id: 42, model: 'rec.onnx', outputs,
    feed: { input: { type: 'float32', dims: [1], data: new Uint8Array(new Float32Array([1]).buffer) } },
    responseBytes: 8 } });
  assert.deepEqual(runs, [outputs]);
  assert.equal(messages.at(-1).kind, 'result', JSON.stringify(messages.at(-1)));
  assert.equal(messages.at(-1).id, 42);
  assert.equal(messages.at(-1).tensors.length, outputs.length);
});
