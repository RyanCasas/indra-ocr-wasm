<img src="assets/icon.svg" width="64" height="64" alt="">

# Indra OCR WASM

Browser WebAssembly port of Indra OCR 1.1.2, with no OCR server.
A TypeScript API converts PDFs and images into text, Markdown, and JSON with lines,
bounding boxes, blocks, reading order, orientation, vertical-writing flags, and timings.

Install [@ryancasas/indra-ocr-wasm from npm](https://www.npmjs.com/package/@ryancasas/indra-ocr-wasm).
Starting with package **0.2.0**, cross-origin isolation, COOP/COEP headers,
SharedArrayBuffer, and service workers are **not required**. Documents stay in
the browser. Starting with **0.3.0**, inference automatically prefers WebGPU, with
a CPU/WebAssembly fallback.

This is a **WebAssembly port**: it adapts the Python pipeline to asynchronous
inference and runs it with CPython/Pyodide, NumPy, and OpenCV compiled to WASM.
It adapts ONNX Runtime to the `onnxruntime-web` WebGPU/WASM backends and
pypdfium2 to actual PDFium WASM. Users do not need Python installed on their devices.

Upstream code is pinned to
[`0e96b93`](https://github.com/datalab-to/indra/tree/0e96b93c6810f17cf8352acbb4487cc9e45b66d5).
The `v1.1.0` models are pinned to Hugging Face commit
`bd02167fdf2005a19962cc15188f8496a2c87d3b`, with SHA-256 hashes in
[models.lock.json](models.lock.json).

Model weights and model-generated outputs have a separate
[Modified OpenRAIL-M license](licenses/INDRA-MODEL-LICENSE), with commercial,
competition, and redistribution restrictions. Review it before running
`npm run assets` or hosting the weights. The Apache-2.0 license applies to this
port's original code; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Getting started

Node.js 22 or later is required to prepare the static assets.

Install the npm package and prepare assets in your app's static directory:

```bash
npm install @ryancasas/indra-ocr-wasm@latest
npx indra-ocr-assets --out-dir public
mkdir -p public/indra
cp -R node_modules/@ryancasas/indra-ocr-wasm/dist/. public/indra/
```

Serve `public/` over HTTPS or localhost as described under [Hosting and distribution](#hosting-and-distribution),
then import `createIndra` from `/indra/index.js` in a browser module. Keep
`index.js`, `runtime.worker.js`, and `inference.worker.js` together in that
directory. TypeScript projects can import types from `@ryancasas/indra-ocr-wasm`.
Runtime archives and model weights are downloaded separately by the asset command;
they are not bundled in the npm tarball.

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
The `assets` command downloads and verifies the runtime and models once; the
server then serves only static files. Conversion does not send documents over
the network.

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
rest of the document, as in Indra. `convertMany(inputs)` returns `{ pages }` or
`{ error }` for each file, preserving input order. Each instance serializes its
conversions; `dispose()` cancels pending work and releases the workers.

`createIndra` options:

- `backend: 'auto' | 'wasm'` (default: `auto`). Tries WebGPU when available,
  with unsupported operators handled by WASM. If a model fails to initialize or
  execute on WebGPU, it switches to WASM and retries there; subsequent calls for
  that model stay on CPU. Use `wasm` for CPU-only execution and comparisons.
  Math models always use CPU/WASM, including with `backend: 'auto'`; see
  [why math models use CPU](#why-math-models-use-cpu).
  Backend selection and recovery are reported through `onProgress`.
- `mode: 'auto' | 'ocr' | 'text'` (default: `auto`).
- `dpi: 200`, `imageOcr: true`, `furniture: false`.
- `pdfOrder` is deprecated and ignored. Indra 1.1 determines reading order from
  layout, with geometric ordering for vertical writing, instead of preserving
  PDF content order.
- `math: true` enables the classifier and LaTeX recognition on CPU/WASM; default:
  `false`. Other OCR models can continue using WebGPU.
- `runtimeURL`, `modelURL`: relative or absolute static asset directories;
  defaults: `/runtime/` and `/models/`. Set these explicitly for apps hosted under
  a subpath.
- `onProgress(message)` and `onLog(message, stream)`.
- `responseBytes`: limit on total tensor bytes per ONNX response; default: 64 MiB.
- `inferenceTimeoutMs`: timeout per inference; default: 120,000 ms.

`convert` options: `maxPages` (0 = all pages) and `password` for encrypted PDFs.
Exported interfaces are defined in [src/index.ts](https://github.com/RyanCasas/indra-ocr-wasm/blob/main/src/index.ts).

## Hosting and distribution

Requires HTTPS or localhost, WebAssembly SIMD, and module workers. Cross-origin
isolation, COOP/COEP headers, SharedArrayBuffer, and service workers are not required.
The browser pipeline awaits inference results sent through ordinary worker
messages with transferable output buffers; CPU inference uses one WASM thread.
Existing sites do not need to enable cross-origin isolation to use the library.

Serve `.wasm` files with `Content-Type: application/wasm`. The included server
already applies this setting and serves without COOP/COEP headers. Static hosting
can be used. Assets are served from the same origin; configure CORS if you use a
different origin for runtime archives or model weights. Keep the browser modules
and worker scripts together on the application's origin. Experimental JSPI APIs
and WebGPU are not required. Opening the HTML directly through `file://` is not
a supported deployment.

The prepared runtime and dependencies occupy approximately 116 MB uncompressed;
the models, including math models and language models, occupy 96 MB (76 MB
without math). Math models are loaded only when
`math` is enabled. The initial download is larger than for a manual Rust/C++ port;
this design reuses the algorithms and their synchronous helpers. The browser's
asynchronous OCR, document, and math adaptations live in `python/web_*.py`; the
pinned upstream files remain unchanged for reference and upstream unit tests.
WebGPU accelerates ONNX inference only; Python preprocessing and PDF rendering
remain on WASM. GPU performance depends on the hardware, model and document;
small models and CPU/GPU transfers can limit gains. Measured comparisons for the
checked documents appear below. Verified model bytes are retained in the inference
worker to recreate CPU sessions without downloading
weights again after a GPU failure. Performance and memory usage depend on the
browser and document. There is no custom persistent cache; HTTP caching can be
applied to versioned assets.

## Performance comparison (0.3.0)

These historical measurements use Indra 0.3.2 and its `v3.1.1` models at
`ed345c7f158eddbc7dee0c6a7269afb75a94f7e8`. They do not describe the current
Indra 1.1.2 pipeline or its larger model set; rerun the benchmark for current timings.

Measured on **2026-10-16** using those older models and this machine:

| Component | Benchmark machine / configuration |
| --- | --- |
| CPU | AMD Ryzen 7 8845HS, 8 cores / 16 threads, x86-64 |
| GPU | Integrated AMD Radeon 780M, RDNA 3; 8 GiB reported by `amdgpu` as VRAM |
| System memory | 64 GB (2 × 32 GB) DDR5-5600 |
| OS | Ubuntu 26.04.1 LTS, Linux 7.0.0-38-generic |
| Graphics stack | `amdgpu`, Mesa Vulkan drivers 26.0.8-1ubuntu0.3, Vulkan loader 1.4.341.0-1 |
| Browser | Playwright Chromium 156.0.8078.4, headless, with the Vulkan flags below |
| ONNX Runtime Web | 1.30.0; one WASM thread, with WebGPU enabled for non-math models in automatic mode |
| Python runtime | Pyodide 0.29.3 |
| PDFium package | `@embedpdf/pdfium` 2.15.1 |
| Node.js | 24.21.0, serving the local assets and running the benchmark harness |

The GPU adapter reported
`isFallbackAdapter: false`; the benchmark observed actual WebGPU compute dispatches
from every exercised non-math model. The four math models were created with
WASM and produced no GPU compute dispatches. All three variants used the same
Chromium flags and single-threaded WASM, without cross-origin
isolation. The fallback variant made `navigator.gpu` unavailable inside the
inference worker before initialization.

Times below are **median milliseconds per complete document**, measured around
`convert()` after one warmup per document, with five measured repetitions. Input
bytes were fetched before timing; initialization is excluded. Cases execute
sequentially and backend order rotates between suites. WebGPU uses a mixture of
GPU and CPU operations where required by ONNX Runtime. Math recognition always
uses CPU/WASM. Math rows were remeasured after enforcing this policy; the other
rows retain the original non-math measurements on the same machine and date.

| Document / options | Pages | WASM (ms) | Auto + WebGPU (ms) | Auto without WebGPU (ms) | WASM / auto |
| --- | ---: | ---: | ---: | ---: | ---: |
| Scanned PNG | 1 | 245.2 | 195.9 | 247.3 | 1.25× |
| Chinese PNG | 1 | 196.4 | 145.1 | 193.9 | 1.35× |
| Multipage TIFF | 3 | 605.7 | 455.8 | 610.3 | 1.33× |
| Digital PDF, default reading order | 2 | 209.9 | 146.5 | 209.6 | 1.43× |
| Hybrid PDF | 1 | 172.7 | 139.9 | 174.6 | 1.23× |
| Digital PDF, `mode: 'ocr'` | 2 | 534.6 | 429.6 | 532.2 | 1.24× |
| Formula PNG, `math: true` (CPU math) | 1 | 442.3 | 464.2 | 430.5 | 0.95× |

On this machine, WebGPU reduced warm conversion latency by **19–30%** for the
non-math cases (1.23–1.43× speedup). With math models pinned to CPU, the formula
case was still about **5% slower** in automatic mode: its other OCR models can
use the GPU. The all-CPU paths were faster for the whole formula document.
Automatic CPU fallback stayed within about 3% of forced WASM across these cases.
These are measurements of small fixtures on one machine, not a speed guarantee
for other documents or GPUs.

Initialization is measured separately around `createIndra()` with three fresh
engines per configuration (median, milliseconds). Runtime and model assets are
served from localhost with `Cache-Control: no-store`; these figures include local
asset loading and checksum verification, not an initial download from the Internet.

| Initialization | WASM (ms) | Auto + WebGPU (ms) | Auto without WebGPU (ms) |
| --- | ---: | ---: | ---: |
| Default models | 3066.8 | 3117.1 | 3068.6 |
| With `math: true` (CPU math) | 3248.0 | 3675.1 | 3271.1 |

The first scan conversion, before warmup, took 413.1 ms on WASM, 606.1 ms on
WebGPU, and 425.2 ms with automatic CPU fallback (one observation each, excluding
initialization). GPU setup and shader compilation
can outweigh the warm-run savings for a single document. Reuse an engine for
multiple conversions when possible.

All **126 conversions / 198 pages**, including warmups, passed comparisons with
native golden outputs using the unchanged parity tolerances. Observed coordinate
and confidence deltas were zero for these cases. Timings are excluded from parity
comparisons; this does not establish universal GPU/native equivalence.

To reproduce from a prepared repository checkout:

```bash
npm run build
npm run assets
npx playwright install --with-deps chromium
npm run benchmark -- --iterations 5 --startups 3
```

The script skips the GPU variant explicitly if no adapter is available. On this
Linux machine, default headless Chromium exposed the API but returned no adapter;
the published measurements used Vulkan with these explicit flags:

```bash
npm run benchmark -- --iterations 5 --startups 3 \
  --gpu-args '["--enable-unsafe-webgpu","--use-angle=vulkan","--enable-features=Vulkan","--disable-vulkan-surface"]'
```

Raw samples, ranges, environment details, backend messages, GPU dispatch evidence,
and parity checks are written to `test-results/benchmark.json` (ignored by Git).
Set `--output <path>` to keep another run, or `--suite math` to remeasure only
mathematics. The math rows above used `--suite math` with the same repetition
counts and Vulkan flags, saved to `test-results/benchmark-math-cpu.json`. The
benchmark fails if GPU execution or CPU fallback cannot be confirmed, a math model
uses the GPU, or any output comparison fails.

### Why math models use CPU

The policy follows the measured latency of this browser pipeline. Before math
was pinned to CPU, the formula fixture took **503.3 ms with WebGPU enabled for
all models versus 421.4 ms with forced WASM**: about 19% longer. These were
whole-document medians from the original five-run comparison, excluding engine
initialization. They do not measure the four math models independently. The
table above contains the later measurements with CPU math enforced.

Math recognition also has a different execution pattern from a single OCR
inference. In [the math reader](python/web_math.py), the decoder generates tokens
sequentially: each step needs the previous token and its attention state (the
key/value caches). The current [Python/ONNX bridge](python/onnxruntime.py) returns
logits and updated caches to CPU memory after every step; Python selects the next
token, then sends the state into the next inference call. The decoding loop and
its caches do not stay resident on the GPU across calls.

With GPU execution, that design introduces repeated CPU/GPU transfers and
synchronization. For short formulas and small batches, those costs can outweigh
faster arithmetic. This is an explanation suggested by the implementation and
the end-to-end results; no per-operator profiling was collected to attribute the
slowdown to a specific transfer or kernel. Both backends passed the checked
native-output comparisons.

Consequently, `mathcls.onnx` (classification), `math_enc.onnx` (encoding),
`math_dec_init.onnx`, and `math_dec_step.onnx` (decoder initialization and token
generation) always use CPU/WASM. Keeping all four together avoids GPU transfers
between stages of the math subpipeline. Orientation, detection, script
identification, ordinary text recognition, and reading order can still use
WebGPU, even on a document containing formulas. Set `backend: 'wasm'` to run the
entire OCR pipeline on CPU.

This is a conservative default based on the tested device and workloads.
Different hardware, larger batches, or a future decoder that keeps its state on
the GPU could change the tradeoff; the current API always enforces CPU math.

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

### Automated testing

After preparing the repository with `npm ci`, `npm run build`, and `npm run assets`:

```bash
npm test
npm run typecheck
npx playwright install --with-deps chromium
npm run test:browser
# Optional: install the corresponding engine and set BROWSER=firefox or webkit.
```

The runner uses the same HTML as the interactive test, verifies that the page has
no COOP/COEP headers, cross-origin isolation, or controlling service worker, blocks
requests to external servers, and writes `test-results/browser.json`.
It also checks concurrent conversion, recovery after invalid inputs, buffer
ownership, and engine disposal.
CI runs Chromium, Firefox, WebKit, and the original native tests. All four jobs
passed for the [0.2.0 release](https://github.com/RyanCasas/indra-ocr-wasm/actions/runs/38939405940).
Each browser job uploads its report as a workflow artifact. The older reports in
[tests/validation](tests/validation) are historical snapshots; current CI artifacts
include the page's isolation state and the latest parity results.

To run the original tests natively or regenerate the reference outputs:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-native.txt
PYTHONPATH=vendor/indra .venv/bin/python -m pytest vendor/indra/tests -q
.venv/bin/python scripts/fixtures.py
# Refresh reference outputs while preserving the existing input documents:
.venv/bin/python scripts/fixtures.py --golden-only
```

Regeneration requires DejaVu Sans/Serif and Noto Sans CJK fonts at the Linux paths
specified in `scripts/fixtures.py`, plus Noto Sans Arabic and Devanagari and a
Pillow build with Raqm for shaping. Fixtures are already included; neither Python
nor these fonts are needed to run the browser tests.

## Releases

See [CHANGELOG.md](CHANGELOG.md) for release history and changes in each version.

The [GitHub Actions workflow](.github/workflows/test.yml) publishes to npm after
all browser and native checks pass on a push to `main`. Version bumps follow
Conventional Commit messages:

- `fix: ...` or `perf: ...` → patch release.
- `feat: ...` → minor release.
- A `!` before the colon, such as `feat(api)!: ...`, or a `BREAKING CHANGE: ...`
  footer → major release.

The largest change since the last stable release tag determines the bump.
Documentation and maintenance commits alone do not publish. Commit messages
without a recognized Conventional Commit prefix do not trigger a release either;
when squash merging, use the prefix in the PR title.

Publishing uses npm trusted publishing with provenance and creates a GitHub
release and `vX.Y.Z` tag. CI updates the package version in its checkout without
committing a version bump back to `main`, so the repository's `package.json`
version can differ from the latest version on npm. npm may take a few minutes to
make a successfully submitted version available.

Preview the version calculated from committed history:

```bash
git fetch origin --tags
npm run release -- --dry-run
```

See [CONTRIBUTING.md](CONTRIBUTING.md#automated-npm-releases) for the full release
rules and trusted publisher setup.

## Project structure and licenses

- `vendor/indra/`: original code and tests, revision, hashes, and license.
- `python/`: asynchronous browser pipeline, dependency adapters, and entry point.
- `src/`: TypeScript API, workers, binary transport, and PDFium bridge.
- `scripts/`: build, asset preparation, fixture generation, and test scripts.
- `tests/`: browser harness, native fixtures, and transport tests.

Indra's code and this port are licensed under Apache-2.0. Model weights and model-generated reference outputs retain
their own [Modified OpenRAIL-M license](licenses/INDRA-MODEL-LICENSE), also
downloaded as `public/models/LICENSE`.
PDFium and other dependencies retain their respective licenses. Third-party
weights and binaries are not included in Git: `npm run assets` prepares them
from pinned versions.

Contribution guidance is in [CONTRIBUTING.md](CONTRIBUTING.md). For security
reports and the scope of dependency audits, follow [SECURITY.md](SECURITY.md). Copyright and upstream attributions
are recorded in [NOTICE](NOTICE). This is an independent project and is not
affiliated with or endorsed by Datalab.
