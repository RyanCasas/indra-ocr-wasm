#!/usr/bin/env node
import { mkdir, cp, readdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const { values } = parseArgs({ options: {
  'out-dir': { type: 'string', default: 'public' },
  help: { type: 'boolean', short: 'h' },
} });
if (values.help) {
  console.log('Usage: indra-ocr-assets [--out-dir <directory>]\n\nPrepares runtime/ and models/ in the output directory (default: ./public).\nDownloads pinned runtime archives and model weights; see the model license\nbefore downloading or hosting: https://github.com/RyanCasas/indra-ocr-wasm/blob/main/licenses/INDRA-MODEL-LICENSE');
  process.exit(0);
}
const root = resolve(import.meta.dirname, '..');
const output = resolve(values['out-dir']);
const runtime = join(output, 'runtime');
const models = join(output, 'models');
// Resolve from this package, including when npm hoists its dependencies.
async function packageDirectory(name) {
  let directory = dirname(fileURLToPath(import.meta.resolve(name)));
  while (true) {
    try {
      const pkg = JSON.parse(await readFile(join(directory, 'package.json'), 'utf8'));
      if (pkg.name === name) return directory;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    const parent = dirname(directory);
    if (parent === directory) throw new Error(`Cannot find package directory for ${name}`);
    directory = parent;
  }
}
const pyodide = await packageDirectory('pyodide');
const pdfium = await packageDirectory('@embedpdf/pdfium');
const ort = await packageDirectory('onnxruntime-web');
const modelLock = JSON.parse(await readFile(join(root, 'models.lock.json'), 'utf8'));
const revision = modelLock.revision;
await mkdir(`${runtime}/pyodide`, { recursive: true });
for (const name of ['pyodide.mjs', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']) {
  await cp(join(pyodide, name), `${runtime}/pyodide/${name}`);
}
const lock = JSON.parse(await readFile(join(pyodide, 'pyodide-lock.json'), 'utf8'));
const pyodideVersion = JSON.parse(await readFile(join(pyodide, 'package.json'), 'utf8')).version;
const needed = new Set();
function add(name) {
  if (needed.has(name)) return;
  needed.add(name);
  for (const dep of lock.packages[name].depends) add(dep);
}
['numpy', 'opencv-python', 'pillow', 'pytest'].forEach(add);
async function download(url, dest, sha256) {
  if (!/^[a-f0-9]{64}$/.test(sha256 ?? '')) throw new Error(`Missing SHA-256 for ${dest}`);
  try {
    const existing = await readFile(dest);
    if (createHash('sha256').update(existing).digest('hex') === sha256) return;
  } catch { /* first download */ }
  console.log(`Downloading ${dest}`);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  const bytes = new Uint8Array(await res.arrayBuffer());
  if (createHash('sha256').update(bytes).digest('hex') !== sha256) throw new Error(`Checksum mismatch: ${dest}`);
  await writeFile(dest, bytes);
}
for (const name of needed) {
  const pkg = lock.packages[name];
  await download(`https://cdn.jsdelivr.net/pyodide/v${pyodideVersion}/full/${pkg.file_name}`,
    `${runtime}/pyodide/${pkg.file_name}`, pkg.sha256);
}
await cp(join(pdfium, 'dist/pdfium.wasm'), `${runtime}/pdfium.wasm`);
await mkdir(`${runtime}/ort`, { recursive: true });
for (const name of await readdir(join(ort, 'dist'))) {
  if (name.startsWith('ort-wasm-simd-threaded') && /\.(wasm|mjs)$/.test(name)) {
    await cp(join(ort, 'dist', name), `${runtime}/ort/${name}`);
  }
}
const sources = [];
async function copyPython(from, to) {
  await mkdir(`${runtime}/python/${to}`, { recursive: true });
  for (const file of await readdir(from, { withFileTypes: true })) {
    if (file.isDirectory() && file.name !== '__pycache__') await copyPython(join(from, file.name), join(to, file.name));
    else if (file.isFile() && file.name.endsWith('.py')) {
      const name = join(to, file.name);
      await cp(join(from, file.name), `${runtime}/python/${name}`);
      sources.push(name);
    }
  }
}
await copyPython(join(root, 'vendor/indra/indra_ocr'), 'indra_ocr');
await copyPython(join(root, 'python'), '');
await writeFile(`${runtime}/python/manifest.json`, JSON.stringify({
  upstream: (await readFile(join(root, 'vendor/indra/REVISION'), 'utf8')).trim(), files: sources,
}, null, 2));
await cp(join(root, 'vendor/indra/LICENSE'), `${runtime}/python/INDRA-LICENSE`);
await cp(join(pdfium, 'LICENSE.pdfium'), `${runtime}/PDFIUM-LICENSE`);
await cp(join(pdfium, 'LICENSE'), `${runtime}/EMBEDPDF-LICENSE`);
await mkdir(models, { recursive: true });
const files = modelLock.files;
// Weights are pinned to an immutable Hugging Face commit, never a moving tag.
for (const name of files) await download(`https://huggingface.co/datalab-to/indra-ocr/resolve/${revision}/${name}`, join(models, name), modelLock.sha256[name]);
const hashes = Object.fromEntries(await Promise.all(files.map(async name => [name,
  createHash('sha256').update(await readFile(join(models, name))).digest('hex')])));
await writeFile(join(models, 'manifest.json'), JSON.stringify({ revision, files, sha256: hashes }, null, 2));
for (const file of ['LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md']) {
  await cp(join(root, file), `${runtime}/${file}`);
}
await cp(join(root, 'licenses'), `${runtime}/licenses`, { recursive: true });
console.log('Self-hosted runtime and versioned model assets ready.');
