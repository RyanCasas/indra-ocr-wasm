import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
const { outputFiles } = await build({ entryPoints:['src/protocol.ts'], bundle:true,
  write:false, format:'esm', platform:'node' });
const { publish, receive } = await import('data:text/javascript;base64,'+Buffer.from(outputFiles[0].contents).toString('base64'));

test('shared transport preserves int64, scalar and aligned float tensor bytes',()=>{
  const buffer=new SharedArrayBuffer(4096);
  const tensors=[
    {type:'int64',dims:[2],data:new BigInt64Array([2n**62n,-123n])},
    {type:'bool',dims:[3],data:new Uint8Array([1,0,1])},
    {type:'float32',dims:[],data:new Float32Array([0.125])},
    {type:'float32',dims:[0],data:new Float32Array()},
  ];
  publish(buffer,tensors);
  const actual=receive(buffer);
  tensors.forEach((ref,i)=>{
    assert.equal(actual[i].type,ref.type);assert.deepEqual(actual[i].dims,ref.dims);
    assert.deepEqual(actual[i].data,new Uint8Array(ref.data.buffer));
  });
  assert.equal(new BigInt64Array(actual[0].data.buffer)[0],2n**62n);
  // Results must own a copy: next inference must not overwrite them.
  new Uint8Array(buffer).fill(0);
  assert.equal(new Float32Array(actual[2].data.buffer)[0],0.125);
});
test('inference errors and response overflow are reported instead of deadlocking',()=>{
  const buffer=new SharedArrayBuffer(1024);
  publish(buffer,new Error('bad model'));
  assert.throws(()=>receive(buffer),/bad model/);
  publish(buffer,[{type:'uint8',dims:[2048],data:new Uint8Array(2048)}]);
  assert.throws(()=>receive(buffer),/increase responseBytes/);
});
