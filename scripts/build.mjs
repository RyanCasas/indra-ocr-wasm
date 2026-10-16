import { build } from 'esbuild';
import { cp, mkdir } from 'node:fs/promises';
await build({ entryPoints: ['src/index.ts', 'src/runtime.worker.ts', 'src/inference.worker.ts'],
  bundle: true, format: 'esm', platform: 'browser', target: 'es2022', outdir: 'dist',
  sourcemap: true, conditions: ['browser'], external: ['node:*'],
});

// Keep attribution and licenses with the standalone browser distribution.
for (const file of ['LICENSE', 'NOTICE', 'THIRD_PARTY_NOTICES.md']) {
  await cp(file, `dist/${file}`);
}
await cp('licenses', 'dist/licenses', { recursive: true });
await mkdir('dist/vendor/indra', { recursive: true });
await cp('vendor/indra/LICENSE', 'dist/vendor/indra/LICENSE');
await cp('node_modules/@embedpdf/pdfium/LICENSE', 'dist/licenses/EMBEDPDF-LICENSE');
await cp('node_modules/@embedpdf/pdfium/LICENSE.pdfium', 'dist/licenses/PDFIUM-LICENSE');
