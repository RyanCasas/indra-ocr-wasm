/** One shared response buffer per synchronous Python → asynchronous ORT call.
 * Header: status, metadata bytes, data bytes. Payload starts on an 8-byte boundary.
 * Status is published last; Atomics provides the happens-before relationship.
 */
export const HEADER_BYTES = 16;
export const RESPONSE_BYTES = 64 * 1024 * 1024;
export type TensorWire = { type: string; dims: number[]; data: ArrayBufferView };
export type ResultMeta = { type: string; dims: number[]; offset: number; length: number };
const encoder = new TextEncoder();
const decoder = new TextDecoder();
export const align8 = (n: number) => Math.ceil(n / 8) * 8;

export function publish(buffer: SharedArrayBuffer, tensors: TensorWire[] | Error): void {
  const state = new Int32Array(buffer, 0, 4);
  let status = 1;
  let metadata: Uint8Array;
  if (tensors instanceof Error) {
    metadata = encoder.encode(JSON.stringify({ error: tensors.message }));
    status = -1;
  } else {
    let offset = 0;
    const meta = tensors.map(t => {
      const item = { type: t.type, dims: t.dims, offset, length: t.data.byteLength };
      offset = align8(offset + t.data.byteLength);
      return item;
    });
    metadata = encoder.encode(JSON.stringify(meta));
    const start = align8(HEADER_BYTES + metadata.length);
    if (start + offset > buffer.byteLength) {
      publish(buffer, new Error(`ONNX response needs ${start + offset} bytes; increase responseBytes`));
      return;
    }
    tensors.forEach((t, i) => new Uint8Array(buffer, start + meta[i].offset, t.data.byteLength)
      .set(new Uint8Array(t.data.buffer, t.data.byteOffset, t.data.byteLength)));
  }
  if (HEADER_BYTES + metadata.length > buffer.byteLength) {
    metadata = encoder.encode('{"error":"ONNX error exceeds response buffer"}');
    status = -1;
  }
  new Uint8Array(buffer, HEADER_BYTES, metadata.length).set(metadata);
  Atomics.store(state, 1, metadata.length);
  Atomics.store(state, 0, status);
  Atomics.notify(state, 0);
}

export function receive(buffer: SharedArrayBuffer): TensorWire[] {
  const state = new Int32Array(buffer, 0, 4);
  const size = Atomics.load(state, 1);
  const meta = JSON.parse(decoder.decode(new Uint8Array(buffer, HEADER_BYTES, size).slice()));
  if (Atomics.load(state, 0) < 0) throw new Error(meta.error);
  const start = align8(HEADER_BYTES + size);
  return (meta as ResultMeta[]).map(t => ({ type: t.type, dims: t.dims,
    data: new Uint8Array(buffer, start + t.offset, t.length).slice() }));
}
