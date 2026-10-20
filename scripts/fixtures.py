"""Generate deterministic inputs and golden outputs using unmodified native Indra.
Run with .venv/bin/python; see requirements-native.txt. Fixtures are committed.
"""
import argparse
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor/indra"))
import cv2
import numpy as np
import onnxruntime
import pikepdf
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import indra_ocr

OUT = ROOT / "tests/fixtures"
OUT.mkdir(exist_ok=True)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--golden-only', action='store_true', help='Refresh reference outputs without rewriting input documents')
args = parser.parse_args()
if not args.golden_only:
    FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    pdfmetrics.registerFont(TTFont("Fixture", FONT))
    font = ImageFont.truetype(FONT, 36)
    scan = Image.new("L", (1400, 1000), 255)
    draw = ImageDraw.Draw(scan)
    for i, text in enumerate(["Indra WebAssembly OCR", "All documents stay in your browser.",
        "The quick brown fox jumps over the lazy dog.", "Invoice 2026: total 123.45 EUR",
        "Unicode: café, España, über, Ελληνικά."]):
        draw.text((90, 100 + i * 100), text, font=font, fill=0)
    scan.save(OUT / "scan.png")
    scan.transpose(Image.Transpose.ROTATE_90).save(OUT / "turned.png")
    scan.rotate(2, fillcolor=255).save(OUT / "skew.png")
    scan.save(OUT / "pages.tiff", save_all=True, append_images=[Image.new("L", (600, 800), 255), scan])

    # Exercise the actual CJK model routing, not just the upstream stub session.
    cjk = Image.new("L", (1400, 700), 255)
    cd = ImageDraw.Draw(cjk)
    cf = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 42)
    for i, text in enumerate(["中文识别测试，浏览器本地运行。", "所有文档都保留在您的设备上。", "价格 123.45 元，总计 2026。"]):
        cd.text((90, 100+i*110), text, font=cf, fill=0)
    cjk.save(OUT / "chinese.png")
    # Fractions and superscripts force the attention decoder and cached state path.
    formula = Image.new("L", (1400, 850), 255)
    fd = ImageDraw.Draw(formula)
    ff = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 44)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 28)
    for y in [130, 350, 570]:
        fd.text((100,y), "f(x) =", font=ff, fill=0)
        fd.text((350,y-30), "x + 1", font=ff, fill=0)
        fd.line((340,y+30,530,y+30), fill=0, width=2)
        fd.text((370,y+45), "x", font=ff, fill=0)
        fd.text((402,y+34), "2", font=small, fill=0)
        fd.text((550,y), "+ α + β = 0", font=ff, fill=0)
    formula.save(OUT/"formula.png")

    c = canvas.Canvas(str(OUT / "digital.pdf"), pagesize=(612, 792), invariant=True)
    for i in range(2):
        c.setFont("Fixture", 18)
        c.drawString(55, 720, f"Browser document page {i+1}")
        c.setFont("Fixture", 12)
        for j, text in enumerate(["The original PDF text layer is preserved.", "Español: acción, información, número 123.",
                                  "Greek: Ελληνικά. Cyrillic: Привет мир.", "A final paragraph for reading order."]):
            c.drawString(55, 660-j*40, text)
        c.showPage()
    c.save()
    with pikepdf.open(OUT / "digital.pdf") as pdf:
        pdf.save(OUT / "locked.pdf", encryption=pikepdf.Encryption(user="pw", owner="owner"), static_id=True)
    with pikepdf.open(OUT / "digital.pdf") as pdf:
        pdf.pages[0].obj.Rotate=90
        pdf.save(OUT / "rotated.pdf", deterministic_id=True)
    with pikepdf.open(OUT / "digital.pdf") as pdf:
        pdf.pages[0].obj.CropBox=pikepdf.Array([40,100,570,750])
        pdf.save(OUT / "cropped.pdf", deterministic_id=True)
    c=canvas.Canvas(str(OUT/"invisible.pdf"),pagesize=(612,792),invariant=True)
    c.drawImage(str(OUT/"scan.png"),0,0,612,792)
    t=c.beginText(50,700); t.setFont("Helvetica",12); t.setTextRenderMode(3); t.textLine("Hidden OCR layer")
    c.drawText(t);c.save()
    c=canvas.Canvas(str(OUT/"hybrid.pdf"),pagesize=(612,792),invariant=True)
    c.setFont("Fixture",18); c.drawString(50,730,"Digital heading with scanned content")
    c.drawImage(str(OUT/"scan.png"),40,100,532,380);c.save()
    c=canvas.Canvas(str(OUT/"table.pdf"),pagesize=(612,792),invariant=True)
    c.setFont("Fixture",20);c.drawString(60,730,"Quarterly report")
    c.setFont("Fixture",14)
    for r,row in enumerate([["Product","Units","Total"],["Paper","12","120.00"],["Ink","3","45.00"],["Sum","15","165.00"]]):
        for x,text in zip([65,240,410],row):c.drawString(x,640-r*40,text)
    for y in [660,620,580,540,500]:c.line(60,y,540,y)
    for x in [60,230,400,540]:c.line(x,500,x,660)
    c.save()
# New 1.1 paths use actual model inference in addition to the upstream unit tests.
if not args.golden_only:
    from PIL import ImageOps
    scan = Image.open(OUT / "scan.png").convert("L")
    ImageOps.invert(scan).save(OUT / "dark.png")
    scan.rotate(12, fillcolor=255).save(OUT / "tilted.png")
    for filename, font_path, direction, lines in [
        ("arabic.png", "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf", "rtl",
         ["مرحبا بالعالم", "جميع المستندات تبقى على جهازك", "قراءة النصوص باللغة العربية"]),
        ("hindi.png", "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf", "ltr",
         ["नमस्ते दुनिया", "सभी दस्तावेज आपके उपकरण पर रहते हैं", "ब्राउज़र में पाठ पहचान परीक्षण"]),
    ]:
        image = Image.new("L", (1400, 700), 255)
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(font_path, 44)
        for i, text in enumerate(lines):
            draw.text((100, 80 + i * 150), text, font=font, fill=0, direction=direction)
        image.save(OUT / filename)

# Small native bridge snapshots catch text geometry regressions independently
# of whether an OCR model happens to produce the same lines.
from indra_ocr.textlayer import extract_runs, invisible_text_frac, _device_affine
pdf_golden={}
for name in ["digital.pdf","rotated.pdf","cropped.pdf","invisible.pdf"]:
    with pdfium.PdfDocument(OUT/name) as doc:
        page=doc[0]; runs,stats=extract_runs(page)
        pdf_golden[name]={"size":page.get_size(),"affine":_device_affine(page).tolist(),
            "runs":[asdict(r) for r in runs],"stats":stats,"invisible":invisible_text_frac(page)}
(OUT/"pdfium.json").write_text(json.dumps(pdf_golden,ensure_ascii=False,indent=2))

suites=[]
for name,options,files in [
    ("auto",{},["scan.png","chinese.png","arabic.png","hindi.png","dark.png","tilted.png","pages.tiff","digital.pdf","hybrid.pdf","table.pdf","rotated.pdf","cropped.pdf","invisible.pdf","locked.pdf"]),
    ("ocr",{"mode":"ocr"},["scan.png","turned.png","skew.png","digital.pdf"]),
    ("text",{"mode":"text","pdfOrder":False,"imageOcr":False,"furniture":True},["digital.pdf","table.pdf"]),
    ("math",{"math":True},["scan.png","formula.png","digital.pdf"]),
]:
    native_options={ {"imageOcr":"image_ocr"}.get(k,k):v for k,v in options.items() if k != "pdfOrder" }
    conv=indra_ocr.load(path=ROOT/"public/models",threads=1,**native_options)
    calls={}
    class Traced:
        def __init__(self, session, name): self.session,self.name=session,name
        def run(self,*a,**k):
            calls[self.name]=calls.get(self.name,0)+1
            return self.session.run(*a,**k)
        def get_inputs(self):return self.session.get_inputs()
    for attr in ['det','rec','order','orient','script']:
        sess=getattr(conv.ocr,attr,None)
        if sess is not None:setattr(conv.ocr,attr,Traced(sess,attr))
    # Keep session identities in the LM registry when adding instrumentation.
    traced = conv.ocr.rec
    if id(traced.session) in conv.ocr.lms:
        conv.ocr.lms[id(traced)] = conv.ocr.lms.pop(id(traced.session))
    for group, (session, vocab) in conv.ocr.groups.items():
        traced = Traced(session, 'rec_' + group)
        conv.ocr.groups[group] = (traced, vocab)
        if id(session) in conv.ocr.lms:
            conv.ocr.lms[id(traced)] = conv.ocr.lms.pop(id(session))
    if conv.ocr.math is not None:
        for attr in ['cls','enc','init','step']:
            setattr(conv.ocr.math,attr,Traced(getattr(conv.ocr.math,attr),'math_'+attr))
    cases=[]
    for file in files:
        convert_opts={"password":"pw"} if file=="locked.pdf" else {}
        pages=[{"page":i,**asdict(p),"text":p.text} for i,p in conv.convert(OUT/file,**convert_opts)]
        assert all(p["source"]!="error" for p in pages),pages
        for p in pages:p.pop("timings")
        print(name,file,len(pages),[p["source"] for p in pages],flush=True)
        cases.append({"file":file,"options":convert_opts,"pages":pages})
    # max_pages has a separate case to verify limiting before conversion.
    if name=="auto":
        pages=[{"page":i,**asdict(p),"text":p.text} for i,p in conv.convert(OUT/"digital.pdf",max_pages=1)]
        for p in pages:p.pop("timings")
        cases.append({"file":"digital.pdf","options":{"maxPages":1},"pages":pages})
    print('model calls',name,calls,flush=True)
    if name=='auto':
        for group in ['cjk', 'rtl', 'world']:
            assert calls.get('rec_' + group, 0) > 0, calls
    if name=='math':assert calls.get('math_step',0)>0
    suites.append({"name":name,"options":options,"cases":cases,"nativeModelCalls":calls})
(OUT/"golden.json").write_text(json.dumps({"versions":{"python":platform.python_version(),"numpy":np.__version__,
    "opencv":cv2.__version__,"onnxruntime":onnxruntime.__version__,"indra":indra_ocr.__version__},
    "upstream":(ROOT/"vendor/indra/REVISION").read_text().strip(),"suites":suites},ensure_ascii=False,indent=2))
