"""Turning a file into something the model can read.

  photo (JPG, PNG, WEBP...)   upright (the phone's rotation flag applied), at most 1600 px, as JPEG
  PDF with text in it         the text itself (invoices from software usually have it): faster and exact
  scanned PDF (no text)       each page drawn as an image, like a photo
"""

import base64
import io
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
MAX_SIDE = 1600  # bigger photos are slower and no more accurate for receipts
MAX_PAGES = 3  # a receipt or invoice longer than this is unusual


def image_b64(img: Image.Image) -> str:
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return base64.b64encode(buffer.getvalue()).decode()


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages[:MAX_PAGES]).strip()


def pdf_images(path: Path) -> list[str]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    pages = [pdf[i].render(scale=2).to_pil() for i in range(min(len(pdf), MAX_PAGES))]
    return [image_b64(p) for p in pages]


def load(path: Path) -> dict:
    """{"images": [base64...]} or {"text": "..."} for one receipt file."""
    ext = path.suffix.lower()
    if ext in IMAGE_TYPES:
        with Image.open(path) as img:
            return {"images": [image_b64(img)]}
    if ext == ".pdf":
        text = pdf_text(path)
        if len(text) > 40:  # real text, not just a stray page number
            return {"text": text}
        return {"images": pdf_images(path)}
    raise ValueError(f"not a photo or PDF: {path.name}")


def find(paths: list[str]) -> list[Path]:
    """The receipt files in these files and folders (folders are searched, sorted by name)."""
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.suffix.lower() in IMAGE_TYPES | {".pdf"})
        elif p.is_file():
            out.append(p)
    return out
