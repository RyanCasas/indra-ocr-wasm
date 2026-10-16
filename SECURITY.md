# Security policy

Security fixes are made on the default branch. Historical commits and old
releases are not maintained separately.

## Reporting a vulnerability

Use the repository's [Security tab](https://github.com/RyanCasas/indra-ocr-wasm/security)
and its **Report a vulnerability** action when private reporting is available.
If that action is unavailable, open an issue requesting a private contact method
without including exploit details, credentials, or confidential documents.

Include the affected revision, browser and operating-system versions, a minimal
synthetic reproducer, expected behavior, and observed behavior. Do not attach
customer documents or personal data. No response-time commitment is specified.

## Processing untrusted documents

OCR and PDF parsing run locally in browser workers. Keep the browser and pinned
runtime dependencies updated. Calling `dispose()` terminates pending work; use
application-level file-size and page-count limits appropriate to the deployment.
Workers isolate scheduling, but they do not eliminate memory-exhaustion risks
from very large or malformed files.

The included HTTP server is a development and test server. Use a maintained
static server for production and configure the headers documented in README.md.

## Dependency audit scope

The native development requirements pin Pillow 12.3.0 and pytest 9.1.1, replacing
versions with published security advisories. Audit them with `pip-audit` alongside
`npm audit`; the npm audit alone does not cover Python or WebAssembly libraries.

Pyodide 0.29.3's bundled Pillow 11.3.0 and pytest 8.3.5 remain **test-only**
dependencies of the browser parity harness. They are loaded only by `runTests`,
not by engine initialization or document conversion. The browser harness uses
synthetic, repository-controlled fixtures. Do not extend these tests to parse
untrusted files with Pillow. The production image path uses OpenCV; PDFs use
PDFium.

Known upstream advisories include Pillow
[CVE-2026-25990](https://github.com/advisories/GHSA-cfh3-3jmp-rvhc) and pytest
[CVE-2025-71176](https://github.com/advisories/GHSA-6w46-j5rx-g56g). Other Pillow
11.3.0 advisories also exist; this list is not exhaustive. The pytest advisory
concerns shared native UNIX temporary directories; browser tests use an isolated
in-memory filesystem. Keeping these packages outside the production conversion
path is a scope mitigation, not a claim that the old packages are patched.
Upgrading the WASM test packages requires compatible Pyodide builds and renewed
parity validation.
