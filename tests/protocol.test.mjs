import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
const { outputFiles } = await build({ entryPoints:['src/protocol.ts'], bundle:true,
  write:false, format:'esm', platform:'node' });
const { copyTensors } = await import('data:text/javascript;base64,'+Buffer.from(outputFiles[0].contents).toString('base64'));

test('transferable transport preserves int64, scalar, empty and sliced tensor bytes',()=>{
  const tensors=[
    {type:'int64',dims:[2],data:new BigInt64Array([2n**62n,-123n])},
    {type:'bool',dims:[3],data:new Uint8Array([0,1,0,1,0]).subarray(1,4)},
    {type:'float32',dims:[],data:new Float32Array([0.125])},
    {type:'float32',dims:[0],data:new Float32Array()},
  ];
  const snapshots=copyTensors(tensors);
  const actual=structuredClone(snapshots,{transfer:snapshots.map(t=>t.data.buffer)});
  tensors.forEach((ref,i)=>{
    assert.equal(actual[i].type,ref.type);assert.deepEqual(actual[i].dims,ref.dims);
    assert.deepEqual(actual[i].data,new Uint8Array(ref.data.buffer,ref.data.byteOffset,ref.data.byteLength));
    assert.equal(snapshots[i].data.buffer.byteLength,0);
    assert.notEqual(actual[i].dims,ref.dims);
  });
  assert.equal(new BigInt64Array(actual[0].data.buffer)[0],2n**62n);
  // Reusing/discarding ORT outputs must not change already delivered results.
  tensors.forEach(t=>new Uint8Array(t.data.buffer).fill(0));
  assert.equal(new Float32Array(actual[2].data.buffer)[0],0.125);
});
test('response byte limit applies to the total output before copying',()=>{
  const tensors=[{type:'uint8',dims:[512],data:new Uint8Array(512)},
    {type:'uint8',dims:[513],data:new Uint8Array(513)}];
  assert.throws(()=>copyTensors(tensors,1024),/increase responseBytes/);
  assert.equal(copyTensors(tensors,1025).length,2);
});
