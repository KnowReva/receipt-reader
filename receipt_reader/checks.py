"""Checking the model's answer with arithmetic, the part that makes the output trustworthy.

A receipt checks itself: the line items add up to the subtotal, and subtotal + taxes + tip is the
total. When they don't, the model misread something, and the receipt is marked for a person to
check instead of slipping silently into your spreadsheet."""

import datetime as dt
import re

TOLERANCE = 0.02  # two cents of rounding
TAX_ADDED = {"CAD", "USD"}  # tax is added on top of the prices, not included in them
INCL = re.compile(r"incl|inkl|inclu", re.I)


def money(x) -> float | None:
    if x is None or x == "":
        return None
    try:
        return round(float(str(x).replace(",", "").strip()), 2)
    except ValueError:
        return None


def close(a: float, b: float) -> bool:
    # Rounded to cents first: in floating point 1.02 - 1.00 is 0.020000000000000018, which would
    # fail "<= 0.02" exactly at the edge. Every amount is already in cents, so this is exact.
    return round(abs(a - b), 2) <= TOLERANCE


def drop_impossible_taxes(r: dict) -> list[str]:
    """Remove "tax" lines that can't be taxes on this receipt: more than the total, or a whole number
    of 7 digits or more (a store's tax registration number, e.g. "GST/HST 137466199 RT 0001").
    Returns notes on what was removed."""
    total = money(r.get("total")) or 0
    kept, notes = [], []
    for t in r.get("taxes") or []:
        amount = money(t.get("amount"))
        looks_like_id = amount is not None and amount == int(amount) and abs(amount) >= 1_000_000
        if amount is not None and (looks_like_id or (total and amount > total)):
            notes.append(f"ignored \"{t.get('name', 'tax')} {t.get('amount')}\": a registration number or "
                         f"other figure, not a tax on a total of {total:.2f}")  # fmt: skip
        else:
            kept.append(t)
    r["taxes"] = kept
    return notes


def drop_unprinted_tax(r: dict) -> list[str]:
    """On a Canadian or US receipt (tax added on top), remove a tax the receipt itself shows can't be
    there: the subtotal equals the total and the items add up to it, so nothing was added. Models
    sometimes fill the tax field anyway (the Walmart scan: 3.74 on tax-free groceries, twice).
    A tax line that says "incl." is left alone. Returns notes on what was removed."""
    taxes = r.get("taxes") or []
    if r.get("currency") not in TAX_ADDED or not taxes or any(INCL.search(str(t.get("name", ""))) for t in taxes):
        return []
    total, subtotal = money(r.get("total")), money(r.get("subtotal"))
    items = [money(i.get("amount")) for i in r.get("items") or []]
    if not total or subtotal is None or not items or None in items:
        return []
    if close(subtotal, total) and close(round(sum(items), 2), total):
        r["taxes"] = []
        named = ", ".join(f"{t.get('name', 'tax')} {t.get('amount')}" for t in taxes)
        return [f"ignored \"{named}\": the items, subtotal and total are all {total:.2f}, so no tax was added"]
    return []


# The receipt's own clues to its currency, for the currency the arithmetic can't check (a plain "$" is
# Canada, the USA, Australia...). Strong clues (tax names and numbers only one country uses) count 3; a
# state or province code after the city counts 2, or 1 to each country when two share it (WA, NT, SA).
STRONG = [
    ("CAD", r"\bGST/HST\b|\bHST\b|\bTPS\b|\bTVQ\b|\bQST\b|\bRT ?0001\b|\bTQ ?0001\b"),
    ("AUD", r"\bABN\b"),
    ("EUR", r"€|\bEUR\b|\bMwSt\b|\bTVA\b|\bIVA\b|\bBTW\b|\bUSt\b"),
    ("INR", r"₹|\bRs\.?\s?\d|\bINR\b|\bCGST\b|\bSGST\b|\bGSTIN\b"),
    ("GBP", r"£|\bGBP\b"),
    ("USD", r"\bsales tax\b"),
]
PROVINCES = "ON QC BC AB MB SK NS NB NL PE YT NU"
US_STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND "
             "OH OK OR PA RI SC SD TN TX UT VT VA WV WI WY DC")  # fmt: skip
AU_STATES = "NSW VIC QLD TAS ACT"
SHARED = {"WA": ("USD", "AUD"), "SA": ("AUD",), "NT": ("CAD", "AUD")}


def currency_from_text(text: str) -> tuple[str, str]:
    """(currency, the clues) when the receipt's text points clearly to one currency, else ("", "")."""
    score: dict[str, int] = {}
    why: dict[str, list[str]] = {}

    def add(cur, n, clue):
        score[cur] = score.get(cur, 0) + n
        why.setdefault(cur, []).append(clue)

    for cur, pattern in STRONG:
        m = re.search(pattern, text or "", re.IGNORECASE if cur == "USD" else 0)
        if m:
            add(cur, 3, m.group(0).strip())
    for line in (text or "").splitlines()[:8]:  # the address is at the top
        m = re.search(r"[A-Za-z][A-Za-z ,.'-]+ ([A-Za-z]{2,3})\.?( [A-Z0-9]{3} ?[A-Z0-9]{3}| \d{4,5}(?:-\d{4})?)?\s*$", line)
        code, post = (m.group(1).upper(), (m.group(2) or "").strip()) if m else ("", "")
        if code in SHARED and re.fullmatch(r"\d{5}(-\d{4})?", post):
            code = "_US"  # a 5-digit ZIP code: the USA (Seattle WA 98101)
        elif code in SHARED and re.fullmatch(r"\d{4}", post):
            code = "_AU"  # a 4-digit postcode: Australia (Perth WA 6000)
        elif code in SHARED and re.fullmatch(r"[A-Z]\d[A-Z] ?\d[A-Z]\d", post):
            code = "ON"  # a Canadian postal code (Yellowknife NT X1A 2P4): counts as a province
        if code == "_US":
            add("USD", 2, line.strip())
            continue
        if code == "_AU":
            add("AUD", 2, line.strip())
            continue
        if code in PROVINCES.split():
            add("CAD", 2, line.strip())
        elif code in AU_STATES.split():
            add("AUD", 2, line.strip())
        elif code in SHARED:
            for cur in SHARED[code]:
                add(cur, 1, line.strip())
        elif code in US_STATES.split():
            add("USD", 2, line.strip())
    if not score:
        return "", ""
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    if ranked[0][1] < 2 or (len(ranked) > 1 and ranked[1][1] >= ranked[0][1]):
        return "", ""
    return ranked[0][0], "; ".join(dict.fromkeys(why[ranked[0][0]]))[:80]


def fix_currency(r: dict, text: str) -> list[str]:
    """The receipt's own clues decide its currency when they are clear."""
    cur, clues = currency_from_text(text)
    if not cur or str(r.get("currency", "")).upper() == cur:
        return []
    before, r["currency"] = r.get("currency"), cur
    return [f"currency {cur} from the receipt's own clues ({clues}); the model said {before}"]


DAY_FIRST = {"EUR", "GBP", "INR", "AUD", "NZD", "CHF", "SEK", "NOK", "DKK", "ZAR", "SGD"}
MONTH_FIRST = {"USD"}


def fix_date(r: dict) -> list[str]:
    """The date in YYYY-MM-DD, worked out by code from the date as printed: a number over 12 must be the
    day; otherwise the country's order (day first in Europe, India, Australia...; month first in the
    USA). Canada uses both: there the model's own reading stands unless a number over 12 decides it.
    A two-digit year is 20YY. Returns notes on what was changed."""
    printed = str(r.get("date_printed") or "").strip()
    m = re.fullmatch(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2}|\d{4})", printed)
    if not m:
        return []
    a, b, y = int(m[1]), int(m[2]), int(m[3])
    y = 2000 + y if y < 100 else y
    if a > 12 and b <= 12:
        day, month = a, b
    elif b > 12 and a <= 12:
        day, month = b, a
    elif str(r.get("currency", "")).upper() in DAY_FIRST:
        day, month = a, b
    elif str(r.get("currency", "")).upper() in MONTH_FIRST:
        day, month = b, a
    else:
        return []  # ambiguous, and a country that writes both: the model's reading stands
    try:
        iso = dt.date(y, month, day).isoformat()
    except ValueError:
        return []
    if iso == str(r.get("date", "")):
        return []
    before, r["date"] = r.get("date"), iso
    return [f"date {iso} from \"{printed}\" as printed (the model said {before})"]


INCLUDED = re.compile(r"(?im)^.*\b(?:MwSt|USt|VAT|GST|TVA|IVA|BTW|tax)\b.*\b(?:incl\.?|included|inkl\.?|inclus\w*|TTC)(?:\W|$)")


def problems(r: dict, today: dt.date | None = None, file_day: dt.date | None = None, text: str = "") -> list[str]:
    """Everything that doesn't add up (empty: the receipt checks out). file_day: when the photo was taken
    (or the file saved): a receipt dated much earlier usually means a misread year ("26" read as 2023).
    text: the receipt's own text, when there is one, for what it says about the tax and the date."""
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
        elif file_day and (file_day - day).days > 400:
            found.append(f"date {day} is {(file_day - day).days // 365} year(s) before this photo or file ({file_day}):"
                         " check the year")  # fmt: skip
    except ValueError:
        found.append(f"date '{r.get('date', '')}' isn't a date (YYYY-MM-DD)")
    printed = str(r.get("date_printed") or "").strip()
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", printed)
    if m:  # printed year first: no doubt about the order, so it must be a real date and the same one
        try:
            as_printed = dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
            if as_printed != str(r.get("date", "")):
                found.append(f"the date {r.get('date')} isn't the one printed ({printed}): check the date")
        except ValueError:
            found.append(f"the date as printed, {printed}, isn't a real date (a misread digit?): check the date")
    vendor = _name(r.get("vendor"))
    if not vendor:
        found.append("no shop name")
    elif any(vendor == _name(i.get("description")) for i in r.get("items") or []):
        found.append(f"the shop name '{r.get('vendor')}' is one of the items: check the shop")
    if not re.fullmatch(r"[A-Z]{3}", str(r.get("currency", ""))):
        found.append(f"currency '{r.get('currency', '')}' isn't a 3-letter code")
    items = [money(i.get("amount")) for i in r.get("items") or []]
    items_sum = round(sum(x for x in items if x is not None), 2) if items else None
    subtotal = money(r.get("subtotal"))
    taxes = round(sum(money(t.get("amount")) or 0 for t in r.get("taxes") or []), 2)
    tip = money(r.get("tip")) or 0
    # tax included in the prices: the items add up to the total, and a "subtotal" may be the amount
    # before tax (total minus the included tax), which is just as right
    net_subtotal = subtotal is not None and items_sum is not None and close(items_sum, round(subtotal + taxes, 2))
    if subtotal is not None and items_sum is not None and not close(items_sum, subtotal) and not net_subtotal:
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
    # Canadian and American receipts add tax on top of the prices; a tax "included" there is almost
    # always a number the model made up to fill the field (a tax-free grocery receipt read with tax).
    # Only a tax line that itself says "incl." is believed.
    if included and r.get("currency") in TAX_ADDED and not any(
            INCL.search(str(t.get("name", ""))) for t in r.get("taxes") or []):
        included = False
        found.append(f"tax {taxes:.2f} isn't on top of the prices, and {r['currency']} receipts don't include tax "
                     "in them: if no tax amount is printed, taxes is empty")  # fmt: skip
    elif included and total and taxes > 0.22 * total:
        included = False
        found.append(f"tax {taxes:.2f} can't be included in a total of {total:.2f} (that would be "
                     f"{100 * taxes / total:.0f}%): check the tax lines")  # fmt: skip
    elif added and base and taxes > 0.30 * base:
        found.append(f"tax {taxes:.2f} is more than 30% of {base:.2f}: check the tax lines")
    if text and taxes and total and base is not None and added and not included and INCLUDED.search(text):
        line = INCLUDED.search(text).group(0).strip()[:40]
        found.append(f"the receipt says the tax is included (\"{line}\"), but this reading adds {taxes:.2f} on "
                     "top: check the total")  # fmt: skip
    if total and base is not None and not (added or included) and not any(p.startswith("tax ") for p in found):
        found.append(f"{'subtotal' if subtotal is not None else 'items'} {base:.2f} + tax {taxes:.2f}"
                     f"{f' + tip {tip:.2f}' if tip else ''} = {base + taxes + tip:.2f}, not the total {total:.2f}")  # fmt: skip
    return found


def _name(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def checked(r: dict) -> bool:
    """True when the arithmetic could be checked at all (items or a subtotal were read)."""
    return bool(r.get("items")) or money(r.get("subtotal")) is not None
