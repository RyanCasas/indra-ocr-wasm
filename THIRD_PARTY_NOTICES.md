# Third-party notices

The Apache-2.0 license for this project's original code does not replace the
licenses of its dependencies, vendored source, model weights, or reference outputs.
Retain these notices when redistributing the project or its prepared assets.

## Indra source code

- Project: [datalab-to/indra](https://github.com/datalab-to/indra).
- Revision: `3d773aeedc5d79d1d0a2a04007a9075cd71a59f4` (Indra OCR 0.3.2).
- Location: `vendor/indra/indra_ocr/` and `vendor/indra/tests/`, copied unchanged.
- License: [Apache-2.0](vendor/indra/LICENSE).

## Indra models and reference outputs

- Publisher: [Datalab](https://huggingface.co/datalab-to/indra-ocr).
- Revision: `ed345c7f158eddbc7dee0c6a7269afb75a94f7e8` (`v3.1.1`).
- License: [AI PUBS OPEN RAIL-M LICENSE (MODIFIED)](licenses/INDRA-MODEL-LICENSE).
- [Original license at the pinned revision](https://huggingface.co/datalab-to/indra-ocr/blob/ed345c7f158eddbc7dee0c6a7269afb75a94f7e8/LICENSE).

Weights are not committed to this repository. `npm run assets` downloads the
unmodified weights and their license; `models.lock.json` records their hashes.
This repository does not modify or relicense the weights.

The model license includes use, commercial, competition, attribution, and
redistribution conditions. Paragraph 8 also addresses outputs and share-alike
licensing. Model-generated OCR reference results in `tests/fixtures/golden.json`
are distributed under that license. These conditions are separate from the
Apache-2.0 license on the browser implementation. Read the full license before
downloading, using, or hosting the models and before redistributing their outputs.

## Browser runtime

- [Pyodide 0.29.3](https://github.com/pyodide/pyodide/tree/72e3c78d53a32a76e0aca7443ad24e5cae1042d3):
  [MPL-2.0](licenses/PYODIDE-LICENSE). Its unmodified source is available at the
  linked revision. The Python, NumPy, OpenCV, Pillow, and pytest distributions
  downloaded for Pyodide retain their own license terms and packaged notices.
- [ONNX Runtime Web 1.30.0](https://github.com/microsoft/onnxruntime/tree/f2c39fe2f838cf35ce7da92824f5a5e3ee6e88a7):
  [MIT](licenses/ONNXRUNTIME-LICENSE), Copyright Microsoft Corporation. The
  [upstream third-party notices](licenses/ONNXRUNTIME-NOTICES) are also included.
- [EmbedPDF PDFium 2.15.1](https://www.npmjs.com/package/@embedpdf/pdfium):
  the wrapper's MIT license and PDFium's bundled notices are retained from the
  installed package as `EMBEDPDF-LICENSE` and `PDFIUM-LICENSE` in prepared runtime
  and distribution directories. These files include the upstream package's
  additional Apache-2.0 text.

`package-lock.json` fixes the npm dependency graph and archive integrity hashes.
The Pyodide lockfile fixes its package archives and hashes. Building and preparing
assets copies this project's notices and the runtime license files alongside the
redistributable code and binaries; package archives retain their embedded notices.

## Synthetic test fixtures and fonts

The input documents and images in `tests/fixtures/` are synthetic examples
created by `scripts/fixtures.py`. They are not customer documents or extracts
from third-party publications. The encrypted PDF uses deliberately public test
passwords (`pw` and `owner`). These are fixture values, not credentials.

PDF fixtures embed subsets of DejaVu Sans. The full upstream
[DejaVu font license](licenses/DEJAVU-LICENSE) includes the Bitstream and Arev
copyright and permission notices. Noto Sans CJK is used to render the Chinese
raster fixture; no Noto font file is bundled. Regenerating fixtures requires the
fonts installed on the developer's system. Model-generated OCR outputs have the
separate license described above; see [the fixture notes](tests/fixtures/README.md).
