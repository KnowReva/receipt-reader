"""receipt-reader on the command line.

  receipt-reader scan receipts/ -o receipts.csv [--items items.csv] [--json all.json]
  receipt-reader eval samples/          accuracy on receipts with answer files
  ... --fast [--text-model qwen3:4b]    read photos' text with Tesseract first (much faster on a CPU)
  receipt-reader learn receipts.csv     remember your corrections to shops and categories
  receipt-reader samples samples/       draw 30 practice receipts with their answers
"""

import argparse
import sys
from pathlib import Path

from . import __version__, evaluate, files, memory, model, output, reader, samples


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="receipt-reader", description="Receipts and invoices to a spreadsheet, "
                                "read by an AI model on your own computer (Ollama).")  # fmt: skip
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="read receipts (photos or PDFs, files or folders) into a CSV")
    scan.add_argument("paths", nargs="+")
    scan.add_argument("-o", "--output", default="receipts.csv")
    scan.add_argument("--items", help="also write every line item to this CSV")
    scan.add_argument("--json", help="also write everything, line items included, to this JSON file")
    ev = sub.add_parser("eval", help="measure accuracy on receipts that have answer files (<name>.json)")
    ev.add_argument("folder")
    le = sub.add_parser("learn", help="remember the shop names and categories you corrected in a scanned CSV")
    le.add_argument("csv")
    sm = sub.add_parser("samples", help="draw practice receipts with their answers")
    sm.add_argument("folder")
    sm.add_argument("--count", type=int, default=30)
    for s in (scan, ev):
        s.add_argument("--currency", default="", help="your usual currency (e.g. CAD), for receipts that only print $")
        s.add_argument("--model", default=model.DEFAULT_MODEL, help=f"Ollama model (default {model.DEFAULT_MODEL})")
        s.add_argument("--url", default=model.DEFAULT_URL, help=f"Ollama address (default {model.DEFAULT_URL})")
        s.add_argument("--fast", action="store_true", help="read photos' text with Tesseract first; the picture only "
                       "when that doesn't add up (needs tesseract-ocr and pytesseract)")  # fmt: skip
        s.add_argument("--text-model", default="", help="with --fast: a smaller model for turning text into fields")
    a = p.parse_args(argv)

    if a.command == "samples":
        made = samples.write(Path(a.folder), a.count)
        print(f"{len(made)} practice receipts with answers in {a.folder}/. Now: receipt-reader eval {a.folder}")
        return 0
    if a.command == "learn":
        print(memory.learn(Path(a.csv)))
        return 0
    if a.command == "eval":
        if a.fast and not _has_tesseract():
            print("--fast needs Tesseract: sudo apt install tesseract-ocr (macOS: brew install tesseract), "
                  "then pip install pytesseract")  # fmt: skip
            return 1
        print(evaluate.report(evaluate.run(Path(a.folder), model=a.model, url=a.url, currency=a.currency,
                                           fast=a.fast, text_model=a.text_model)))  # fmt: skip
        return 0

    if a.fast and not _has_tesseract():
        print("--fast needs Tesseract: sudo apt install tesseract-ocr (macOS: brew install tesseract), "
              "then pip install pytesseract")  # fmt: skip
        return 1
    paths = files.find(a.paths)
    if not paths:
        print("No photos or PDFs found there.")
        return 1
    results = []
    for n, path in enumerate(paths, 1):
        try:
            r = reader.read(path, model=a.model, url=a.url, currency=a.currency, fast=a.fast, text_model=a.text_model)
        except model.ModelError as e:  # Ollama isn't running, or the model isn't there: stop with the fix
            print(f"Stopped: {e}")
            return 1
        except Exception as e:  # noqa: BLE001 - one unreadable file doesn't stop the others
            r = {"file": str(path), "status": "check", "problems": [f"couldn't read it: {e}"]}
        results.append(r)
        print(f"[{n}/{len(paths)}] {path.name}: {r.get('vendor', '?')} {r.get('total', '')} {r.get('currency', '')}"
              f" {'OK' if r['status'] == 'ok' else 'CHECK: ' + '; '.join(r['problems'])}")  # fmt: skip
    output.write_csv(results, Path(a.output))
    memory.keep_readings(results)  # so `receipt-reader learn` can see what you change
    if a.items:
        output.write_items(results, Path(a.items))
    if a.json:
        output.write_json(results, Path(a.json))
    to_check = sum(r["status"] == "check" for r in results)
    print(f"\n{len(results)} receipts in {a.output}" + (f"; {to_check} marked CHECK (see the problems column)" if to_check else ""))
    return 0


def _has_tesseract() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    sys.exit(main())
