<img src="assets/icon.svg" width="64" height="64" alt="">

# Indra OCR WASM

Browser WebAssembly port of Indra OCR 1.1.2. The TypeScript API converts PDFs
and images locally into text, Markdown, and JSON with lines, bounding boxes,
blocks, reading order, orientation, vertical-writing flags, and timings.

The Python pipeline runs asynchronously on CPython/Pyodide, NumPy, and OpenCV
compiled to WASM, with ONNX Runtime Web for inference and PDFium WASM for PDFs.
Users need no Python installation or OCR server.

Code and models are pinned; see [third-party notices](THIRD_PARTY_NOTICES.md)
for revisions and licenses. This port's original code is Apache-2.0. Model
weights and generated outputs use a separate
[Modified OpenRAIL-M license](licenses/INDRA-MODEL-LICENSE) with commercial,
competition, and redistribution restrictions. Review it before downloading or
hosting weights.

## Getting started

Node.js 22 or later is required to prepare the static assets.

Install the npm package and prepare assets in your app's static directory:

```bash
npm install @ryancasas/indra-ocr-wasm@latest
npx indra-ocr-assets --out-dir public
mkdir -p public/indra
cp -R node_modules/@ryancasas/indra-ocr-wasm/dist/. public/indra/
```

Serve `public/` using the [hosting requirements](#hosting-and-distribution),
then import `createIndra` from `/indra/index.js` in a browser module. TypeScript
projects can import types from `@ryancasas/indra-ocr-wasm`. The asset command
downloads runtime archives and weights separately from the npm package.

Your static directory will contain:

```text
public/
  indra/       # Browser modules, workers, type declarations, and licenses
  runtime/     # Pyodide, NumPy, OpenCV, PDFium, ONNX Runtime, and Python sources
  models/      # Pinned model weights, metadata, manifest, and model license
```

When upgrading the npm package, rerun the asset command and copy the new `dist/`
files so the browser modules and prepared runtime stay in sync.

### Run the repository demo

To run the demo and tests from source:

```bash
git clone https://github.com/RyanCasas/indra-ocr-wasm.git
cd indra-ocr-wasm
npm ci
npm run build
npm run assets
npm run dev
```

Open **http://localhost:5173/** to convert a local file or run the tests.
The asset command downloads and verifies the runtime and models; the demo
server serves the prepared files.

## Browser API

This example uses the npm installation layout above: `/indra/` for the browser
modules, `/runtime/` for the runtime, and `/models/` for the weights. The repository
demo serves the browser modules at `/dist/` instead.

```html
<input id="document" type="file" accept="application/pdf,image/*" disabled>
<pre id="output">Loading OCR runtime…</pre>

<script type="module">
  import { createIndra } from '/indra/index.js';

  const input = document.querySelector('#document');
  const output = document.querySelector('#output');

  const indra = await createIndra({
    runtimeURL: '/runtime/',
    modelURL: '/models/',
    backend: 'auto',
    mode: 'auto',
    onProgress: message => { output.textContent = message; },
  });
  input.disabled = false;
  output.textContent = 'Choose a PDF or image.';

  input.onchange = async () => {
    const file = input.files[0];
    if (!file) return;
    input.disabled = true;
    try {
      const pages = await indra.convert(file, { maxPages: 10 });
      output.textContent = pages.map(page =>
        page.source === 'error' ? page.note : (page.markdown ?? page.text)
      ).join('\n\n');
      console.log(pages); // Includes lines, blocks, coordinates, and timings.
    } catch (error) {
      output.textContent = String(error);
    } finally {
      input.disabled = false;
    }
  };

  // When closing the view: indra.dispose();
</script>
```

`convert` accepts a `File`/`Blob`, `ArrayBuffer`, or `Uint8Array`. It preserves
caller-owned buffers and returns `Promise<Page[]>` with zero-based indices, in
page order. An unreadable file rejects the promise; a failed page returns
`source: 'error'` with its message in `note`, and processing continues with the
rest of the document. `convertMany(inputs)` returns `{ pages }` or
`{ error }` for each file, preserving input order. Each instance serializes its
conversions; `dispose()` cancels pending work and releases the workers.

`createIndra` options:

- `backend: 'auto' | 'webgpu' | 'wasm'` (default: `auto`):
  - `auto`: WebGPU for non-math models, CPU/WASM for math. A GPU initialization
    or execution failure retries that model on WASM for this and subsequent calls.
  - `webgpu`: requests GPU execution for every model, including math. An
    unavailable adapter or model failure raises an error without whole-model CPU
    retry. Unsupported individual operators may still use WASM.
  - `wasm`: CPU-only inference.
  Selection and recovery appear in `onProgress`. See
  [math backend selection](#math-backend-selection) for the automatic policy's rationale.
- `mode: 'auto' | 'ocr' | 'text'` (default: `auto`).
- `dpi: 200`, `imageOcr: true`, `furniture: false`.
- `pdfOrder` is deprecated and ignored. Indra 1.1 determines reading order from
  layout, with geometric ordering for vertical writing, instead of preserving
  PDF content order.
- `math: true` enables the classifier and LaTeX recognition; default: `false`.
- `runtimeURL`, `modelURL`: relative or absolute static asset directories;
  defaults: `/runtime/` and `/models/`. Set these explicitly for apps hosted under
  a subpath.
- `onProgress(message)` and `onLog(message, stream)`.
- `responseBytes`: limit on total tensor bytes per ONNX response; default: 64 MiB.
- `inferenceTimeoutMs`: timeout per inference; default: 120,000 ms.

`convert` options: `maxPages` (0 = all pages) and `password` for encrypted PDFs.
Exported interfaces are defined in [src/index.ts](https://github.com/RyanCasas/indra-ocr-wasm/blob/main/src/index.ts).

## Hosting and distribution

Serve over HTTPS or localhost with WebAssembly SIMD and module workers.
Cross-origin isolation, COOP/COEP headers, SharedArrayBuffer, service workers,
JSPI, and WebGPU are optional. Use HTTP serving rather than `file://`.

Serve `.wasm` files as `application/wasm`; the included development server sets
this MIME type. Keep `index.js`, `runtime.worker.js`, and `inference.worker.js`
together on the application's origin. Runtime archives and model weights can
use another origin with CORS configured.

Inference uses worker messages with transferable buffers and one WASM thread.
WebGPU accelerates ONNX inference; Python preprocessing and PDF rendering remain
on WASM. Verified model bytes stay in the inference worker for CPU recovery
without another download. Apply HTTP caching to versioned assets; the library
has no custom persistent cache.

Models occupy about 96 MB, or 76 MB without math; math models load only when
`math` is enabled. The 1.0.0 runtime occupied about 116 MB uncompressed; runtime
size varies with dependency versions. This port reuses Python algorithms and
synchronous helpers, with asynchronous browser adaptations in `python/web_*.py`.

## Performance comparison (1.0.0)

Measured on **2026-10-20**, using Indra 1.1.2 and the pinned `v1.1.0` model set.
The [benchmark report](tests/validation/benchmark-1.0.0.json) records samples,
versions, revisions, browser-module hashes, and GPU dispatch evidence. These are
historical results, not measurements of the current dependency pins. Its
`packageVersion` is the development baseline; see [release rules](CONTRIBUTING.md#automated-npm-releases).

| Component | Benchmark machine / configuration |
| --- | --- |
| CPU | AMD Ryzen 7 8845HS, 8 cores / 16 threads, x86-64 |
| GPU | Integrated AMD Radeon 780M, RDNA 3; hardware adapter (`isFallbackAdapter: false`) |
| System memory | 64 GB DDR5-5600 |
| OS | Ubuntu 26.04.1 LTS, Linux 7.0.0-38-generic |
| Graphics stack | Mesa Vulkan 26.0.8-1ubuntu0.3, Vulkan loader 1.4.341.0-1 |
| Browser | Playwright Chromium 156.0.8078.4, headless, with the Vulkan flags below |
| Runtime | ONNX Runtime Web 1.30.0, Pyodide 0.29.3, PDFium 2.15.1, Node v24.21.0 |

Each value is **median milliseconds per complete document**, measured around
`convert()` after one warmup per document, with five measured repetitions.
Inputs are fetched before timing, and initialization is excluded. Cases execute
sequentially; backend order rotates between suites. All four configurations use
one WASM thread, the same browser flags, no cross-origin isolation, and no
external requests. The fallback configuration makes `navigator.gpu` unavailable
inside the inference worker before initialization.

Columns follow the [backend options](#browser-api). The harness observed compute
dispatches from all four math models in explicit WebGPU mode and none in automatic
mode, and rejects whole-model CPU fallback in explicit mode.

| Document / options | Pages | WASM (ms) | Auto + GPU (ms) | WebGPU incl. math (ms) | Auto without GPU (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Scanned PNG | 1 | 293.8 | 268.6 | 261.7 | 319.6 |
| Chinese PNG | 1 | 245.3 | 279.0 | 285.1 | 263.1 |
| Arabic PNG | 1 | 191.9 | 185.9 | 186.0 | 199.4 |
| Hindi PNG | 1 | 201.0 | 227.2 | 226.8 | 203.5 |
| Light text on dark ground | 1 | 293.2 | 264.4 | 260.6 | 290.8 |
| 12-degree tilt | 1 | 343.5 | 307.5 | 312.8 | 362.9 |
| Multipage TIFF | 3 | 712.2 | 592.0 | 597.8 | 767.5 |
| Digital PDF | 2 | 224.6 | 164.0 | 169.5 | 245.3 |
| Hybrid PDF | 1 | 189.0 | 177.9 | 181.7 | 214.1 |
| Digital PDF (`mode: 'ocr'`) | 2 | 650.2 | 581.8 | 1306.3 | 627.2 |
| Scanned PNG (`math: true`) | 1 | 333.9 | 266.4 | 276.1 | 307.0 |
| Formula PNG (`math: true`) | 1 | 463.8 | 381.2 | 538.4 | 400.6 |
| Digital PDF (`math: true`) | 2 | 310.8 | 175.7 | 183.2 | 233.3 |

Explicit GPU math was about 41% slower than automatic CPU math on the formula
fixture. These whole-document measurements cover one device, not individual
operators or a speed guarantee. Performance varies with the document, hardware,
load, and browser. Automatic and explicit GPU modes use the same providers for
non-math models; their non-math timing differences reflect run variation.
The explicit-GPU forced-OCR samples ranged from 638 to 1658 ms, with the last
two near 638 ms. One warmup did not establish steady timing for that case;
its median should not be interpreted as an inherent cost of explicit selection.

Initialization is measured separately around `createIndra()` using three fresh
engines per configuration (median milliseconds). Assets are served from localhost
with `Cache-Control: no-store`: these include local loading and verification,
not an Internet download.

| Initialization | WASM (ms) | Auto + GPU (ms) | WebGPU incl. math (ms) | Auto without GPU (ms) |
| --- | ---: | ---: | ---: | ---: |
| Default models | 3877.6 | 4039.0 | 4029.2 | 3973.1 |
| With `math: true` | 4273.8 | 4324.1 | 4486.0 | 4214.2 |

All **312 conversions / 432 pages**, including warmups, passed the
[parity comparisons](#parity-verification). The harness also checks GPU dispatches,
automatic CPU math selection, and recovery from an unavailable adapter.

To reproduce from a prepared checkout:

```bash
npm run build
npm run assets
npx playwright install --with-deps chromium
npm run benchmark -- --iterations 5 --startups 3 \
  --gpu-args '["--enable-unsafe-webgpu","--use-angle=vulkan","--enable-features=Vulkan","--disable-vulkan-surface"]'
```

The Vulkan flags were needed to expose this machine's hardware adapter in
headless Chromium. The script explicitly skips GPU variants if no adapter is
available. Use `--suite math` to measure the three math-enabled cases only, or
`--output <path>` to keep another report. Default output is
`test-results/benchmark.json` (ignored by Git).

### Math backend selection

Automatic mode keeps `mathcls.onnx`, `math_enc.onnx`, `math_dec_init.onnx`, and
`math_dec_step.onnx` on CPU/WASM. To request GPU math, use:

```js
const indra = await createIndra({ backend: 'webgpu', math: true });
```

The [math decoder](python/web_math.py) generates tokens sequentially. Each step
returns logits and attention caches to Python on the CPU, which selects the
next token and sends the state into the next inference call. GPU execution
therefore includes repeated CPU/GPU transfers and synchronization. This is an
implementation-based explanation of the overhead; the benchmark measures whole
documents and does not attribute latency to individual transfers or kernels.

The formula result supports CPU math as the automatic default on this device;
other hardware or a decoder that keeps state on the GPU could change the tradeoff.

## Parity verification

The **74 original tests** are copied without modifications into
[vendor/indra/tests](vendor/indra/tests). `npm test` checks their hashes and those
of the upstream code, as well as tensor transport, including 64-bit integers,
scalars, response size limits, inference errors, and timeouts. It also tests
automatic SemVer decisions and release guards using temporary Git repositories.

The test button runs `pytest` **inside the production WASM worker**:

- 73 original tests pass in WASM.
- 1 original test is skipped by its existing `importorskip`: it uses pikepdf to
  *create* an encrypted PDF. Its behavior is also checked using a real encrypted
  PDF generated natively, with missing, incorrect, and correct passwords.
- 5 additional tests check passwords and PDFium character geometry against native
  results, including rotation, crop boxes, and invisible text.

In addition, [golden.json](tests/fixtures/golden.json) contains outputs from
**unmodified native Indra** for 24 cases / 33 pages: PNG, Chinese, Arabic, Hindi,
dark backgrounds, 12-degree tilt, multipage TIFF,
digital PDFs, forced OCR, hybrid documents, HTML tables, encrypted PDFs, rotation,
skew, cropping, invisible text, page limits, model-based reading order, and LaTeX
formulas. The generator verifies that the CJK, right-to-left, and world recognizers
and all four math models execute, including the decoder with cached state.

Text, Markdown/HTML, labels, order, source, and notes are compared exactly.
Bounding boxes allow a difference of 0.11 pixels and confidence scores allow
0.0002 to account for floating-point operations across backends. Timings are
validated but are not compared between native CPU and WASM. Reports also record
the maximum numeric differences and whether each case matches exactly.

These tests establish parity for the checked cases, **not a universal guarantee
of bit-for-bit identity** for every document. Indra's recognition limitations
still apply. The CLI, HTTP viewer, Python processes, and operating-system Hugging
Face cache are outside the web API; JavaScript handles asset loading. The
original cache tests use their original mocks and do not test a persistent
browser cache.

### Running tests

Use [Contributing](CONTRIBUTING.md#validation) for setup, browser validation,
native tests, and fixture regeneration. The browser runner uses the interactive
test HTML, checks operation without isolation or a service worker, blocks external
requests, and checks concurrent conversion, invalid-input recovery, buffer
ownership, and disposal. Reports go to `test-results/browser.json` and CI artifacts.
CI covers Chromium, Firefox, WebKit, and native upstream tests;
[tests/validation](tests/validation) contains historical reports.

## Project guidance

- [Changelog](CHANGELOG.md): npm release history, independent of Indra versions.
- [Contributing](CONTRIBUTING.md): validation, fixture regeneration, release rules,
  and trusted publisher setup.
- [Security](SECURITY.md): vulnerability reporting and dependency audit scope.
- [Third-party notices](THIRD_PARTY_NOTICES.md): source and model pins, licenses,
  and fixture provenance. [NOTICE](NOTICE) records copyright and attribution.

This independent project is not affiliated with or endorsed by Datalab.
