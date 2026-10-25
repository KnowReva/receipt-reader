"""Writing the results: one row per receipt, and optionally one row per line item."""

import csv
import json
from pathlib import Path

from .checks import money

COLUMNS = ["file", "status", "problems", "date", "vendor", "category", "currency", "subtotal", "tax", "tip",
           "total", "payment_method", "notes"]  # fmt: skip


def row(r: dict) -> dict:
    tax = round(sum(money(t.get("amount")) or 0 for t in r.get("taxes") or []), 2)
    return {"file": r["file"], "status": r["status"], "problems": "; ".join(r.get("problems", [])),
            "date": r.get("date", ""), "vendor": r.get("vendor", ""), "category": r.get("category", ""),
            "currency": r.get("currency", ""), "subtotal": money(r.get("subtotal")) if r.get("subtotal") is not None else "",
            "tax": tax if r.get("taxes") else "", "tip": money(r.get("tip")) if r.get("tip") is not None else "",
            "total": money(r.get("total")), "payment_method": r.get("payment_method", ""),
            "notes": "; ".join(r.get("notes") or [])}  # fmt: skip


def write_csv(results: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in results:
            w.writerow(row(r))


def write_items(results: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "description", "quantity", "amount"])
        for r in results:
            for i in r.get("items") or []:
                w.writerow([r["file"], i.get("description", ""), i.get("quantity", ""), money(i.get("amount"))])


def write_json(results: list[dict], path: Path) -> None:
    path.write_text(json.dumps(results, indent=1, ensure_ascii=False))
