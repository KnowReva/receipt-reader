"""Measuring accuracy: read every receipt that has an answer file (<name>.json) and compare.

Fields compared: date, total and tax exactly (to the cent), currency, vendor (allowing small
spelling differences). The most useful number is the last one: of the receipts the model got
wrong, how many did the arithmetic check flag for you? Those are the ones that can't slip through."""

import datetime as dt
import difflib
import json
import re
from pathlib import Path

from . import files, reader
from .checks import money

FIELDS = ["date", "total", "tax", "currency", "vendor"]


def _vendor(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def compare(got: dict, truth: dict) -> dict[str, bool]:
    def tax(r):
        return round(sum(money(t.get("amount")) or 0 for t in r.get("taxes") or []), 2)

    return {
        "date": str(got.get("date")) == truth["date"],
        "total": money(got.get("total")) == money(truth["total"]),
        "tax": tax(got) == tax(truth),
        "currency": str(got.get("currency", "")).upper() == truth["currency"],
        "vendor": difflib.SequenceMatcher(None, _vendor(got.get("vendor")), _vendor(truth["vendor"])).ratio() >= 0.85,
    }


def run(folder: Path, chat=None, today: dt.date | None = None, say=print, details: Path | None = None, **kw) -> dict:
    pairs = [(f, f.with_suffix(".json")) for f in files.find([str(folder)]) if f.with_suffix(".json").exists()]
    if not pairs:
        raise SystemExit(f"No receipts with answer files (<name>.json) in {folder}. Make some: receipt-reader samples {folder}")
    rows, wrong = [], []
    for n, (f, answer) in enumerate(pairs, 1):
        truth = json.loads(answer.read_text())
        error = ""
        try:
            got = reader.read(f, chat=chat, today=today, remember=False, **kw)  # the model alone
        except Exception as e:  # noqa: BLE001 - one failure is counted, not fatal
            got, error = {"status": "check", "problems": [f"error: {e}"], "seconds": 0}, f"{type(e).__name__}: {e}"
        right = compare(got, truth)
        if details and not all(right.values()):  # what was read next to the right answer, to see why
            wrong.append({"file": f.name, "wrong": [k for k, v in right.items() if not v], "read": got, "answer": truth})
        rows.append({"file": f.name, "right": right, "status": got["status"], "seconds": got.get("seconds", 0),
                     "error": error, "read_by": got.get("read_by", "")})  # fmt: skip
        if error:
            say(f"[{n}/{len(pairs)}] {f.name}: COULDN'T READ IT ({error[:200]})")
        else:
            why = f": {'; '.join(got.get('problems', []))[:160]}" if got["status"] == "check" else ""
            say(f"[{n}/{len(pairs)}] {f.name}: {'all right' if all(right.values()) else 'wrong ' + ', '.join(k for k, v in right.items() if not v)}"
                f" (status {got['status']}{why}, {got.get('seconds', 0)}s)")  # fmt: skip
    if details:
        details.write_text(json.dumps(wrong, indent=1, ensure_ascii=False, default=str))
        say(f"The {len(wrong)} wrong reading(s), next to the right answers: {details}")
    return summary(rows)


def summary(rows: list[dict]) -> dict:
    failed = [r for r in rows if r.get("error")]
    rows = [r for r in rows if not r.get("error")]  # accuracy is measured on what was read
    if not rows:
        return {"receipts": 0, "errors": len(failed), "error_examples": [r["error"] for r in failed[:3]]}
    n = len(rows)
    wrong = [r for r in rows if not all(r["right"].values())]
    out = {"receipts": n,
           "fields": {k: sum(r["right"][k] for r in rows) for k in FIELDS},
           "all_right": n - len(wrong),
           "wrong": len(wrong),
           "wrong_but_flagged": sum(r["status"] == "check" for r in wrong),
           "right_but_flagged": sum(r["status"] == "check" for r in rows if all(r["right"].values())),
           "seconds_each": round(sum(r["seconds"] for r in rows) / n, 1),
           "by_text": sum(r.get("read_by") == "recognised text" for r in rows),
           "by_text_right": sum(r.get("read_by") == "recognised text" and all(r["right"].values()) for r in rows),
           "errors": len(failed), "error_examples": [r["error"] for r in failed[:3]]}  # fmt: skip
    return out


def report(s: dict) -> str:
    n = s["receipts"]
    errors = [f"Couldn't read {s['errors']} (errors, not misreadings): " + " | ".join(e[:120] for e in s["error_examples"])] if s.get("errors") else []
    if not n:
        return "\n".join(errors or ["Nothing was read."])
    lines = [f"Receipts read: {n}", *errors, ""] + [f"  {k:<9} {v}/{n} right ({100 * v / n:.0f}%)" for k, v in s["fields"].items()]
    lines += ["", f"All five fields right: {s['all_right']}/{n} ({100 * s['all_right'] / n:.0f}%)"]
    if s["wrong"]:
        lines.append(f"Of the {s['wrong']} with a mistake, the arithmetic check flagged {s['wrong_but_flagged']} for you to check.")
    lines.append(f"Correct ones flagged anyway (extra work, not errors): {s['right_but_flagged']}")
    if s.get("by_text"):
        lines.append(f"Read from the recognised text alone (--fast): {s['by_text']}/{n}, all five fields right on "
                     f"{s['by_text_right']} of them; the rest were read from the picture")  # fmt: skip
    lines.append(f"Time: {s['seconds_each']} seconds a receipt on this computer")
    return "\n".join(lines)
