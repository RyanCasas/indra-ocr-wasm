/** Binary tensor messages between the Python and ONNX workers. */
export const RESPONSE_BYTES = 64 * 1024 * 1024;
export type TensorWire = { type: string; dims: number[]; data: ArrayBufferView };

/** Own the output bytes before disposing ORT tensors or transferring buffers. */
export function copyTensors(tensors: TensorWire[], limit = RESPONSE_BYTES): TensorWire[] {
  const bytes = tensors.reduce((sum, tensor) => sum + tensor.data.byteLength, 0);
  if (bytes > limit) {
    throw new Error(`ONNX response needs ${bytes} bytes; increase responseBytes`);
  }
  return tensors.map(tensor => ({
    type: tensor.type,
    dims: [...tensor.dims],
    data: new Uint8Array(tensor.data.buffer, tensor.data.byteOffset, tensor.data.byteLength).slice(),
  }));
}
