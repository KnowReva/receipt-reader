# Changes

## 0.3.5 (October 2026)

From the second `eval --fast` run (0.3.4: 26/30 all right, every total right, 47 s a receipt):
- "GST incl." is a clue for AUD (Canada adds its GST on top; the USA has none). The 4 misses were
  Australian receipts whose only clue it was; replayed, 3 right and 1 CHECK.
- No false alarm on VAT receipts that print a subtotal before tax: when the items add up to the
  total, the tax is in them, as printed (3 right readings had been flagged).
- A receipt that prints an included tax while the reading has none is marked CHECK.

## 0.3.4 (October 2026)

From `eval --fast --details` on the practice set (12 wrong, none flagged), two more checks:
- a receipt that says its tax is included ("MwSt 7% incl.", "GST incl.") but a reading that adds it on
  top is marked CHECK (and with --fast, read again from the picture);
- a date printed year first must be a real date, and the same one: "2026-05-97" (a misread 07) is CHECK.
Replayed with the receipts' own clues, those 12 readings now come out 9 right and 3 flagged, none wrong
(tests/data/why-fast-2026-10-26.json).

## 0.3.3 (October 2026)

- The receipt's own clues decide its currency when they are clear: a province or state code after the
  city (with the postcode for WA, NT, SA), and tax names only one country uses (GST/HST, TPS/TVQ, ABN,
  MwSt, CGST, Rs...). From the PDF's text, or the photo's (Tesseract, when installed). In the --fast
  run, 11 of the 12 wrong receipts had the wrong currency; these clues alone get all 30 practice
  receipts right. The date order is then worked out from the corrected currency.
- `RECEIPT_KEEP_ALIVE` (e.g. 5m): how long Ollama keeps the model after a receipt; and the README says
  how to take turns with other AI jobs on the same computer (flock on Dhoon's queue).

## 0.3.2 (October 2026)

- The context window is no longer sent by default. Asking for 8192 on every request made Ollama reload
  the whole model whenever its server ran with another size (Dhoon's runs with 16-32k), and again for
  the other programs sharing it: minutes per receipt. `RECEIPT_CONTEXT` sets one when you need it.

## 0.3.1 (October 2026)

- Dates are put in order by code from the date as printed (a new field, `date_printed`): a number over 12
  must be the day; otherwise day first in Europe, India and Australia, month first in the USA; in
  Canada the model's reading stands. Fixes "28/07/2026" left unconverted and Australian dates read in
  US order.
- `eval --details why.json` saves each wrong reading next to the right answer.
- `eval --fast` counted text PDFs (always read as text) as read from recognised text.

## 0.3.0 (October 2026)

- `--fast`: Tesseract reads a photo's text first (under a second); the model turns the text into fields,
  optionally a smaller one (`--text-model`). A reading that doesn't add up is read from the picture.
  `eval --fast` reports how many were read from the text alone and how accurately.
- `receipt-reader learn receipts.csv`: remembers the shop names and categories you corrected; a small
  naive Bayes model learns your categories once there are enough corrections. Changes are noted.

## 0.2.0 (October 2026)

What testing on a real receipt taught (see the README's "Our results"):

- Phone scanner PDFs (Adobe Scan, Microsoft Lens) are read from the picture, not from the app's guessed text.
- A shop name that matches one of the items gets a second look.
- A tax "included in the prices" on a CAD or USD receipt is flagged unless the receipt says "incl.";
  a tax the items, subtotal and total leave no room for is removed with a note.
- A broken or cut-off answer from the model gets the one second look; the context window is 8192 tokens
  (`RECEIPT_CONTEXT`).
- iPhone photos (HEIC) are read directly.
- No tax is written as 0, not blank.
- Exactly two cents counts as two cents in floating point.

## 0.1.0 (October 2026)

First release: photos and PDFs to a CSV, structured outputs, arithmetic checks, one second look,
30 practice receipts and `eval`, registration numbers dropped, tax limits, two-digit years checked
against the photo date, `--currency`.
