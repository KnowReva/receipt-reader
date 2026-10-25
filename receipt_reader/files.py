"""Turning a file into something the model can read.

  photo (JPG, PNG, WEBP, HEIC...)  upright (the phone's rotation flag applied), at most 1600 px, as JPEG
  PDF with text in it         the text itself (invoices from software usually have it): faster and exact
  scanned PDF (no text)       each page drawn as an image, like a photo
  scanned PDF with text       a phone scanner app (Adobe Scan, Microsoft Lens...) adds text it guessed
                              from the photo, with mistakes ("Walmart" read as "Walmartsa"): the page
                              images go to the model, with that text as a hint only
"""

import base64
import datetime as dt
import io
from pathlib import Path

from PIL import Image, ImageOps

try:  # iPhone photos (HEIC): the pillow-heif plugin teaches Pillow to open them
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC = {".heic", ".heif"}
except ImportError:  # pragma: no cover - installed with receipt-reader, but optional for your own builds
    HEIC = set()

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"} | HEIC
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


def scanned(path: Path) -> bool:
    """True when a PDF page is mostly one picture: a scan or a phone photo, whatever text it carries."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw

    pdf = pdfium.PdfDocument(str(path))
    try:
        for i in range(min(len(pdf), MAX_PAGES)):
            page = pdf[i]
            width, height = page.get_size()
            for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE]):
                left, bottom, right, top = (getattr(obj, "get_bounds", None) or obj.get_pos)()  # pypdfium2 5 or 4
                if (right - left) * (top - bottom) >= 0.5 * width * height:
                    return True
    except Exception:  # noqa: BLE001 - can't tell: treat the text as real
        return False
    return False


def load(path: Path) -> dict:
    """{"images": [base64...]}, {"text": "..."}, or both with "scan_text" for a scan that carries the
    text a scanner app guessed, for one receipt file."""
    ext = path.suffix.lower()
    if ext in IMAGE_TYPES:
        with Image.open(path) as img:
            return {"images": [image_b64(img)]}
    if ext == ".pdf":
        text = pdf_text(path)
        if len(text) > 40 and not scanned(path):  # real text, not just a stray page number
            return {"text": text}
        if len(text) > 40:
            return {"images": pdf_images(path), "scan_text": text}
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


def taken_on(path: Path) -> dt.date | None:
    """When a photo was taken (its EXIF date), else when the file was last saved."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            stamp = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, else DateTime
        if stamp:
            return dt.datetime.strptime(str(stamp)[:10], "%Y:%m:%d").date()
    except Exception:  # noqa: BLE001 - a PDF or a photo without EXIF
        pass
    try:
        return dt.date.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None
