import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, rm, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { planRelease, requireReleaseContext, checkPublishedCommit, prepareVersion } from '../scripts/release.mjs';

async function repository(t) {
  const cwd = await mkdtemp(join(tmpdir(), 'indra-release-'));
  t.after(() => rm(cwd, { recursive: true, force: true }));
  const git = (...args) => execFileSync('git', args, { cwd, encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  git('init', '--quiet', '--initial-branch=main');
  git('config', 'user.name', 'Release test');
  git('config', 'user.email', 'release-test@example.invalid');
  const commit = message => git('commit', '--quiet', '--allow-empty', '--message', message);
  commit('Initial manually published package');
  return { cwd, git, commit, initial: { version: '0.1.0', ref: git('rev-parse', 'HEAD') } };
}

for (const [message, releaseType, version] of [
  ['fix: handle unreadable images', 'patch', '0.1.1'],
  ['perf(ocr): reduce tensor copies', 'patch', '0.1.1'],
  ['feat: run without isolation headers', 'minor', '0.2.0'],
  ['feat(api)!: change conversion results', 'major', '1.0.0'],
  ['refactor: replace the API\n\nBREAKING CHANGE: convert now returns a different shape.', 'major', '1.0.0'],
  ['docs: clarify hosting requirements', null, null],
  ['ci: add publishing workflow', null, null],
]) {
  test(`release recommendation for ${message.split('\n')[0]}`, async t => {
    const repo = await repository(t);
    repo.commit(message);
    const plan = await planRelease(repo.cwd, repo.initial);
    assert.equal(plan.lastVersion, '0.1.0');
    assert.equal(plan.releaseType, releaseType);
    assert.equal(plan.version, version);
  });
}

test('the largest change since the last release determines the bump', async t => {
  const repo = await repository(t);
  for (const message of ['fix: one bug', 'feat: a feature', 'fix!: remove an old API']) repo.commit(message);
  assert.equal((await planRelease(repo.cwd, repo.initial)).version, '1.0.0');
});

test('reachable stable tags determine the base, with no repeated release at the same commit', async t => {
  const repo = await repository(t);
  repo.commit('feat: old feature');
  repo.git('tag', 'v0.2.0');
  repo.git('tag', 'v0.3.0-beta.1');
  const released = await planRelease(repo.cwd, repo.initial);
  assert.equal(released.lastTag, 'v0.2.0');
  assert.equal(released.version, null);
  repo.commit('fix: a later bug');
  const next = await planRelease(repo.cwd, repo.initial);
  assert.equal(next.version, '0.2.1');
});

test('tags on unmerged branches cannot change the published version', async t => {
  const repo = await repository(t);
  repo.git('tag', 'v0.1.0');
  repo.git('checkout', '--quiet', '-b', 'unmerged');
  repo.commit('feat!: unrelated work');
  repo.git('tag', 'v99.0.0');
  repo.git('checkout', '--quiet', 'main');
  repo.commit('fix: real change');
  assert.equal((await planRelease(repo.cwd, repo.initial)).version, '0.1.1');
});

test('missing release history fails instead of inventing a version', async t => {
  const repo = await repository(t);
  await assert.rejects(planRelease(repo.cwd, { version: '0.1.0', ref: 'missing-commit' }));
});

test('publishing requires the original repository main-branch push context', () => {
  const env = { GITHUB_ACTIONS: 'true', GITHUB_EVENT_NAME: 'push',
    GITHUB_REF: 'refs/heads/main', GITHUB_REPOSITORY: 'RyanCasas/indra-ocr-wasm' };
  assert.doesNotThrow(() => requireReleaseContext(env));
  for (const change of [{ GITHUB_ACTIONS: undefined }, { GITHUB_EVENT_NAME: 'pull_request' },
    { GITHUB_REF: 'refs/heads/feature' }, { GITHUB_REPOSITORY: 'someone/fork' }]) {
    assert.throws(() => requireReleaseContext({ ...env, ...change }), /only allowed/);
  }
});

test('a retry can reuse a published version only from the same commit', () => {
  assert.doesNotThrow(() => checkPublishedCommit('abc', 'abc', '0.1.1'));
  assert.throws(() => checkPublishedCommit('old', 'new', '0.1.1'), /refusing to retag/);
  assert.throws(() => checkPublishedCommit(null, 'new', '0.1.1'), /refusing to retag/);
});

for (const currentVersion of ['0.2.1', '0.3.0']) {
  test(`release preparation updates package and lock files from ${currentVersion} to 0.3.0`, async t => {
    const repo = await repository(t);
    await writeFile(join(repo.cwd, 'package.json'), JSON.stringify({ name: 'indra-release-test', version: currentVersion }));
    await writeFile(join(repo.cwd, 'package-lock.json'), JSON.stringify({
      name: 'indra-release-test', version: currentVersion, lockfileVersion: 3,
      packages: { '': { name: 'indra-release-test', version: currentVersion } },
    }));
    prepareVersion(repo.cwd, '0.3.0');
    const pkg = JSON.parse(await readFile(join(repo.cwd, 'package.json'), 'utf8'));
    const lock = JSON.parse(await readFile(join(repo.cwd, 'package-lock.json'), 'utf8'));
    assert.equal(pkg.version, '0.3.0');
    assert.equal(lock.version, '0.3.0');
    assert.equal(lock.packages[''].version, '0.3.0');
    assert.equal(repo.git('tag', '--list'), '');
    assert.equal(repo.git('rev-parse', 'HEAD'), repo.initial.ref);
  });
}
