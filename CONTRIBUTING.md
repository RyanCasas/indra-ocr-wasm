# Contributing

Read [README.md](README.md) for the runtime design and browser API, and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for dependency and model licenses.
Review the model license before running `npm run assets`.

Use Node.js 22 or later:

```bash
npm ci
npm run build
npm run assets
npm test
npm run typecheck
npx playwright install --with-deps chromium
npm run test:browser
```

Set `BROWSER=firefox` or `BROWSER=webkit` after installing that engine to run the
same harness there. Browser reports are written to the ignored `test-results/`
directory. Native tests and fixture regeneration are described in README.md.

Keep documentation, code comments, and interface text in English. Preserve
multilingual OCR fixtures and the unmodified upstream code and tests in
`vendor/indra/`. Make browser adaptations in `src/` and `python/`; update the
vendored revision and integrity manifest together only when upgrading upstream.

For behavior changes, include a focused regression test and describe validation
and any numeric tolerances in the pull request. Never weaken parity assertions
or regenerate golden outputs just to make a failing browser implementation pass.
Document the source revision and dependency versions when changing fixtures.

Do not commit model weights, built runtime assets, environment files, secrets,
customer documents, or local test reports. Contributions to the original code
are accepted under Apache-2.0; preserve the separate licenses of third-party
material and model-generated reference outputs.
