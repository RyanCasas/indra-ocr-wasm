# Test fixture provenance

`scripts/fixtures.py` creates the synthetic PDF, PNG, and TIFF inputs. Preserve
their multilingual text. They contain no customer data. `locked.pdf` uses public
test passwords: `pw` (user) and `owner` (owner).

| Files | Provenance and license |
| --- | --- |
| PDF, PNG, TIFF | Copyright 2026 Ryan Casas, Apache-2.0; embedded fonts retain the [DejaVu license](../../licenses/DEJAVU-LICENSE). |
| `golden.json` | Model-generated OCR references under the [Modified OpenRAIL-M license](../../licenses/INDRA-MODEL-LICENSE), including its use and redistribution conditions. |
| `pdfium.json` | Text and character geometry extracted by PDFium without model inference; Apache-2.0. |

The JSON files record upstream revisions, native dependency versions, and model
execution coverage where applicable. See [third-party notices](../../THIRD_PARTY_NOTICES.md)
for model attribution and pins, and [Contributing](../../CONTRIBUTING.md#validation)
for regeneration instructions.
