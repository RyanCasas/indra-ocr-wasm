# Test fixture provenance

All PDF, PNG, and TIFF input files in this directory are synthetic documents
created by `scripts/fixtures.py`. Their text is deliberately multilingual and
must not be translated when changing the project's documentation.

- Input documents and images: Copyright 2026 Ryan Casas, Apache-2.0, with the
  embedded font notices in [the DejaVu license](../../licenses/DEJAVU-LICENSE).
- `golden.json`: model-generated reference OCR results from the pinned Indra
  models, distributed under the [Modified OpenRAIL-M license](../../licenses/INDRA-MODEL-LICENSE).
  That license's use and redistribution conditions apply to these outputs.
- `pdfium.json`: character geometry and text extracted directly from the
  synthetic PDFs by PDFium, without model inference; Apache-2.0.

The JSON files record the upstream code revision, native dependency versions,
and model execution coverage where applicable. The generated fixtures contain
no customer data. `locked.pdf` is intentionally encrypted with the public test
password `pw` (owner password: `owner`).

The publisher of the pinned models, their license, revision, and attribution
are identified in [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md).
