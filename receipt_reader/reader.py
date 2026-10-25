"""Reading one receipt: ask the model, check the answer, and ask once more if it doesn't add up."""

import datetime as dt
import json
import time
from pathlib import Path

from . import checks, files, model
from .schema import PROMPT, SCHEMA


# Ollama's documentation advises giving the schema in the prompt too, "to ground the model's response".
SCHEMA_TEXT = "\n\nAnswer with JSON that matches this schema:\n" + json.dumps(SCHEMA)


def ask(content: dict, extra: str = "", chat=None, **kw) -> dict:
    chat = chat or model.chat
    extra = SCHEMA_TEXT + extra
    if "text" in content:
        message = {"role": "user", "content": f"{PROMPT}{extra}\n\nTHE RECEIPT (text from a PDF):\n{content['text'][:12000]}"}
    else:
        message = {"role": "user", "content": PROMPT + extra, "images": content["images"]}
    return chat([message], SCHEMA, **kw)


def read(path: Path, chat=None, today: dt.date | None = None, **kw) -> dict:
    """The receipt's details plus: file, status ("ok" or "check"), problems, seconds."""
    began = time.monotonic()
    content = files.load(path)
    r = ask(content, chat=chat, **kw)
    found = checks.problems(r, today)
    if found:  # one second look, told exactly what didn't add up
        hint = ("\n\nA first reading had these problems: " + "; ".join(found)
                + ". Look again carefully at each number on the receipt.")  # fmt: skip
        again = ask(content, hint, chat=chat, **kw)
        again_found = checks.problems(again, today)
        if len(again_found) < len(found):
            r, found = again, again_found
    if not found and not checks.checked(r):
        found = ["no items or subtotal read, so the total couldn't be checked"]
    return {"file": str(path), **r, "status": "check" if found else "ok", "problems": found,
            "seconds": round(time.monotonic() - began, 1)}  # fmt: skip
