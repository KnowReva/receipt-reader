"""Practice receipts with known answers, to measure accuracy without sharing anyone's real receipts.

`receipt-reader samples samples/` draws 30 receipts (photos with a slight tilt, blur and JPEG noise;
3 text PDFs; 3 scanned PDFs) from five regions with their own taxes and date formats, and writes the
correct answer next to each one (<name>.json). They are easier than crumpled real receipts: add your
own photos with an answer file to make the test harder and closer to your work."""

import datetime as dt
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

STORES = {
    "on": ("CAD", [("Maple Corner Grocery", "groceries"), ("Northline Hardware", "other"), ("Blue Kettle Diner", "restaurant")]),
    "qc": ("CAD", [("Marche du Coin", "groceries"), ("Cafe Lumen", "restaurant")]),
    "us": ("USD", [("Harbor Fuel & Go", "fuel"), ("Sunrise Pharmacy", "health"), ("Lakeside Books", "other")]),
    "eu": ("EUR", [("Backerei Sonnenschein", "groceries"), ("Papeterie Lefevre", "office")]),
    "in": ("INR", [("Spice Route Kitchen", "restaurant"), ("Green Leaf Supermart", "groceries")]),
    "au": ("AUD", [("Coastline Green Grocer", "groceries"), ("Southern Cross Taxis", "travel")]),
}  # fictional shops
ITEMS = {
    "groceries": [("Bananas 1kg", 1.79), ("Whole milk 2L", 4.49), ("Bread loaf", 3.29), ("Eggs dozen", 5.99),
                  ("Cheddar 400g", 7.49), ("Apples 1.5kg", 6.99), ("Coffee beans", 12.99), ("Rice 2kg", 6.49)],
    "restaurant": [("Soup of the day", 7.50), ("Club sandwich", 14.95), ("Veg curry", 13.00), ("Latte", 4.75),
                   ("Fries", 5.25), ("Iced tea", 3.50), ("Paneer tikka", 11.00), ("Dessert", 6.95)],
    "fuel": [("Regular unleaded 38.2L", 61.12), ("Car wash", 12.00), ("Water 1L", 2.29)],
    "health": [("Pain relief 24ct", 8.99), ("Bandages", 5.49), ("Vitamin D", 11.99), ("Hand cream", 7.25)],
    "office": [("A4 paper 500", 6.90), ("Pens x10", 4.50), ("Stapler", 9.80), ("Folders x5", 3.20)],
    "travel": [("Fare", 24.60), ("Booking fee", 2.50)],
    "other": [("Paperback novel", 18.99), ("Notebook", 6.99), ("Screws pack", 4.79), ("Tape measure", 12.49),
              ("Gift card", 25.00)],
}  # fmt: skip
PAY = ["VISA ****4821", "DEBIT", "CASH", "MASTERCARD ****1177"]


def _font(size):
    for name in ("DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "Courier New.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _date_text(region: str, d: dt.date) -> str:
    return {"us": f"{d:%m/%d/%Y}", "eu": f"{d:%d.%m.%Y}", "in": f"{d:%d/%m/%Y}", "au": f"{d:%d/%m/%Y}",
            "qc": f"{d:%Y-%m-%d}", "on": f"{d:%b %d, %Y}"}[region]  # fmt: skip


def make(rng: random.Random, region: str, multiplier: float = 1.0) -> dict:
    """One receipt: {truth, lines} (lines are what gets printed)."""
    currency, shops = STORES[region]
    vendor, category = rng.choice(shops)
    picks = rng.sample(ITEMS[category], k=min(len(ITEMS[category]), rng.randint(1, 5)))
    items = []
    for desc, price in picks:
        qty = rng.choice([1, 1, 1, 2, 3]) if category in ("groceries", "restaurant") else 1
        amount = round(price * multiplier * qty, 2)
        items.append({"description": desc, "quantity": qty, "amount": amount})
    sub = round(sum(i["amount"] for i in items), 2)
    taxes, included = [], False
    if region == "on":
        taxes = [{"name": "HST 13%", "amount": round(sub * 0.13, 2)}]
    elif region == "qc":
        taxes = [{"name": "TPS/GST 5%", "amount": round(sub * 0.05, 2)}, {"name": "TVQ/QST 9.975%", "amount": round(sub * 0.09975, 2)}]
    elif region == "us":
        taxes = [{"name": "Sales tax 8.875%", "amount": round(sub * 0.08875, 2)}] if category != "fuel" else []
    elif region == "in":
        taxes = [{"name": "CGST 2.5%", "amount": round(sub * 0.025, 2)}, {"name": "SGST 2.5%", "amount": round(sub * 0.025, 2)}]
    elif region == "eu":  # prices include VAT
        included = True
        taxes = [{"name": "MwSt 7% incl.", "amount": round(sub - sub / 1.07, 2)}]
    elif region == "au":  # prices include GST
        included = True
        taxes = [{"name": "GST incl.", "amount": round(sub / 11, 2)}]
    tip = round(sub * rng.choice([0.15, 0.18, 0.2]), 2) if category == "restaurant" and region in ("on", "qc", "us") and rng.random() < 0.6 else None
    total = round((sub if included else sub + sum(t["amount"] for t in taxes)) + (tip or 0), 2)
    day = dt.date(2025, 11, 1) + dt.timedelta(days=rng.randint(0, 330))
    pay = rng.choice(PAY)
    sym = {"CAD": "$", "USD": "$", "EUR": "", "INR": "Rs ", "AUD": "$"}[currency]
    lines = [("center", vendor.upper()), ("center", f"{rng.randint(10, 999)} Main Street"), ("", ""),
             ("", f"Date: {_date_text(region, day)}  {rng.randint(8, 21):02d}:{rng.randint(0, 59):02d}"), ("", "-" * 32)]  # fmt: skip
    for i in items:
        label = f"{i['quantity']} x {i['description']}" if i["quantity"] > 1 else i["description"]
        lines.append(("pair", (label[:22], f"{sym}{i['amount']:.2f}")))
    lines.append(("", "-" * 32))
    if not included:
        lines.append(("pair", ("SUBTOTAL", f"{sym}{sub:.2f}")))
        for t in taxes:
            lines.append(("pair", (t["name"], f"{sym}{t['amount']:.2f}")))
    if tip:
        lines.append(("pair", ("TIP", f"{sym}{tip:.2f}")))
    lines.append(("pair", ("TOTAL " + currency if currency == "EUR" else "TOTAL", f"{sym}{total:.2f}" + (" EUR" if currency == "EUR" else ""))))
    if included:
        for t in taxes:
            lines.append(("pair", (t["name"], f"{sym}{t['amount']:.2f}")))
    lines += [("", ""), ("", pay), ("center", "THANK YOU")]
    truth = {"vendor": vendor, "date": day.isoformat(), "currency": currency, "items": items,
             "subtotal": None if included else sub, "taxes": taxes, "tip": tip, "total": total,
             "payment_method": pay, "category": category}  # fmt: skip
    return {"truth": truth, "lines": lines}


def draw(lines: list, rng: random.Random, rough: bool = True) -> Image.Image:
    font, width, line_h = _font(22), 520, 30
    img = Image.new("RGB", (width, 60 + line_h * len(lines)), (250, 249, 244))
    d = ImageDraw.Draw(img)
    y = 30
    for kind, text in lines:
        if kind == "center":
            d.text((width // 2, y), text, font=font, fill=(25, 25, 25), anchor="ma")
        elif kind == "pair":
            d.text((24, y), text[0], font=font, fill=(25, 25, 25))
            d.text((width - 24, y), text[1], font=font, fill=(25, 25, 25), anchor="ra")
        else:
            d.text((24, y), text, font=font, fill=(25, 25, 25))
        y += line_h
    if not rough:
        return img
    bg = Image.new("RGB", (img.width + 160, img.height + 160), tuple(rng.randint(90, 160) for _ in range(3)))
    bg.paste(img, (80, 80))
    bg = bg.rotate(rng.uniform(-4, 4), resample=Image.BICUBIC, fillcolor=bg.getpixel((0, 0)))
    bg = bg.filter(ImageFilter.GaussianBlur(rng.uniform(0.2, 0.9)))
    return ImageEnhance.Brightness(bg).enhance(rng.uniform(0.85, 1.1))


def text_pdf(lines: list[str], path: Path) -> None:
    """A one-page PDF with real text in it, like an invoice from accounting software (no library needed)."""
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    ops = ["BT /F1 11 Tf 14 TL 60 780 Td"] + [f"({esc(t)}) Tj T*" for t in lines] + ["ET"]
    stream = "\n".join(ops).encode("latin-1", "replace")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]  # fmt: skip
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def _plain(lines: list) -> list[str]:
    out = []
    for kind, text in lines:
        out.append(f"{text[0]:<24}{text[1]:>12}" if kind == "pair" else text)
    return out


def write(folder: Path, count: int = 30, seed: int = 7) -> list[Path]:
    """Draw `count` practice receipts into folder, each with its answer (<name>.json)."""
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    regions = list(STORES)
    made = []
    for n in range(1, count + 1):
        region = regions[(n - 1) % len(regions)]
        r = make(rng, region, multiplier=10.0 if region == "in" else 1.0)  # rupee prices
        name = f"receipt-{n:02d}-{region}"
        if n % 10 == 0:  # an invoice PDF with text
            path = folder / f"{name}.pdf"
            text_pdf(_plain(r["lines"]), path)
        elif n % 10 == 5:  # a scanned PDF (an image inside, no text)
            path = folder / f"{name}.pdf"
            draw(r["lines"], rng).save(path, "PDF", resolution=150)
        else:
            path = folder / f"{name}.jpg"
            draw(r["lines"], rng).save(path, "JPEG", quality=rng.randint(60, 85))
        (folder / f"{name}.json").write_text(json.dumps(r["truth"], indent=1))
        made.append(path)
    return made
