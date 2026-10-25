"""Checking the model's answer with arithmetic, the part that makes the output trustworthy.

A receipt checks itself: the line items add up to the subtotal, and subtotal + taxes + tip is the
total. When they don't, the model misread something, and the receipt is marked for a person to
check instead of slipping silently into your spreadsheet."""

import datetime as dt
import re

TOLERANCE = 0.02  # two cents of rounding


def money(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        return round(float(str(x).replace(",", "").strip()), 2)
    except ValueError:
        return None


def close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE


def problems(r: dict, today: dt.date | None = None) -> list[str]:
    """Everything that doesn't add up (empty: the receipt checks out)."""
    today = today or dt.date.today()
    found = []
    total = money(r.get("total"))
    if not total or total <= 0:
        found.append("no total")
    try:
        day = dt.date.fromisoformat(str(r.get("date", "")))
        if day > today:
            found.append(f"date {day} is in the future")
        elif day.year < 2000:
            found.append(f"date {day} looks wrong")
    except ValueError:
        found.append(f"date '{r.get('date', '')}' isn't a date (YYYY-MM-DD)")
    if not re.fullmatch(r"[A-Z]{3}", str(r.get("currency", ""))):
        found.append(f"currency '{r.get('currency', '')}' isn't a 3-letter code")
    items = [money(i.get("amount")) for i in r.get("items") or []]
    items_sum = round(sum(x for x in items if x is not None), 2) if items else None
    subtotal = money(r.get("subtotal"))
    taxes = round(sum(money(t.get("amount")) or 0 for t in r.get("taxes") or []), 2)
    tip = money(r.get("tip")) or 0
    if subtotal is not None and items_sum is not None and not close(items_sum, subtotal):
        found.append(f"items add up to {items_sum:.2f}, not the subtotal {subtotal:.2f}")
    base = subtotal if subtotal is not None else items_sum
    # Tax added on top (North America, India), or already included in the prices (VAT in Europe,
    # GST in Australia: the receipt shows "incl." and the items add up to the total).
    added = close(round(base + taxes + tip, 2), total) if total and base is not None else True
    included = bool(taxes) and close(round(base + tip, 2), total) if total and base is not None else False
    # Taxes have limits: tax included in the prices is at most about 22% of the total (VAT of 27%,
    # the highest anywhere, is 21% of a tax-included price); tax added on top at most about 30% of the
    # subtotal (India's highest GST is 28%). More means something else was read as tax, such as the
    # store's tax registration number.
    if included and total and taxes > 0.22 * total:
        included = False
        found.append(f"tax {taxes:.2f} can't be included in a total of {total:.2f} (that would be "
                     f"{100 * taxes / total:.0f}%): check the tax lines")  # fmt: skip
    elif added and base and taxes > 0.30 * base:
        found.append(f"tax {taxes:.2f} is more than 30% of {base:.2f}: check the tax lines")
    if total and base is not None and not (added or included) and not any(p.startswith("tax ") for p in found):
        found.append(f"{'subtotal' if subtotal is not None else 'items'} {base:.2f} + tax {taxes:.2f}"
                     f"{f' + tip {tip:.2f}' if tip else ''} = {base + taxes + tip:.2f}, not the total {total:.2f}")  # fmt: skip
    return found


def checked(r: dict) -> bool:
    """True when the arithmetic could be checked at all (items or a subtotal were read)."""
    return bool(r.get("items")) or money(r.get("subtotal")) is not None
