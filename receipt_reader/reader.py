"""Reading one receipt: ask the model, check the answer, and ask once more if it doesn't add up."""

import datetime as dt
import json
import re
import time
from pathlib import Path

from . import checks, files, model
from .schema import PROMPT, SCHEMA


# Ollama's documentation advises giving the schema in the prompt too, "to ground the model's response".
SCHEMA_TEXT = "\n\nAnswer with JSON that matches this schema:\n" + json.dumps(SCHEMA)


def ask(content: dict, extra: str = "", chat=None, currency: str = "", **kw) -> dict:
    chat = chat or model.chat
    hint = (f"\nIf the receipt doesn't make the currency clear (a plain \"$\" with no country), it is {currency}."
            if currency else "")  # fmt: skip
    extra = hint + SCHEMA_TEXT + extra
    if "text" in content:
        message = {"role": "user", "content": f"{PROMPT}{extra}\n\nTHE RECEIPT (text from a PDF):\n{content['text'][:12000]}"}
    else:
        message = {"role": "user", "content": PROMPT + extra, "images": content["images"]}
    return chat([message], SCHEMA, **kw)


def read(path: Path, chat=None, today: dt.date | None = None, currency: str = "", **kw) -> dict:
    """The receipt's details plus: file, status ("ok" or "check"), problems, seconds.
    currency: your usual currency (e.g. CAD), for receipts that only print "$"."""
    began = time.monotonic()
    currency = currency.strip().upper()
    content = files.load(path)
    file_day = files.taken_on(path)

    def look(extra: str = "") -> tuple[dict, list[str]]:
        r = ask(content, extra, chat=chat, currency=currency, **kw)
        if currency and not re.fullmatch(r"[A-Z]{3}", str(r.get("currency", "")).strip().upper()):
            r["currency"] = currency  # "$" or "" read: your usual currency
        r["notes"] = checks.drop_impossible_taxes(r)  # registration numbers read as tax
        return r, checks.problems(r, today, file_day)

    r, found = look()
    if found:  # one second look, told exactly what didn't add up
        again, again_found = look("\n\nA first reading had these problems: " + "; ".join(found)
                                  + ". Look again carefully at each number on the receipt.")  # fmt: skip
        if len(again_found) < len(found):
            r, found = again, again_found
    if not found and not checks.checked(r):
        found = ["no items or subtotal read, so the total couldn't be checked"]
    return {"file": str(path), **r, "status": "check" if found else "ok", "problems": found,
            "seconds": round(time.monotonic() - began, 1)}  # fmt: skip
