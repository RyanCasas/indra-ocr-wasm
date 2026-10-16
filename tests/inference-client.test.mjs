import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
const { outputFiles } = await build({ entryPoints:['src/inference-client.ts'], bundle:true,
  write:false, format:'esm', platform:'node' });
const { InferenceClient } = await import('data:text/javascript;base64,'+Buffer.from(outputFiles[0].contents).toString('base64'));

class WorkerStub {
  messages=[];
  postMessage(data) { this.messages.push(structuredClone(data)); }
  reply(data) { this.onmessage({data}); }
  terminate() { this.terminated=true; }
}

test('model errors reject and subsequent inference can succeed',async()=>{
  const worker=new WorkerStub();const client=new InferenceClient(worker,1000,2048);
  try {
    const first=client.run('model',{},null);
    assert.equal(worker.messages[0].responseBytes,2048);
    worker.reply({kind:'error',id:worker.messages[0].id,error:'bad model'});
    await assert.rejects(first,/bad model/);
    const second=client.run('model',{},null);
    const tensors=[{type:'int64',dims:[1],data:new BigInt64Array([2n**62n])}];
    worker.reply({kind:'result',id:worker.messages[1].id,tensors});
    assert.deepEqual(await second,tensors);
  } finally { client.dispose(); }
});

test('late responses after a timeout cannot complete another request',async()=>{
  const worker=new WorkerStub();const client=new InferenceClient(worker,20);
  try {
    await assert.rejects(client.run('slow',{},null),/timed out/);
    const second=client.run('next',{},null);
    worker.reply({kind:'result',id:worker.messages[0].id,tensors:['late']});
    worker.reply({kind:'result',id:worker.messages[1].id,tensors:[]});
    assert.deepEqual(await second,[]);
  } finally { client.dispose(); }
});

for (const event of ['onerror','onmessageerror','dispose']) {
  test(`${event} rejects pending and future requests`,async()=>{
    const worker=new WorkerStub();const client=new InferenceClient(worker,1000);
    const pending=client.run('model',{},null);
    if(event==='dispose')client.dispose();
    else worker[event]({message:'worker crashed'});
    await assert.rejects(pending);
    await assert.rejects(client.run('model',{},null));
    client.dispose();assert.equal(worker.terminated,true);
  });
}

test('a postMessage failure cleans up without poisoning later requests',async()=>{
  const worker=new WorkerStub();const client=new InferenceClient(worker,1000);
  worker.postMessage=()=>{throw new Error('cannot clone');};
  await assert.rejects(client.run('model',{},null),/cannot clone/);
  worker.postMessage=WorkerStub.prototype.postMessage;
  const next=client.run('model',{},null);
  worker.reply({kind:'result',id:worker.messages[0].id,tensors:[]});
  assert.deepEqual(await next,[]);client.dispose();
});

test('backend progress is forwarded without settling inference', async () => {
  const worker = new WorkerStub();
  const messages = [];
  const client = new InferenceClient(worker, 1000, 2048, message => messages.push(message));
  try {
    const pending = client.run('model', {}, null);
    worker.reply({ kind: 'progress', message: 'Retrying with WASM' });
    assert.deepEqual(messages, ['Retrying with WASM']);
    worker.reply({ kind: 'result', id: worker.messages[0].id, tensors: [] });
    assert.deepEqual(await pending, []);
  } finally { client.dispose(); }
});
