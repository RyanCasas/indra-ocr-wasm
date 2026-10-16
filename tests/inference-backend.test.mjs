import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
const { outputFiles } = await build({ entryPoints: ['src/inference-backend.ts'], bundle: true,
  write: false, format: 'esm', platform: 'node' });
const { InferenceBackend } = await import('data:text/javascript;base64,' + Buffer.from(outputFiles[0].contents).toString('base64'));

for (const gpu of [false, true]) {
  test(`successful ${gpu ? 'GPU' : 'CPU'} session is reused`, async () => {
    const calls = [];
    const session = { release: async () => {} };
    const backend = new InferenceBackend(async enabled => { calls.push(enabled); return session; }, gpu, () => {});
    assert.equal(await backend.load(), session);
    assert.equal(await backend.run(async s => s), session);
    assert.deepEqual(calls, [gpu]);
  });
}

test('GPU initialization failure falls back to WASM', async () => {
  const calls = [];
  const cpu = { release: async () => {} };
  const backend = new InferenceBackend(async gpu => {
    calls.push(gpu);
    if (gpu) throw new Error('adapter unavailable / unsupported graph');
    return cpu;
  }, true, () => {});
  assert.equal(await backend.load(), cpu);
  assert.deepEqual(calls, [true, false]);
});

test('device loss retries the same operation once on CPU and stays there', async () => {
  const calls = [];
  const gpu = { release: async () => { throw new Error('lost device'); } };
  const cpu = { release: async () => {} };
  const backend = new InferenceBackend(async enabled => { calls.push(enabled); return enabled ? gpu : cpu; }, true, () => {});
  const seen = [];
  const operation = async session => { seen.push(session); if (session === gpu) throw new Error('device lost'); return 42; };
  assert.equal(await backend.run(operation), 42);
  assert.equal(await backend.run(operation), 42);
  assert.deepEqual(seen, [gpu, cpu, cpu]);
  assert.deepEqual(calls, [true, false]);
});

test('CPU inference failures propagate without retries', async () => {
  let runs = 0;
  const backend = new InferenceBackend(async () => ({ release: async () => {} }), false, () => {});
  await assert.rejects(backend.run(async () => { runs++; throw new Error('invalid feed'); }), /invalid feed/);
  assert.equal(runs, 1);
});

test('failure in the CPU retry propagates without looping', async () => {
  const created = [], executed = [];
  const backend = new InferenceBackend(async gpu => {
    created.push(gpu); return { gpu, release: async () => {} };
  }, true, () => {});
  await assert.rejects(backend.run(async session => {
    executed.push(session.gpu); throw new Error(session.gpu ? 'device lost' : 'CPU failed');
  }), /CPU failed/);
  assert.deepEqual(created, [true, false]);
  assert.deepEqual(executed, [true, false]);
});
