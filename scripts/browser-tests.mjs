/** Headless CI runner for the same harness used by the collaborative preview. */
import { chromium, firefox, webkit } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { serve } from './serve.mjs';
import { dirname } from 'node:path';
const reportFile=process.env.BROWSER_REPORT??'test-results/browser.json';
const browserType={chromium,firefox,webkit}[process.env.BROWSER??'chromium'];
if (!browserType) throw new Error('BROWSER must be chromium, firefox or webkit');
const server=await serve(0);
let browser;
try {
  browser=await browserType.launch({headless:true,args:JSON.parse(process.env.BROWSER_ARGS??'[]')});
  const page=await browser.newPage();
  const errors=[];
  page.on('pageerror',error=>errors.push(String(error)));
  // The full runtime is self-hosted: any external fetch is a test failure.
  const port=server.address().port;
  const origin=`http://localhost:${port}`;
  await page.context().route('**/*',route=>{
    const url=route.request().url();
    if (url.startsWith(origin+'/')||url.startsWith('blob:')) return route.continue();
    errors.push(`Unexpected external request: ${url}`);return route.abort();
  });
  const productionRequests=[];
  const collect=request=>productionRequests.push(request.url());
  page.on('request',collect);
  const response=await page.goto(origin+'/tests/browser.html');
  const headers=response.headers();
  if(headers['cross-origin-opener-policy']||headers['cross-origin-embedder-policy']) {
    throw new Error('Browser tests must run without COOP/COEP headers');
  }
  const isolation=await page.evaluate(()=>({crossOriginIsolated,
    sharedArrayBufferAvailable:typeof SharedArrayBuffer!=='undefined',
    serviceWorkerControlled:!!navigator.serviceWorker?.controller}));
  if(isolation.crossOriginIsolated||isolation.serviceWorkerControlled) {
    throw new Error('Browser tests must run without cross-origin isolation or a service worker');
  }
  console.log('Browser environment: '+JSON.stringify(isolation));
  const production=await page.evaluate(async()=>{
    const {createIndra}=await import('/dist/index.js');
    const engine=await createIndra();
    try {
      const bytes=await (await fetch('/tests/fixtures/scan.png')).arrayBuffer();
      const pages=await engine.convert(bytes);
      if(pages.length!==1||pages[0].source!=='ocr'||!pages[0].lines.length)throw new Error('Production OCR smoke test failed');
      return {pages:pages.length,source:pages[0].source};
    } finally {engine.dispose();}
  });
  page.off('request',collect);
  const testPackages=productionRequests.filter(url=>/\/(pillow|pytest)[-_][^/]*\.whl$/i.test(new URL(url).pathname));
  if(testPackages.length)throw new Error('Production conversion loaded test-only packages: '+testPackages.join(', '));
  production.testOnlyPackagesLoaded=false;
  await page.evaluate(()=>{void window.runTests();});
  await page.waitForFunction(()=>['passed','failed'].includes(window.testState?.status),null,{timeout:180_000});
  const result=await page.evaluate(()=>window.testState);
  await mkdir(dirname(reportFile),{recursive:true});
  await writeFile(reportFile,JSON.stringify({browser:browserType.name(),isolation,production,errors,...result},null,2));
  console.log(result.logs.map(l=>l.message).filter(s=>s.includes('passed')||s.includes('skipped')).join('\n'));
  for(const r of result.parity??[])console.log(`${r.suite}/${r.file}: ${r.pages} pages, ${r.differences.length} differences`);
  if(result.status!=='passed'||errors.length)throw new Error(result.error??errors.join('\n'));
  console.log('Browser parity and lifecycle checks passed.');
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
