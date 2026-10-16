import { execFileSync } from 'node:child_process';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { Bumper } from 'conventional-recommended-bump';
import semver from 'semver';

const root = resolve(import.meta.dirname, '..');
const repository = 'RyanCasas/indra-ocr-wasm';
// The manually published 0.1.0 predates automated release tags.
const initialRelease = { version: '0.1.0', ref: '536123cd749d54d47bb043603c0b9cc22bc421cb' };

function command(cwd, file, args, inherit = false) {
  return execFileSync(file, args, { cwd, encoding: 'utf8',
    stdio: inherit ? 'inherit' : ['ignore', 'pipe', 'pipe'] })?.trim();
}

export async function planRelease(cwd = root, initial = initialRelease) {
  const git = (...args) => command(cwd, 'git', args);
  const tags = git('tag', '--merged', 'HEAD').split('\n')
    .filter(tag => tag.startsWith('v') && semver.valid(tag.slice(1)) && !semver.prerelease(tag.slice(1)))
    .sort((a, b) => semver.rcompare(a.slice(1), b.slice(1)));
  const lastTag = tags[0] ?? null;
  const lastVersion = lastTag ? lastTag.slice(1) : initial.version;
  const from = lastTag ?? initial.ref;
  // Fail on shallow/missing history rather than guessing the first version.
  git('merge-base', '--is-ancestor', from, 'HEAD');
  const recommendation = await new Bumper(cwd).loadPreset('conventionalcommits')
    .commits({ from, to: 'HEAD' }).bump();
  return {
    head: git('rev-parse', 'HEAD'), lastTag, lastVersion,
    releaseType: recommendation.releaseType ?? null,
    version: recommendation.releaseType ? semver.inc(lastVersion, recommendation.releaseType) : null,
  };
}

export function requireReleaseContext(env) {
  if (env.GITHUB_ACTIONS !== 'true' || env.GITHUB_EVENT_NAME !== 'push'
    || env.GITHUB_REF !== 'refs/heads/main' || env.GITHUB_REPOSITORY !== repository) {
    throw new Error('Publishing is only allowed from this repository\'s main-branch push workflow. Use --dry-run locally.');
  }
}

export function checkPublishedCommit(publishedHead, head, version) {
  if (publishedHead !== head) {
    throw new Error(`npm version ${version} already exists for a different or unknown commit; refusing to retag it.`);
  }
}

async function release(dryRun) {
  if (!dryRun) requireReleaseContext(process.env);
  const plan = await planRelease();
  console.log(JSON.stringify(plan, null, 2));
  if (dryRun) return;
  if (plan.head !== process.env.GITHUB_SHA) throw new Error('Checkout does not match the tested commit.');
  const latestHead = command(root, 'git', ['ls-remote', 'origin', 'refs/heads/main']).split(/\s+/)[0];
  if (latestHead !== plan.head) {
    console.log('A newer main commit exists; its successful CI run will release the accumulated changes.');
    return;
  }
  if (!plan.version) {
    console.log('No release-worthy commits since the last version.');
    return;
  }

  const pkg = JSON.parse(await readFile(resolve(root, 'package.json'), 'utf8'));
  const versions = JSON.parse(command(root, 'npm', ['view', pkg.name, 'versions', '--json']));
  if (versions.includes(plan.version)) {
    // Recover when publishing succeeded but creating the GitHub release failed.
    const publishedHead = JSON.parse(command(root, 'npm', ['view', `${pkg.name}@${plan.version}`, 'gitHead', '--json']) || 'null');
    checkPublishedCommit(publishedHead, plan.head, plan.version);
    console.log(`npm ${plan.version} is already published from this commit; completing its GitHub release.`);
  } else {
    if (versions.some(version => semver.valid(version) && !semver.prerelease(version) && semver.gte(version, plan.version))) {
      throw new Error('npm is ahead of the release tags. Reconcile existing releases before publishing.');
    }
    command(root, 'npm', ['version', plan.version, '--no-git-tag-version', '--ignore-scripts'], true);
    // Keep retry verification independent of npm's automatic gitHead detection.
    pkg.version = plan.version;
    pkg.gitHead = plan.head;
    await writeFile(resolve(root, 'package.json'), JSON.stringify(pkg, null, 2) + '\n');
    // prepack builds the exact sources that passed CI. npm authenticates with OIDC.
    command(root, 'npm', ['publish', '--access', 'public', '--provenance'], true);
  }

  const args = ['release', 'create', `v${plan.version}`, '--repo', repository,
    '--target', plan.head, '--title', `v${plan.version}`, '--generate-notes'];
  if (plan.lastTag) args.push('--notes-start-tag', plan.lastTag);
  command(root, 'gh', args, true);
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const { values } = parseArgs({ options: { 'dry-run': { type: 'boolean', default: false } } });
  await release(values['dry-run']);
}
