import { init } from '@embedpdf/pdfium';

/** A deliberately narrow pypdfium2 backend. All geometry, glyph extraction and
 * rasterization is delegated to the real PDFium C API, never approximated. */
export async function createPdfium(wasmURL: string) {
  const response = await fetch(wasmURL);
  if (!response.ok) throw new Error(`PDFium download: ${response.status}`);
  const p = await init({ wasmBinary: await response.arrayBuffer() });
  p.PDFiumExt_Init();
  const m = p.pdfium;
  const alloc = m.wasmExports.malloc;
  const free = m.wasmExports.free;
  // Emscripten refreshes HEAPU8 after memory growth; look it up on each call.
  const heap = () => (m as unknown as { HEAPU8: Uint8Array }).HEAPU8;
  const read = (ptr: number, size: number) => heap().slice(ptr, ptr + size);
  const write = (ptr: number, bytes: Uint8Array) => heap().set(bytes, ptr);
  return {
    call(name: string, args: number[]) {
      const fn = (p as unknown as Record<string, (...a: number[]) => unknown>)[name];
      if (!fn) throw new Error(`PDFium function unavailable: ${name}`);
      return fn(...args);
    },
    open(bytes: Uint8Array, password: string) {
      const ptr = alloc(bytes.length);
      write(ptr, bytes);
      const doc = p.FPDF_LoadMemDocument64(ptr, bytes.length, password);
      if (!doc) { free(ptr); throw new Error(p.FPDF_GetLastError() === 4 ? 'password required or incorrect' : 'invalid PDF'); }
      return [doc, ptr];
    },
    close(doc: number, ptr: number) { p.FPDF_CloseDocument(doc); if (ptr) free(ptr); },
    device(page: number, width: number, height: number, x: number, y: number) {
      const ptr = alloc(8);
      try {
        if (!p.FPDF_PageToDevice(page, 0, 0, width, height, 0, x, y, ptr, ptr + 4)) throw new Error('PageToDevice failed');
        return [m.getValue(ptr, 'i32'), m.getValue(ptr + 4, 'i32')];
      } finally { free(ptr); }
    },
    charbox(text: number, index: number) {
      const ptr = alloc(32);
      try {
        if (!p.FPDFText_GetCharBox(text, index, ptr, ptr + 8, ptr + 16, ptr + 24)) return [];
        return [0, 8, 16, 24].map(i => m.getValue(ptr + i, 'double'));
      } finally { free(ptr); }
    },
    setText(object: number, codeUnits: Uint16Array) {
      const ptr = alloc(codeUnits.byteLength);
      try {
        write(ptr, new Uint8Array(codeUnits.buffer, codeUnits.byteOffset, codeUnits.byteLength));
        return p.FPDFText_SetText(object, ptr);
      } finally { free(ptr); }
    },
    render(page: number, scale: number) {
      const w = Math.ceil(p.FPDF_GetPageWidth(page) * scale);
      const h = Math.ceil(p.FPDF_GetPageHeight(page) * scale);
      const bitmap = p.FPDFBitmap_CreateEx(w, h, 1, 0, 0); // FPDFBitmap_Gray
      if (!bitmap) throw new Error(`Could not allocate ${w}×${h} PDF bitmap`);
      try {
        p.FPDFBitmap_FillRect(bitmap, 0, 0, w, h, 0xffffffff);
        p.FPDF_RenderPageBitmap(bitmap, page, 0, 0, w, h, 0, 9); // FPDF_GRAYSCALE | FPDF_ANNOT, pypdfium2 defaults
        const stride = p.FPDFBitmap_GetStride(bitmap);
        return { width: w, height: h, stride,
          data: read(p.FPDFBitmap_GetBuffer(bitmap), stride * h) };
      } finally { p.FPDFBitmap_Destroy(bitmap); }
    },
    save(doc: number) {
      const writer = p.PDFiumExt_OpenFileWriter();
      let ptr = 0;
      try {
        if (!p.PDFiumExt_SaveAsCopy(doc, writer)) throw new Error('Could not save PDF');
        const size = p.PDFiumExt_GetFileWriterSize(writer);
        ptr = alloc(size);
        p.PDFiumExt_GetFileWriterData(writer, ptr, size);
        return read(ptr, size);
      } finally { if (ptr) free(ptr); p.PDFiumExt_CloseFileWriter(writer); }
    },
  };
}
