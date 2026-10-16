import { mkdir, cp, readdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

const runtime = 'public/runtime';
const modelLock = JSON.parse(await readFile('models.lock.json', 'utf8'));
const revision = modelLock.revision;
await mkdir(`${runtime}/pyodide`, { recursive: true });
for (const name of ['pyodide.mjs', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json']) {
  await cp(`node_modules/pyodide/${name}`, `${runtime}/pyodide/${name}`);
}
const lock = JSON.parse(await readFile('node_modules/pyodide/pyodide-lock.json', 'utf8'));
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
  await download(`https://cdn.jsdelivr.net/pyodide/v0.29.3/full/${pkg.file_name}`,
    `${runtime}/pyodide/${pkg.file_name}`, pkg.sha256);
}
await cp('node_modules/@embedpdf/pdfium/dist/pdfium.wasm', `${runtime}/pdfium.wasm`);
await mkdir(`${runtime}/ort`, { recursive: true });
for (const name of await readdir('node_modules/onnxruntime-web/dist')) {
  if (name.startsWith('ort-wasm-simd-threaded') && /\.(wasm|mjs)$/.test(name)) {
    await cp(`node_modules/onnxruntime-web/dist/${name}`, `${runtime}/ort/${name}`);
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
await copyPython('vendor/indra/indra_ocr', 'indra_ocr');
await copyPython('python', '');
await writeFile(`${runtime}/python/manifest.json`, JSON.stringify({
  upstream: (await readFile('vendor/indra/REVISION', 'utf8')).trim(), files: sources,
}, null, 2));
await cp('vendor/indra/LICENSE', `${runtime}/python/INDRA-LICENSE`);
await cp('node_modules/@embedpdf/pdfium/LICENSE.pdfium', `${runtime}/PDFIUM-LICENSE`);
await cp('node_modules/@embedpdf/pdfium/LICENSE', `${runtime}/EMBEDPDF-LICENSE`);
await mkdir('public/models', { recursive: true });
const files = modelLock.files;
// Weights are pinned to an immutable Hugging Face commit, never a moving tag.
for (const name of files) await download(`https://huggingface.co/datalab-to/indra-ocr/resolve/${revision}/${name}`, `public/models/${name}`, modelLock.sha256[name]);
const hashes = Object.fromEntries(await Promise.all(files.map(async name => [name,
  createHash('sha256').update(await readFile(`public/models/${name}`)).digest('hex')])));
await writeFile('public/models/manifest.json', JSON.stringify({ revision, files, sha256: hashes }, null, 2));
for (const file of ['LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md']) {
  await cp(file, `${runtime}/${file}`);
}
await cp('licenses', `${runtime}/licenses`, { recursive: true });
console.log('Self-hosted runtime and versioned model assets ready.');
