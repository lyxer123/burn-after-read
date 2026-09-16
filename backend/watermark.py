#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Best-effort watermarking for burn-after-read links.

PDF  : reportlab draws a tiled, rotated, semi-transparent text layer, then
       pypdf merges it onto every page.
Image: Pillow tiles the text across the picture.
Other: falls back to a plain copy of the original (no watermark).
All imports are optional - if a library is missing the function degrades to a
straight copy rather than crashing the download.
"""
import io
import os
import mimetypes
import shutil

try:
    from PIL import Image, ImageDraw, ImageFont
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

try:
    from reportlab.pdfgen import canvas as _rl_canvas
    import pypdf
    HAVE_PDF = True
except Exception:
    HAVE_PDF = False


def _make_watermark_page(text, w, h, buf):
    c = _rl_canvas.Canvas(buf, pagesize=(w, h))
    c.setFillAlpha(0.16)
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.setFont("Helvetica-Bold", 26)
    c.saveState()
    c.translate(w / 2.0, h / 2.0)
    c.rotate(-30)
    step = 230
    for x in range(-int(w), int(w), step):
        for y in range(-int(h), int(h), step):
            c.drawCentredString(x, y, text)
    c.restoreState()
    c.showPage()
    c.save()


def watermark_pdf(input_path, output_path, text):
    reader = pypdf.PdfReader(input_path)
    writer = pypdf.PdfWriter()
    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        buf = io.BytesIO()
        _make_watermark_page(text, w, h, buf)
        buf.seek(0)
        wm_page = pypdf.PdfReader(buf).pages[0]
        page.merge_page(wm_page)
        writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)


def watermark_image(input_path, output_path, text):
    img = Image.open(input_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("arial.ttf", max(22, img.size[1] // 28))
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    step_x = tw + 70
    step_y = th + 70
    for y in range(-th, img.size[1], step_y):
        for x in range(-tw, img.size[0], step_x):
            draw.text((x, y), text, font=font, fill=(200, 0, 0, 110))
    out = Image.alpha_composite(img, overlay).convert("RGB")
    out.save(output_path)


def apply(input_path, output_path, text):
    """Watermark <input_path> -> <output_path>. Falls back to a copy."""
    if not text:
        shutil.copyfile(input_path, output_path)
        return
    mime, _ = mimetypes.guess_type(input_path)
    try:
        if HAVE_PDF and mime == "application/pdf":
            watermark_pdf(input_path, output_path, text)
            return
        if HAVE_PIL and mime and mime.startswith("image/"):
            watermark_image(input_path, output_path, text)
            return
    except Exception:
        pass
    # unsupported type -> plain copy (still works, just no watermark)
    shutil.copyfile(input_path, output_path)
