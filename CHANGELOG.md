# Changelog

Versions refer to the `@ryancasas/indra-ocr-wasm` npm package, independently of
the upstream Indra OCR version. Release dates use UTC.

## Unreleased

### Breaking changes

- `pdfOrder` remains accepted but is ignored: reading order now follows
  upstream's layout-based ordering instead of preserving PDF content order.
- The TypeScript `Page` interface now requires the `vertical` flag.
- Regenerate runtime and model assets and copy the new browser modules together
  when upgrading. Older model manifests are incompatible with this pipeline.

### Changed

- Update the unmodified vendored Indra source and tests from 0.3.2 to 1.1.2,
  with SHA-256-pinned `v1.1.0` models and language models.
- Adapt asynchronous inference for multilingual script routing, language-model
  decoding, dark scans, larger tilts, vertical writing, picture regions, and
  right-to-left layout.
- Apply upstream fixes for rotated PDF text, visual-order right-to-left layers,
  and legacy-font layers whose codes disagree with the page's script.
- Refresh native parity references and exercise all 74 upstream tests in WASM,
  with additional Arabic, Hindi, dark-background, and tilted-image fixtures.
  The model download is now about 76 MB without math, or 96 MB with math.

### Fixed

- Keep PDF documents alive while a page is still referenced by the PDFium adapter.
- Transfer only requested ONNX outputs and expose output metadata for language
  model initialization. Verify metadata and language-model checksums at runtime.

## [0.3.0] - 2026-10-16

### Added

- Automatic WebGPU inference with per-model WASM fallback during initialization
  and execution, plus `backend: 'wasm'` to force CPU inference.
- Backend selection and recovery messages through `onProgress`.
- Math classification, encoding, and decoding always use CPU/WASM while the
  remaining OCR models can use WebGPU.
- A reproducible browser benchmark comparing WASM, WebGPU, and automatic CPU
  fallback, with startup costs, conversion timings, and native-output checks.
- Measured performance comparisons and reproduction instructions in the README.

### Fixed

- Detect an actual WebGPU adapter instead of treating the presence of the API as
  proof that acceleration is available.

## [0.2.1] - 2026-10-16

### Added

- A changelog covering the stable npm releases, included in the npm package and
  linked from the README.

### Changed

- Updated the README with npm installation and upgrade instructions, a browser
  API example using the installed asset paths, current CI results, and the
  automatic release rules.

### Fixed

- Release preparation accepts a package version already updated in the
  repository, keeping `package.json` and `package-lock.json` at 0.2.1.

## [0.2.0] - 2026-10-16

### Added

- Automatic npm publishing after Chromium, Firefox, WebKit, and native CI checks
  pass on `main`, with Conventional Commit messages determining SemVer bumps.
- npm trusted publishing with provenance, GitHub releases, and version tags.
- Tests for inference failures, timeouts, late responses, worker disposal,
  transferable tensor data, and release version decisions.
- Browser checks that verify conversion and native-output parity without
  cross-origin isolation or a controlling service worker.

### Changed

- Adapted the browser OCR, document, math, and ONNX inference paths to use
  asynchronous calls while retaining the pinned upstream algorithms and helpers.
- Replaced the shared-memory inference bridge with ordinary worker messages and
  transferable output buffers. ONNX inference continues to use one WASM thread.
- `responseBytes` now limits the total tensor bytes in an inference response
  instead of allocating a fixed shared response buffer.

### Removed

- The requirement for `SharedArrayBuffer`, cross-origin isolation, and COOP/COEP
  hosting headers. A service worker is not needed as a hosting workaround.

## [0.1.0] - 2026-10-16

### Added

- Initial stable npm package with a TypeScript API for converting PDFs and
  images entirely in browser WebAssembly workers.
- OCR and PDF text-layer extraction, reading order, layout blocks, Markdown,
  Chinese recognition, and optional LaTeX recognition.
- Pyodide, NumPy, OpenCV, PDFium, and ONNX Runtime Web adapters for Indra OCR 0.3.2.
- The `indra-ocr-assets` command to prepare self-hosted runtime files and pinned,
  checksum-verified model weights.
- An interactive conversion and test page, upstream tests running in WASM, and
  native-output parity fixtures covering 20 cases / 29 pages.
- Dependency, upstream, model, and fixture license notices.

### Requirements

- This version requires cross-origin isolation and COOP/COEP hosting headers
  for its synchronous shared-memory inference bridge. Upgrade to 0.2.0 or later
  to remove that requirement.

[0.3.0]: https://github.com/RyanCasas/indra-ocr-wasm/releases/tag/v0.3.0
[0.2.1]: https://github.com/RyanCasas/indra-ocr-wasm/releases/tag/v0.2.1
[0.2.0]: https://github.com/RyanCasas/indra-ocr-wasm/releases/tag/v0.2.0
[0.1.0]: https://github.com/RyanCasas/indra-ocr-wasm/tree/536123cd749d54d47bb043603c0b9cc22bc421cb
