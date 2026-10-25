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


def run(folder: Path, chat=None, today: dt.date | None = None, say=print, **kw) -> dict:
    pairs = [(f, f.with_suffix(".json")) for f in files.find([str(folder)]) if f.with_suffix(".json").exists()]
    if not pairs:
        raise SystemExit(f"No receipts with answer files (<name>.json) in {folder}. Make some: receipt-reader samples {folder}")
    rows = []
    for n, (f, answer) in enumerate(pairs, 1):
        truth = json.loads(answer.read_text())
        try:
            got = reader.read(f, chat=chat, today=today, **kw)
        except Exception as e:  # noqa: BLE001 - one failure is counted, not fatal
            got = {"status": "check", "problems": [f"error: {e}"], "seconds": 0}
        right = compare(got, truth)
        rows.append({"file": f.name, "right": right, "status": got["status"], "seconds": got.get("seconds", 0)})
        say(f"[{n}/{len(pairs)}] {f.name}: {'all right' if all(right.values()) else 'wrong ' + ', '.join(k for k, v in right.items() if not v)}"
            f" (status {got['status']}, {got.get('seconds', 0)}s)")  # fmt: skip
    return summary(rows)


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    wrong = [r for r in rows if not all(r["right"].values())]
    out = {"receipts": n,
           "fields": {k: sum(r["right"][k] for r in rows) for k in FIELDS},
           "all_right": n - len(wrong),
           "wrong": len(wrong),
           "wrong_but_flagged": sum(r["status"] == "check" for r in wrong),
           "right_but_flagged": sum(r["status"] == "check" for r in rows if all(r["right"].values())),
           "seconds_each": round(sum(r["seconds"] for r in rows) / n, 1)}  # fmt: skip
    return out


def report(s: dict) -> str:
    n = s["receipts"]
    lines = [f"Receipts: {n}", ""] + [f"  {k:<9} {v}/{n} right ({100 * v / n:.0f}%)" for k, v in s["fields"].items()]
    lines += ["", f"All five fields right: {s['all_right']}/{n} ({100 * s['all_right'] / n:.0f}%)"]
    if s["wrong"]:
        lines.append(f"Of the {s['wrong']} with a mistake, the arithmetic check flagged {s['wrong_but_flagged']} for you to check.")
    lines.append(f"Correct ones flagged anyway (extra work, not errors): {s['right_but_flagged']}")
    lines.append(f"Time: {s['seconds_each']} seconds a receipt on this computer")
    return "\n".join(lines)
