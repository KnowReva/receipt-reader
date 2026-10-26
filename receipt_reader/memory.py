"""Learning from your corrections: the shop names and categories you fix in the spreadsheet.

  receipt-reader scan ~/Receipts -o receipts.csv     the readings are also kept, to compare with later
  (fix a shop or a category in receipts.csv, save it)
  receipt-reader learn receipts.csv                  remember every change you made

Next time, a shop you corrected gets your name for it ("WAL-MART #1007" -> "Walmart"), and a shop you
gave a category gets that category. For shops it hasn't seen, a small word-counting model (naive Bayes,
about 30 lines) learns your categories from shop names and items once you have corrected enough, and
changes the model's guess only when it is sure. Every change says so in the notes column. Nothing leaves
your computer: the memory is one JSON file (~/.receipt-reader/memory.json, or RECEIPT_MEMORY)."""

import csv
import difflib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

MIN_EXAMPLES = 15  # corrections before the word model may change a category
SURE = 0.8


def home() -> Path:
    return Path(os.environ.get("RECEIPT_MEMORY", Path.home() / ".receipt-reader" / "memory.json"))


def _readings() -> Path:
    return home().with_name("last-readings.json")


def norm(name) -> str:
    """"WAL-MART #1007" and "Wal-Mart Store 1007" -> "wal mart" (no numbers, signs or store words)."""
    words = re.findall(r"[a-z]+", str(name or "").lower())
    return " ".join(w for w in words if w not in {"store", "inc", "ltd", "llc", "the", "co"})


def _words(r: dict) -> list[str]:
    text = " ".join([str(r.get("vendor", ""))] + [str(i.get("description", "")) for i in r.get("items") or []])
    return [w for w in re.findall(r"[a-z]{3,}", text.lower())]


def load() -> dict:
    try:
        m = json.loads(home().read_text())
    except (OSError, ValueError):
        m = {}
    return {"vendors": m.get("vendors", {}), "categories": m.get("categories", {}), "examples": m.get("examples", [])}


def save(m: dict) -> None:
    home().parent.mkdir(parents=True, exist_ok=True)
    home().write_text(json.dumps(m, indent=1, ensure_ascii=False))


def keep_readings(results: list[dict]) -> None:
    """What the model read, by file, so `learn` can see what you changed."""
    data = {r["file"]: {"vendor": r.get("vendor", ""), "category": r.get("category", ""), "words": _words(r)}
            for r in results if r.get("file")}  # fmt: skip
    _readings().parent.mkdir(parents=True, exist_ok=True)
    _readings().write_text(json.dumps(data, ensure_ascii=False))


def learn(csv_path: Path) -> str:
    """Compare your edited spreadsheet with what was read, and remember the changes."""
    try:
        read = json.loads(_readings().read_text())
    except (OSError, ValueError):
        return "Nothing to compare with: scan your receipts first (receipt-reader scan ... -o receipts.csv)."
    m, shops, cats = load(), 0, 0
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        before = read.get(row.get("file", ""))
        if not before:
            continue
        vendor, category = row.get("vendor", "").strip(), row.get("category", "").strip()
        if vendor and norm(vendor) != norm(before["vendor"]) and norm(before["vendor"]):
            m["vendors"][norm(before["vendor"])] = vendor
            shops += 1
        if category and category != before["category"]:
            m["categories"][norm(vendor or before["vendor"])] = category
            cats += 1
        if category:  # every row you saved is an example of your categories, changed or not
            m["examples"].append([before["words"], category])
    m["examples"] = m["examples"][-2000:]
    save(m)
    return (f"Remembered {shops} shop name(s) and {cats} category change(s) from {csv_path.name} "
            f"({len(m['examples'])} examples of your categories so far). Saved in {home()}.")  # fmt: skip


def _bayes(examples: list, words: list[str]) -> tuple[str, float]:
    """Naive Bayes over your examples: the likeliest category for these words, and how sure (0-1)."""
    counts: dict[str, Counter] = {}
    for ws, cat in examples:
        counts.setdefault(cat, Counter()).update(ws)
    vocab = {w for c in counts.values() for w in c}
    total = sum(1 for _ in examples)
    score = {}
    for cat, c in counts.items():
        prior = sum(1 for _, k in examples if k == cat) / total
        n = sum(c.values())
        score[cat] = math.log(prior) + sum(math.log((c[w] + 1) / (n + len(vocab))) for w in words if w in vocab)
    best = max(score, key=score.get)
    z = sum(math.exp(v - score[best]) for v in score.values())
    return best, 1 / z


def apply(r: dict, m: dict | None = None) -> dict:
    """Your shop names and categories on a reading, each change noted."""
    m = m or load()
    if not (m["vendors"] or m["categories"] or m["examples"]):
        return r
    notes = r.setdefault("notes", [])
    key = norm(r.get("vendor"))
    match = m["vendors"].get(key) or next((m["vendors"][k] for k in difflib.get_close_matches(key, list(m["vendors"]),
                                           n=1, cutoff=0.9)), None)  # fmt: skip
    if match and match != r.get("vendor"):
        notes.append(f"shop \"{r.get('vendor')}\" written as \"{match}\", as you corrected it before")
        r["vendor"] = match
    category = m["categories"].get(norm(r.get("vendor")))
    if category and category != r.get("category"):
        notes.append(f"category {category} (you chose it for this shop before; the model said {r.get('category')})")
        r["category"] = category
    elif not category and len(m["examples"]) >= MIN_EXAMPLES:
        guess, sure = _bayes(m["examples"], _words(r))
        if guess != r.get("category") and sure >= SURE:
            notes.append(f"category {guess} (learned from your {len(m['examples'])} corrections, {sure:.0%} sure; "
                         f"the model said {r.get('category')})")  # fmt: skip
            r["category"] = guess
    return r
