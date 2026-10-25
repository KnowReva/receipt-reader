# Changes

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
