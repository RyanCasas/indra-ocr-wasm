"""Subset of pypdfium2 used by Indra, backed by PDFium WebAssembly.

Not a general replacement for pypdfium2. The vendored Indra algorithms stay
unmodified; this module adapts their calls to the same PDFium C API in WASM.
"""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from indra_bridge import pdfium
from . import raw
from pyodide.ffi import to_js


class PdfiumError(RuntimeError):
    pass


class PdfDocument:
    def __init__(self, path=None, password=None):
        self.pages = []
        self.raw = 0
        self.ptr = 0
        try:
            data = np.frombuffer(Path(path).read_bytes(), dtype=np.uint8)
            self.raw, self.ptr = pdfium.open(to_js(data), password or "").to_py()
        except Exception as e:
            raise PdfiumError(str(e)) from e

    @classmethod
    def new(cls):
        doc = cls.__new__(cls)
        doc.pages, doc.ptr = [], 0
        doc.raw = raw.FPDF_CreateNewDocument()
        return doc

    def __len__(self):
        return raw.FPDF_GetPageCount(self.raw)

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        page = PdfPage(raw.FPDF_LoadPage(self.raw, index), self)
        self.pages.append(page)
        return page

    def new_page(self, width, height):
        page = PdfPage(raw.FPDFPage_New(self.raw, len(self), width, height), self)
        self.pages.append(page)
        return page

    def save(self, path):
        Path(path).write_bytes(bytes(pdfium.save(self.raw).to_py()))

    def close(self):
        if self.raw:
            for page in self.pages:
                page.close()
            pdfium.close(self.raw, self.ptr)
            self.raw = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        self.close()


class PdfPage:
    def __init__(self, handle, document):
        self.raw = handle
        # A page keeps its document alive, including PdfDocument(path)[0].
        self.document = document
        self.textpages = []
        if not handle:
            raise PdfiumError("Could not load PDF page")

    def get_size(self):
        return raw.FPDF_GetPageWidth(self.raw), raw.FPDF_GetPageHeight(self.raw)

    def get_rotation(self):
        return raw.FPDFPage_GetRotation(self.raw) * 90

    def set_rotation(self, rotation):
        raw.FPDFPage_SetRotation(self.raw, (rotation // 90) % 4)

    def render(self, scale=1, grayscale=False):
        if not grayscale:
            raise NotImplementedError("Indra PDFium backend renders grayscale only")
        result = pdfium.render(self.raw, scale)
        # Copy out of the PDFium heap: the bitmap is already released by JS.
        arr = np.asarray(result.data.to_py(), dtype=np.uint8).reshape(result.height, result.stride)
        image = arr[:, :result.width].copy()
        return SimpleNamespace(to_numpy=lambda: image)

    def get_textpage(self):
        tp = TextPage(raw.FPDFText_LoadPage(self.raw))
        self.textpages.append(tp)
        return tp

    def get_objects(self, max_depth=4):
        def walk(handle, depth, form=False):
            count = raw.FPDFFormObj_CountObjects(handle) if form else raw.FPDFPage_CountObjects(handle)
            for i in range(count):
                obj = raw.FPDFFormObj_GetObject(handle, i) if form else raw.FPDFPage_GetObject(handle, i)
                kind = raw.FPDFPageObj_GetType(obj)
                yield SimpleNamespace(raw=obj, type=kind)
                if kind == 5 and depth < max_depth:
                    yield from walk(obj, depth + 1, True)
        yield from walk(self.raw, 1)

    def close(self):
        if self.raw:
            for tp in self.textpages:
                tp.close()
            raw.FPDF_ClosePage(self.raw)
            self.raw = 0


class TextPage:
    def __init__(self, handle):
        self.raw = handle
        if not handle:
            raise PdfiumError("Could not load PDF text page")

    def count_chars(self):
        return raw.FPDFText_CountChars(self.raw)

    def close(self):
        if self.raw:
            raw.FPDFText_ClosePage(self.raw)
            self.raw = 0
