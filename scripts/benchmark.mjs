/** Reproducible, sequential browser benchmark; never labels a CPU fallback as GPU. */
import { chromium } from 'playwright';
import { cpus, platform, release } from 'node:os';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { serve } from './serve.mjs';

const { values } = parseArgs({ options: {
  iterations: { type: 'string', default: '5' },
  startups: { type: 'string', default: '3' },
  suite: { type: 'string' },
  output: { type: 'string', default: 'test-results/benchmark.json' },
  'gpu-args': { type: 'string', default: '[]' },
} });
const iterations = Number(values.iterations), startups = Number(values.startups);
if (![iterations, startups].every(n => Number.isSafeInteger(n) && n > 0)) {
  throw new Error('iterations and startups must be positive integers');
}
const gpuArgs = JSON.parse(values['gpu-args']);
if (!Array.isArray(gpuArgs) || gpuArgs.some(arg => typeof arg !== 'string')) {
  throw new Error('gpu-args must be a JSON array of Chromium arguments');
}
const pkg = JSON.parse(await readFile(new URL('../package.json', import.meta.url)));
const variants = [
  { name: 'wasm', backend: 'wasm', args: gpuArgs },
  { name: 'auto-webgpu', backend: 'auto', args: gpuArgs, requireGpu: true },
  { name: 'auto-no-webgpu', backend: 'auto', args: gpuArgs, disableGpu: true },
];
const allSuites = [
  { name: 'auto', files: ['scan.png', 'chinese.png', 'pages.tiff', 'digital.pdf', 'hybrid.pdf'] },
  { name: 'ocr', files: ['digital.pdf'] },
  { name: 'math', files: ['formula.png'] },
];
if (values.suite && !allSuites.some(s => s.name === values.suite)) throw new Error('suite must be auto, ocr or math');
const suites = allSuites.filter(s => !values.suite || s.name === values.suite);
const report = {
  schemaVersion: 1, date: new Date().toISOString(), packageVersion: pkg.version,
  environment: { os: `${platform()} ${release()}`, cpu: cpus()[0].model, logicalCpus: cpus().length,
    node: process.version, dependencies: pkg.dependencies },
  methodology: { iterations, startups, warmupsPerCase: 1,
    timing: 'performance.now() around createIndra / convert; input fetched before timing',
    serving: 'localhost, Cache-Control: no-store; no COOP/COEP; no external requests',
    scheduling: 'sequential; variant order rotated between suites; new engine for each startup',
    fallbackSimulation: 'navigator.gpu set to undefined in inference worker before module evaluation',
    correctness: 'Every conversion compared with native golden outputs using unchanged parity tolerances' },
  variants: [], valid: true,
};
const browsers = [], servers = [];
// Emit one diagnostic per model on its first actual WebGPU compute dispatch.
// This runs in every variant; subsequent dispatches only check a Set.
const gpuInstrumentation = `
let benchmarkModel = 'initialization';
const benchmarkSeen = new Set();
self.addEventListener('message', ({data}) => { if (data.kind === 'run') benchmarkModel = data.model; });
if (typeof GPUComputePassEncoder !== 'undefined') {
  for (const method of ['dispatchWorkgroups', 'dispatchWorkgroupsIndirect']) {
    const original = GPUComputePassEncoder.prototype[method];
    GPUComputePassEncoder.prototype[method] = function(...args) {
      const result = Reflect.apply(original, this, args);
      if (!benchmarkSeen.has(benchmarkModel)) {
        benchmarkSeen.add(benchmarkModel);
        self.postMessage({kind: 'progress', message: 'Benchmark GPU compute: ' + benchmarkModel});
      }
      return result;
    };
  }
}
`;
const median = samples => { const sorted = [...samples].sort((a,b) => a-b); const i = Math.floor(sorted.length/2);
  return sorted.length % 2 ? sorted[i] : (sorted[i-1]+sorted[i])/2; };
const stats = samples => ({ medianMs: median(samples), minMs: Math.min(...samples), maxMs: Math.max(...samples) });

try {
  for (const variant of variants) {
    const server = await serve(0, { transform: (path, bytes) => {
      if (path !== '/dist/inference.worker.js') return bytes;
      const disable = variant.disableGpu ? "Object.defineProperty(navigator, 'gpu', { value: undefined });\n" : '';
      return Buffer.concat([Buffer.from(disable + gpuInstrumentation), bytes]);
    } });
    servers.push(server);
    const origin = `http://localhost:${server.address().port}`;
    const browser = await chromium.launch({ headless: true, args: variant.args });
    browsers.push(browser);
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.context().route('**/*', async route => {
      const url = route.request().url();
      if (!url.startsWith(origin + '/') && !url.startsWith('blob:')) {
        errors.push(`Unexpected external request: ${url}`); return route.abort();
      }
      return route.continue();
    });
    await page.goto(origin + '/tests/browser.html');
    const environment = await page.evaluate(async () => {
      const adapter = await navigator.gpu?.requestAdapter();
      return { userAgent: navigator.userAgent, crossOriginIsolated,
        sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
        adapter: adapter ? Object.fromEntries(['vendor','architecture','device','description','isFallbackAdapter']
          .map(key => [key, adapter.info[key]])) : null };
    });
    const result = { name: variant.name, backend: variant.backend, chromium: browser.version(),
      args: variant.args, inferenceGpuDisabled: !!variant.disableGpu, environment, suites: [], errors };
    report.variants.push(result);
    variant.page = page; variant.result = result;
    if (variant.requireGpu && !environment.adapter) {
      result.skipped = 'No WebGPU adapter. Pass --gpu-args for the GPU configuration you want to measure.';
      console.log(`${variant.name}: SKIPPED (no adapter)`);
    }
  }
  for (let index = 0; index < suites.length; index++) {
    const suite = suites[index];
    // Rotate configurations so one backend is not always measured first.
    const ordered = variants.slice(index).concat(variants.slice(0,index));
    for (const variant of ordered) {
      if (variant.result.skipped) continue;
      console.log(`${variant.name}/${suite.name}: running`);
      const result = await variant.page.evaluate(async ({ suiteName, files, backend, iterations, startups }) => {
        const { createIndra } = await import('/dist/index.js');
        const { compare } = await import('/tests/compare.mjs');
        const golden = await (await fetch('/tests/fixtures/golden.json')).json();
        const suite = golden.suites.find(s => s.name === suiteName);
        const cases = await Promise.all(files.map(async file => {
          const reference = suite.cases.find(c => c.file === file);
          return { reference, bytes: await (await fetch('/tests/fixtures/' + file)).arrayBuffer(),
            result: { file, pages: reference.pages.length, samplesMs: [], pageTimings: [], differences: [],
              maxCoordinateDelta: 0, maxConfidenceDelta: 0 } };
        }));
        const initializationMs = [], progress = [];
        for (let startup = 0; startup < startups; startup++) {
          let engine;
          const start = performance.now();
          try {
            engine = await createIndra({ ...suite.options, backend, onProgress: message => progress.push({ startup, message }) });
            initializationMs.push(performance.now() - start);
            if (startup) continue;
            // One warmup for each document, recorded but excluded from the median.
            for (let sample = -1; sample < iterations; sample++) {
              for (const { reference, bytes, result } of cases) {
                const t = performance.now();
                const pages = await engine.convert(bytes, reference.options);
                const elapsed = performance.now() - t;
                if (sample < 0) result.warmupMs = elapsed;
                else { result.samplesMs.push(elapsed); result.pageTimings.push(pages.map(p => p.timings)); }
                const { differences, metrics } = compare(pages, reference.pages);
                result.maxCoordinateDelta = Math.max(result.maxCoordinateDelta, metrics.maxCoordinateDelta);
                result.maxConfidenceDelta = Math.max(result.maxConfidenceDelta, metrics.maxConfidenceDelta);
                if (differences.length) result.differences.push({ sample, count: differences.length, first: differences.slice(0,5) });
                if (pages.some(p => p.source === 'error')) throw new Error('Conversion returned an error page: ' + JSON.stringify(pages));
              }
            }
          } finally { engine?.dispose(); }
        }
        return { name: suiteName, options: suite.options, initializationMs, progress, cases: cases.map(c => c.result) };
      }, { suiteName: suite.name, files: suite.files, backend: variant.backend, iterations, startups });
      result.initialization = stats(result.initializationMs);
      result.gpuComputeModels = [...new Set(result.progress.filter(p => p.message.startsWith('Benchmark GPU compute: '))
        .map(p => p.message.slice('Benchmark GPU compute: '.length)).filter(name => name !== 'initialization'))];
      if (suite.name === 'math') {
        const mathModels = ['mathcls.onnx', 'math_enc.onnx', 'math_dec_init.onnx', 'math_dec_step.onnx'];
        if (result.gpuComputeModels.some(name => name.startsWith('math'))) report.valid = false;
        for (const model of mathModels) {
          if (result.progress.filter(p => p.message === `${model}: using CPU/WASM for math`).length !== startups) report.valid = false;
        }
      }
      if (variant.requireGpu && !result.gpuComputeModels.length) report.valid = false;
      if (variant.disableGpu && result.progress.filter(p => p.message.includes('adapter unavailable; using WASM')).length !== startups) report.valid = false;
      if (!variant.requireGpu && result.gpuComputeModels.length) report.valid = false;
      for (const c of result.cases) {
        Object.assign(c, stats(c.samplesMs));
        if (c.differences.length) report.valid = false;
        console.log(`  ${c.file}: ${c.medianMs.toFixed(1)} ms (${c.differences.length} parity failures)`);
      }
      console.log(`  GPU compute models: ${result.gpuComputeModels.join(', ') || 'none'}`);
      variant.result.suites.push(result);
    }
  }
  if (report.variants.some(v => v.errors.length)) report.valid = false;
} catch (error) {
  report.valid = false;
  report.error = error.stack ?? String(error);
  throw error;
} finally {
  await Promise.all(browsers.map(browser => browser.close()));
  await Promise.all(servers.map(server => new Promise(resolve => server.close(resolve))));
  const output = resolve(values.output);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, JSON.stringify(report, null, 2) + '\n');
  console.log(`Report: ${output}`);
}
if (!report.valid) process.exitCode = 1;
