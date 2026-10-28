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
static server for production and follow the hosting requirements in README.md.

## Dependency audit scope

Audit the native development requirements with `pip-audit` alongside `npm audit`;
the npm audit alone does not cover Python or WebAssembly libraries.

Pyodide 314.0.7 bundles Pillow 12.2.0 and pytest 9.0.2 as **test-only**
dependencies of the browser parity harness. They are loaded only by `runTests`,
not by engine initialization or document conversion. The browser harness uses
synthetic, repository-controlled fixtures. The production image path uses OpenCV;
PDFs use PDFium. Audit the bundled Pyodide packages separately when updating them.
