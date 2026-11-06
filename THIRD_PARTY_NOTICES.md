# Third-party notices

This project's original code uses Apache-2.0. Dependencies, vendored source,
weights, and reference outputs retain their licenses. Preserve these notices
when redistributing the project or prepared assets.

## Indra source code

- Project: [datalab-to/indra](https://github.com/datalab-to/indra).
- Revision: `0e96b93c6810f17cf8352acbb4487cc9e45b66d5` (Indra OCR 1.1.2).
- Location: `vendor/indra/indra_ocr/` and `vendor/indra/tests/`, copied unchanged.
- Browser adaptations: `python/web_document.py`, `python/web_pipeline.py`, and
  `python/web_math.py` change inference calls to await asynchronous results.
- License: [Apache-2.0](vendor/indra/LICENSE).

## Indra models and reference outputs

- Publisher: [Datalab](https://huggingface.co/datalab-to/indra-ocr).
- Revision: `bd02167fdf2005a19962cc15188f8496a2c87d3b` (`v1.1.0`).
- License: [AI PUBS OPEN RAIL-M LICENSE (MODIFIED)](licenses/INDRA-MODEL-LICENSE).
- [Original license at the pinned revision](https://huggingface.co/datalab-to/indra-ocr/blob/bd02167fdf2005a19962cc15188f8496a2c87d3b/LICENSE).

`npm run assets` downloads unmodified weights and their license;
[models.lock.json](models.lock.json) records SHA-256 hashes. Weights stay out of Git.

Read the full license before downloading, using, or hosting weights or
redistributing outputs. It includes use, commercial, competition, attribution,
and redistribution conditions; paragraph 8 covers outputs and share-alike
licensing. It also governs the model-generated references in
`tests/fixtures/golden.json`.

## Browser runtime

- [Pyodide 314.0.7](https://github.com/pyodide/pyodide/tree/b1e4fcc2488962f6360a97f19b9982d6fdb5d16f):
  [MPL-2.0](licenses/PYODIDE-LICENSE). Its unmodified source is available at the
  linked revision. The Python, NumPy, OpenCV, Pillow, and pytest distributions
  downloaded for Pyodide retain their own license terms and packaged notices.
- [ONNX Runtime Web 1.31.1](https://github.com/microsoft/onnxruntime/tree/6af1a932e2286d5c58166085d24c68783033edee):
  [MIT](licenses/ONNXRUNTIME-LICENSE), Copyright Microsoft Corporation. The
  [upstream third-party notices](licenses/ONNXRUNTIME-NOTICES) are also included.
- [EmbedPDF PDFium 2.15.1](https://www.npmjs.com/package/@embedpdf/pdfium):
  the wrapper's MIT license and PDFium's bundled notices are retained from the
  installed package as `EMBEDPDF-LICENSE` and `PDFIUM-LICENSE` in prepared runtime
  and distribution directories. These files include the upstream package's
  additional Apache-2.0 text.

`package-lock.json` pins npm archives; Pyodide's lockfile pins its package
archives. Build and asset preparation copy notices and licenses beside the
redistributable code and binaries. Archives retain embedded notices.

## Synthetic test fixtures and fonts

[Fixture provenance](tests/fixtures/README.md) identifies input and reference-output
licenses. The PDFs embed DejaVu Sans subsets; the
[DejaVu license](licenses/DEJAVU-LICENSE) includes Bitstream and Arev notices.
Multilingual raster fixtures use Noto Sans CJK, Arabic, and Devanagari, with no
Noto font files bundled. Regeneration uses system-installed fonts as described
in [Contributing](CONTRIBUTING.md#validation).
