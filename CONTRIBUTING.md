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

## Automated npm releases

Pushes to `main` publish automatically after the Chromium, Firefox, WebKit, and
native CI jobs all succeed. Pull requests, other branches, and failed CI runs
cannot publish. Release jobs run one at a time; an older run skips publishing
when a newer commit is already on `main`.

Use Conventional Commits for the commits that reach `main` (the PR title when
squash merging):

- `fix: ...`, `perf: ...`, and `chore(deps): ...` produce a patch release, such as `0.1.0` → `0.1.1`.
- `feat: ...` produces a minor release, such as `0.1.0` → `0.2.0`.
- `feat!: ...`, `fix(api)!: ...`, or a `BREAKING CHANGE: ...` footer produces a
  major release, such as `0.1.0` → `1.0.0`.
- Documentation, CI, test, and maintenance commits alone do not publish.

The largest change since the last reachable stable `vX.Y.Z` tag determines the
next version. The original, manually published `0.1.0` is anchored to commit
`536123cd749d54d47bb043603c0b9cc22bc421cb` until the first automated release tag.
The standard SemVer rules apply even while the package is below `1.0.0`.

CI updates `package.json` and `package-lock.json` in its checkout, publishes to
npm with provenance, then creates a GitHub release and version tag. Version bumps
are not committed back to `main`; release tags and npm contain the released
version. The repository's package version remains its development baseline.
If publishing succeeds but GitHub release creation fails, rerunning the workflow
can complete the release only if npm's recorded source commit matches that run.

Preview the next version from committed history without changing files or
publishing anything:

```bash
npm run release -- --dry-run
```

### One-time npm authentication setup

Publishing uses npm trusted publishing through GitHub OIDC; no `NPM_TOKEN` secret
is required. Configure a GitHub Actions trusted publisher in the npm settings
for `@ryancasas/indra-ocr-wasm` with owner `RyanCasas`, repository
`indra-ocr-wasm`, workflow filename **`test.yml`**, no environment name, and
permission to publish directly. The workflow grants `id-token: write` only to
its release job. See [npm's trusted publishing documentation](https://docs.npmjs.com/trusted-publishers/).

With npm 11.15 or later, an authenticated maintainer can also configure it using:

```bash
npm trust github @ryancasas/indra-ocr-wasm --repo RyanCasas/indra-ocr-wasm --file test.yml --allow-publish --yes
```

npm may require interactive account authentication to complete this command.

Do not commit model weights, built runtime assets, environment files, secrets,
customer documents, or local test reports. Contributions to the original code
are accepted under Apache-2.0; preserve the separate licenses of third-party
material and model-generated reference outputs.
