"""Reading one receipt: ask the model, check the answer, and ask once more if it doesn't add up."""

import datetime as dt
import json
import re
import time
from pathlib import Path

from . import checks, files, memory, model
from .schema import PROMPT, SCHEMA


# Ollama's documentation advises giving the schema in the prompt too, "to ground the model's response".
SCHEMA_TEXT = "\n\nAnswer with JSON that matches this schema:\n" + json.dumps(SCHEMA)


def ask(content: dict, extra: str = "", chat=None, currency: str = "", **kw) -> dict:
    chat = chat or model.chat
    hint = (f"\nIf the receipt doesn't make the currency clear (a plain \"$\" with no country), it is {currency}."
            if currency else "")  # fmt: skip
    extra = hint + SCHEMA_TEXT + extra
    if "text" in content:
        where = ("text a text-recognition program read from a photo; it can misread a character, so copy numbers "
                 "only as they appear" if content.get("recognised") else "text from a PDF")  # fmt: skip
        message = {"role": "user", "content": f"{PROMPT}{extra}\n\nTHE RECEIPT ({where}):\n{content['text'][:12000]}"}
    else:
        hint = ("\n\nTEXT A SCANNER APP GUESSED FROM THIS PHOTO (it misreads letters and digits, and mixes in ads "
                "and survey text: trust the image, use this only to help read it):\n" + content["scan_text"][:6000]
                if content.get("scan_text") else "")  # fmt: skip
        message = {"role": "user", "content": PROMPT + extra + hint, "images": content["images"]}
    return chat([message], SCHEMA, **kw)


def read(path: Path, chat=None, today: dt.date | None = None, currency: str = "", fast: bool = False,
         text_model: str = "", remember: bool = True, **kw) -> dict:  # fmt: skip
    """The receipt's details plus: file, status ("ok" or "check"), problems, seconds, read_by.
    currency: your usual currency (e.g. CAD), for receipts that only print "$".
    fast: for photos and scanned pages, Tesseract reads the text first and the model only turns that text
    into fields (text_model, if given, a smaller model for that); when the result adds up, that's it.
    When it doesn't, the picture is read as usual. Wrong text can't slip through: it has to add up.
    remember: apply the shop names and categories you corrected before (memory.py); off for eval."""
    began = time.monotonic()
    currency = currency.strip().upper()
    content = files.load(path)
    file_day = files.taken_on(path)

    if fast and "images" in content:
        text = files.recognise(path)
        if text and len(text) > 40:
            quick = {"text": text, "recognised": True}
            try:
                r = ask(quick, chat=chat, currency=currency, **(dict(kw, model=text_model) if text_model else kw))
                if currency and not re.fullmatch(r"[A-Z]{3}", str(r.get("currency", "")).strip().upper()):
                    r["currency"] = currency
                r["notes"] = checks.drop_impossible_taxes(r) + checks.drop_unprinted_tax(r) + checks.fix_date(r)
                found = checks.problems(r, today, file_day)
            except model.BadAnswer:
                found, r = ["broken answer"], {}
            if not found and checks.checked(r):
                if remember:
                    memory.apply(r)
                return {"file": str(path), **r, "status": "ok", "problems": [], "read_by": "recognised text",
                        "seconds": round(time.monotonic() - began, 1)}  # fmt: skip

    def look(extra: str = "") -> tuple[dict, list[str]]:
        r = ask(content, extra, chat=chat, currency=currency, **kw)
        if currency and not re.fullmatch(r"[A-Z]{3}", str(r.get("currency", "")).strip().upper()):
            r["currency"] = currency  # "$" or "" read: your usual currency
        r["notes"] = checks.drop_impossible_taxes(r)  # registration numbers read as tax
        r["notes"] += checks.fix_date(r)  # the printed date, put in order by code
        r["notes"] += checks.drop_unprinted_tax(r)  # a tax the receipt's own numbers leave no room for
        return r, checks.problems(r, today, file_day)

    try:
        r, found = look()
    except model.BadAnswer as e:  # broken or cut-off JSON: the second look below gets the chance
        r, found = None, [str(e)]
    if found:  # one second look: a new, single-message request, told exactly what didn't add up
        hint = ("\n\nA first reading had these problems: " + "; ".join(found)
                + ". Look again carefully at each number on the receipt.")  # fmt: skip
        try:
            again, again_found = look(hint)
        except model.BadAnswer:
            if r is None:
                raise
        else:
            if r is None or len(again_found) < len(found):
                r, found = again, again_found
    if not found and not checks.checked(r):
        found = ["no items or subtotal read, so the total couldn't be checked"]
    if remember:
        memory.apply(r)
    return {"file": str(path), **r, "status": "check" if found else "ok", "problems": found,
            "read_by": "picture" if "images" in content else "text", "seconds": round(time.monotonic() - began, 1)}  # fmt: skip
