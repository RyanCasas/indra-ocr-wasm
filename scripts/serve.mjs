import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import { pathToFileURL } from 'node:url';
const root = resolve(import.meta.dirname, '..');
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript','.mjs':'text/javascript',
  '.wasm':'application/wasm','.json':'application/json','.png':'image/png','.svg':'image/svg+xml'};
export function serve(port=5173, { transform } = {}) {
  const server=createServer(async(req,res)=>{
    res.setHeader('Cache-Control','no-store');
    try {
      const url=new URL(req.url,'http://localhost');
      const path=decodeURIComponent(url.pathname);
      const dir=/^\/(runtime|models)\//.test(path)?resolve(root,'public'):root;
      const file=resolve(dir,'.'+(path==='/'?'/tests/browser.html':path));
      const allowed=['dist','tests','vendor/indra/tests', 'public/runtime','public/models','assets']
        .some(prefix=>file.startsWith(resolve(root,prefix)+'/'));
      if (!file.startsWith(dir+'/')||!allowed) {res.writeHead(403).end();return;}
      let data=await readFile(file);
      if (transform) data=await transform(path, data);
      res.setHeader('Content-Type',mime[extname(file)]??'application/octet-stream');
      res.setHeader('Content-Length',data.length);
      res.end(req.method==='HEAD'?undefined:data);
    } catch { res.writeHead(404).end('Not found'); }
  });
  return new Promise(resolve=>server.listen(port,'0.0.0.0',()=>resolve(server)));
}
if (process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url) {
  const port=Number(process.env.PORT??5173); await serve(port);
  console.log(`Indra WASM: http://localhost:${port}/tests/browser.html`);
}
