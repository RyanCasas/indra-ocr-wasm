import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
test('vendored upstream algorithms and tests are byte-for-byte pinned',async()=>{
  const hashes=JSON.parse(await readFile('vendor/indra/integrity.json','utf8'));
  for(const [file,hash] of Object.entries(hashes)) {
    assert.equal(createHash('sha256').update(await readFile('vendor/indra/'+file)).digest('hex'),hash,file);
  }
});
