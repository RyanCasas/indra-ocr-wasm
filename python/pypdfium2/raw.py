"""Adapt only the two pointer-output calls; forward scalar C calls directly."""
from pyodide.ffi import to_js
from indra_bridge import pdfium

FPDF_PAGEOBJ_TEXT = 1
FPDF_TEXTRENDERMODE_INVISIBLE = 3


def FPDF_PageToDevice(page, x0, y0, width, height, rotate, x, y, dx, dy):
    if x0 or y0 or rotate:
        raise NotImplementedError("Only the device transform used by Indra is supported")
    dx.value, dy.value = pdfium.device(page, width, height, x, y).to_py()
    return 1


def FPDFText_GetCharBox(tp, index, pl, pr, pb, pt):
    values = pdfium.charbox(tp, index).to_py()
    if not values:
        return 0
    for ptr, value in zip((pl, pr, pb, pt), values):
        ptr._obj.value = value
    return 1


def __getattr__(name):
    if name.startswith("FPDF"):
        return lambda *args: pdfium.call(name, to_js(args))
    raise AttributeError(name)
