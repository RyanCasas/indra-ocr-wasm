# Contributing

Read [README.md](README.md) for the API and runtime design. Before downloading
models, review their [license](licenses/INDRA-MODEL-LICENSE) and
[third-party notices](THIRD_PARTY_NOTICES.md).

## Validation

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

For Firefox or WebKit, install the engine and set `BROWSER=firefox` or
`BROWSER=webkit`. Browser reports go to the ignored `test-results/` directory.
Acceptance criteria and numeric tolerances are in
[Parity verification](README.md#parity-verification).

Run upstream tests natively with Python 3.13:

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements-native.txt
PYTHONPATH=vendor/indra .venv/bin/python -m pytest vendor/indra/tests -q
```

Regenerate fixtures only when their inputs or native references need updating:

```bash
.venv/bin/python scripts/fixtures.py
# Refresh references while preserving input documents:
.venv/bin/python scripts/fixtures.py --golden-only
```

Generation requires DejaVu Sans/Serif, Noto Sans CJK, Arabic, and Devanagari at
the paths in `scripts/fixtures.py`, and Pillow with Raqm shaping. Included fixtures
let browser tests run without Python or fonts. See
[fixture provenance](tests/fixtures/README.md) for licensing and test passwords.

## Change boundaries

Keep documentation, comments, and interface text in English; preserve multilingual
fixture text. Keep `vendor/indra/` unchanged as an upstream reference. Make browser
adaptations in `src/` and `python/`. An upstream upgrade must update the vendored
revision and integrity manifest together.

Behavior changes need a focused regression test and a PR description of validation
and numeric tolerances. Fix browser failures against the existing parity assertions
and golden outputs; do not weaken assertions or regenerate references to mask a
failure. Fixture changes must record source revision and dependency versions.

Commit source and synthetic fixtures; keep weights, built assets, environment
files, secrets, customer documents, and local reports out of Git. Original-code
contributions use Apache-2.0; preserve third-party and reference-output licenses.

## Automated npm releases

Pushes to `main` publish after Chromium, Firefox, WebKit, and native CI pass.
Release jobs serialize and skip a run if a newer commit is on `main`.

Use Conventional Commits for commits reaching `main`, or the PR title when
squash merging. The largest change since the last reachable stable `vX.Y.Z` tag
sets the bump, including below 1.0.0:

| Commit | Bump |
| --- | --- |
| `fix:`, `perf:`, `chore(deps):` | Patch |
| `feat:` | Minor |
| `!` before the colon or a `BREAKING CHANGE:` footer | Major |
| Documentation, CI, tests, other maintenance, or unrecognized prefixes | None |

Before the first automated tag, the manually published 0.1.0 baseline is commit
`536123cd749d54d47bb043603c0b9cc22bc421cb`.

CI updates `package.json` and `package-lock.json` in its checkout, publishes with
npm provenance, and creates a GitHub release and tag. Version bumps stay out of
`main`; the repository package version is a development baseline. npm availability
may lag publication by a few minutes. If GitHub release creation fails after
publishing, rerunning can finish only when npm's recorded source commit matches
the run.

Preview the version from committed history without publishing:

```bash
git fetch origin --tags
npm run release -- --dry-run
```

### One-time npm authentication setup

Publishing uses GitHub OIDC trusted publishing. In npm's settings for
`@ryancasas/indra-ocr-wasm`, configure owner `RyanCasas`, repository
`indra-ocr-wasm`, workflow **`test.yml`**, no environment name, and direct-publish
permission. Only the release job receives `id-token: write`; no `NPM_TOKEN` is
needed. See [npm trusted publishing](https://docs.npmjs.com/trusted-publishers/).

An authenticated maintainer using npm 11.15 or later can configure it with:

```bash
npm trust github @ryancasas/indra-ocr-wasm --repo RyanCasas/indra-ocr-wasm --file test.yml --allow-publish --yes
```

npm may require interactive authentication.
