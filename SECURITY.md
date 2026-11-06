# Security policy

Security fixes target the default branch; older releases have no separate maintenance.

## Reporting a vulnerability

Use **Report a vulnerability** in the repository's
[Security tab](https://github.com/RyanCasas/indra-ocr-wasm/security) when available.
Otherwise, open an issue requesting a private contact method and reserve sensitive
details for that channel.

Include the affected revision, browser and OS versions, a synthetic reproducer,
and expected and observed behavior. Exclude customer documents, personal data,
credentials, and public exploit details. No response-time commitment is specified.

## Untrusted documents

OCR and PDF parsing run in local browser workers. Keep browsers and runtime
dependencies updated, and set application-level file-size and page-count limits.
`dispose()` terminates pending work. Workers isolate scheduling but cannot prevent
memory exhaustion from large or malformed files.

Use a maintained static server for production and follow the README's
[hosting requirements](README.md#hosting-and-distribution). The included server
is for development and tests.

## Dependency audits

Run `pip-audit -r requirements-native.txt` alongside `npm audit`; npm covers
neither Python nor WASM libraries. Audit Pyodide's bundled packages separately
when updating them; its lockfile records their versions and hashes.

Pillow and pytest in the prepared Pyodide runtime serve only the `runTests`
parity harness, which uses synthetic repository fixtures. Engine initialization
and conversion leave them unloaded. Production images use OpenCV; PDFs use PDFium.
