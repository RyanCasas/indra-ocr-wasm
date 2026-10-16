<img src="assets/icon.svg" width="64" height="64" alt="">

# Indra OCR WASM

Indra OCR 0.3.2 running entirely in the browser, with no OCR server.
A TypeScript API converts PDFs and images into text, Markdown, and JSON with lines,
bounding boxes, blocks, reading order, orientation, and timings.

This is a **WebAssembly compatibility port**: it preserves the original Python
pipeline without modifications and runs it with CPython/Pyodide, NumPy, and OpenCV
compiled to WASM. It adapts ONNX Runtime to the `onnxruntime-web` WASM backend and
pypdfium2 to actual PDFium WASM. Users do not need Python installed on their devices.

Upstream code is pinned to
[`3d773ae`](https://github.com/datalab-to/indra/tree/3d773aeedc5d79d1d0a2a04007a9075cd71a59f4).
The `v3.1.1` models are pinned to Hugging Face commit
`ed345c7f158eddbc7dee0c6a7269afb75a94f7e8`, with SHA-256 hashes in
[models.lock.json](models.lock.json).

Model weights and model-generated outputs have a separate
[Modified OpenRAIL-M license](licenses/INDRA-MODEL-LICENSE), with commercial,
competition, and redistribution restrictions. Review it before running
`npm run assets` or hosting the weights. The Apache-2.0 license applies to this
port's original code; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Getting started

Node.js 22 or later is required to prepare the static assets.

```bash
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

Serve `dist/` and the `public/runtime/` and `public/models/` directories. The latter
two are exposed as `/runtime/` and `/models/` by the example server.

```html
<script type="module">
  import { createIndra } from '/dist/index.js';

  const indra = await createIndra({
    runtimeURL: '/runtime/',
    modelURL: '/models/',
    mode: 'auto',
    onProgress: message => console.log(message),
  });

  document.querySelector('input[type=file]').onchange = async event => {
    const pages = await indra.convert(event.target.files[0], { maxPages: 10 });
    for (const page of pages) {
      console.log(page.page, page.source, page.markdown ?? page.text);
      console.log(page.lines, page.blocks, page.rotation, page.skew, page.timings);
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

- `mode: 'auto' | 'ocr' | 'text'` (default: `auto`).
- `dpi: 200`, `pdfOrder: true`, `imageOcr: true`, `furniture: false`.
- `math: true` enables the classifier and LaTeX recognition; default: `false`.
- `runtimeURL`, `modelURL`: relative or absolute static asset directories.
- `onProgress(message)` and `onLog(message, stream)`.
- `responseBytes`: ONNX response buffer limit; default: 64 MiB.
- `inferenceTimeoutMs`: timeout per inference; default: 120,000 ms.

`convert` options: `maxPages` (0 = all pages) and `password` for encrypted PDFs.
Exported interfaces are defined in [src/index.ts](src/index.ts).

## Hosting and distribution

Requires HTTPS or localhost, WebAssembly SIMD, module workers, and cross-origin
isolation for `SharedArrayBuffer`. Send these headers with the main page:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Serve `.wasm` files with `Content-Type: application/wasm`. The included server
already applies these settings. Any static hosting service that supports these
settings can be used. Assets are served from the same origin; configure CORS and
COEP if you use a different origin. Experimental JSPI APIs and WebGPU are not
required.

The prepared runtime and dependencies occupy approximately 116 MB uncompressed;
the models, including math models, occupy 37 MB. Math models are loaded only when
`math` is enabled. The initial download is larger than for a manual Rust/C++ port;
this design preserves the algorithms and allows direct reuse of the Python tests.
Performance and memory usage depend on the browser and document. There is no
custom persistent cache; HTTP caching can be applied to versioned assets.

## Parity verification

The **27 original tests** are copied without modifications into
[vendor/indra/tests](vendor/indra/tests). `npm test` checks their hashes and those
of the upstream code, as well as tensor transport, including 64-bit integers,
scalars, errors, and memory limits.

The test button runs `pytest` **inside the production WASM worker**:

- 26 original tests pass in WASM.
- 1 original test is skipped by its existing `importorskip`: it uses pikepdf to
  *create* an encrypted PDF. Its behavior is also checked using a real encrypted
  PDF generated natively, with missing, incorrect, and correct passwords.
- 5 additional tests check passwords and PDFium character geometry against native
  results, including rotation, crop boxes, and invisible text.

In addition, [golden.json](tests/fixtures/golden.json) contains outputs from
**unmodified native Indra** for 20 cases / 29 pages: PNG, Chinese, multipage TIFF,
digital PDFs, forced OCR, hybrid documents, HTML tables, encrypted PDFs, rotation,
skew, cropping, invisible text, page limits, model-based reading order, and LaTeX
formulas. The generator verifies that the Chinese recognizer and all four math
models execute, including the decoder with cached state.

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

```bash
npm test
npm run typecheck
npx playwright install --with-deps chromium
npm run test:browser
# Optional: install the corresponding engine and set BROWSER=firefox or webkit.
```

The runner uses the same HTML as the interactive test, blocks requests to external
servers, and writes `test-results/browser.json`. It also checks concurrent
conversion, recovery after invalid inputs, buffer ownership, and engine disposal.
CI includes Chromium, Firefox, and WebKit, as well as the native tests. The local
validation reports in [tests/validation](tests/validation) cover Chromium and
Firefox. WebKit could not start in this environment because native dependencies
were missing; CI is configured to install them with `--with-deps`.

To run the original tests natively or regenerate the reference outputs:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-native.txt
PYTHONPATH=vendor/indra .venv/bin/python -m pytest vendor/indra/tests -q
.venv/bin/python scripts/fixtures.py
```

Regeneration requires DejaVu Sans/Serif and Noto Sans CJK fonts at the Linux paths
specified in `scripts/fixtures.py`. Fixtures are already included; neither Python
nor these fonts are needed to run the browser tests.

## Project structure and licenses

- `vendor/indra/`: original code and tests, revision, hashes, and license.
- `python/`: dependency adapters and browser entry point.
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
