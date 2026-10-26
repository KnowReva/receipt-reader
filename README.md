# receipt-reader

Receipts and invoices to a spreadsheet, read by an AI model **on your own computer**. Photos and
PDFs go in; a CSV with the date, shop, category, tax and total comes out. Nothing is uploaded
anywhere, and nothing costs money per receipt.

```
$ receipt-reader scan ~/Receipts -o receipts.csv
[1/3] IMG_2041.jpg: Maple Corner Grocery 17.26 CAD OK
[2/3] IMG_2042.jpg: Blue Kettle Diner 48.10 CAD OK
[3/3] invoice-118.pdf: Papeterie Lefevre 23.40 EUR CHECK: items add up to 21.40, not the total 23.40

3 receipts in receipts.csv; 1 marked CHECK (see the problems column)
```

A [KnowReva](https://knowreva.com) open-source project. The guide
[Build a receipt reader with a local AI model](https://knowreva.com/guides/) explains every part of
the code step by step.

## Why it can be trusted

The model reads each receipt into a fixed set of fields (Ollama's structured outputs), and then
**code checks the arithmetic**: the line items must add up to the subtotal, and subtotal + tax +
tip must equal the total. VAT and GST already included in the prices also count. When a receipt
doesn't add up, the model gets one more look, told exactly what was wrong. If it still doesn't
add up, the row is marked `CHECK` with the reason, so a misread number never slips quietly into
your spreadsheet.

You can measure the accuracy yourself on your own computer (see [Measure it](#measure-it)).

## Install

You need [Ollama](https://ollama.com) and Python 3.10 or newer.

```bash
ollama pull qwen2.5vl:7b          # the model that reads the receipts (6 GB download, Ollama 0.7.0+)
pip install git+https://github.com/knowreva/receipt-reader
```

On a smaller computer (8 GB of memory), `qwen2.5vl:3b` (3.2 GB) is faster but less accurate. Use
it with `--model qwen2.5vl:3b`.

## Use

```bash
receipt-reader scan photo.jpg invoice.pdf          # files
receipt-reader scan ~/Receipts -o receipts.csv     # a whole folder (and its subfolders)
receipt-reader scan ~/Receipts --items items.csv   # also every line item, one per row
receipt-reader scan ~/Receipts --json all.json     # everything, for your own scripts
receipt-reader scan ~/Receipts --currency CAD      # your usual currency, for receipts that only print "$"
```

| Column | |
|---|---|
| `status` | `ok`: the numbers add up. `check`: look at this one (the `problems` column says why) |
| `date` | YYYY-MM-DD |
| `vendor`, `category` | category is one of groceries, restaurant, fuel, travel, office, utilities, health, other |
| `currency`, `subtotal`, `tax`, `tip`, `total` | tax is all tax lines added together |
| `payment_method` | as printed (card, cash...) |
| `notes` | anything code corrected by itself, e.g. a store's tax registration number the model read as a tax |

Photos: JPG, PNG, WEBP, TIFF, HEIC. PDFs: invoices with real text are read as text (fast and exact);
scanned PDFs are read page by page as images (up to 3 pages). PDFs from phone scanner apps (Adobe Scan,
Microsoft Lens...) carry text the app guessed from the photo, with mistakes, so they are read as images
too, with that text as a hint. iPhone photos (HEIC) are read as they are.

Settings: `--model` (or `RECEIPT_MODEL`), `--url` (or `OLLAMA_URL`, default
`http://localhost:11434`), `RECEIPT_CONTEXT` (the model's context window in tokens; not sent unless
set, because a size different from the server's makes Ollama reload the whole model, and again for
any other program sharing it. Set 8192 only if your Ollama runs with its default of 4096 and long
receipts get cut off).

An answer that isn't complete JSON (cut off, or broken) gets the same one second look as a receipt
that doesn't add up.

## Faster: read the text first (`--fast`)

Reading a photo with a vision model takes a minute or two on a computer without a graphics card. Text
recognition (Tesseract) reads a receipt's text in under a second. With `--fast`, Tesseract reads first
and the model only turns that text into fields, which is much quicker, even more so with a small text
model. The arithmetic check still decides: a receipt whose text reading doesn't add up is read from the
picture as usual.

```bash
sudo apt install tesseract-ocr          # macOS: brew install tesseract
pip install pytesseract                 # or: pip install "receipt-reader[fast] @ git+https://github.com/knowreva/receipt-reader"
receipt-reader scan ~/Receipts --fast
receipt-reader scan ~/Receipts --fast --text-model qwen3:4b   # a small text model for the text
receipt-reader eval samples/ --fast     # how many were read from the text alone, how accurately, how fast
```

Tesseract is run with `--psm 6` (the page as one block of text): with its default layout it left out
the column of prices on every practice receipt; with 6 it read every total.

Run `eval` with and without `--fast` on the same receipts before you rely on it: the arithmetic catches
misread numbers, but not a misread shop name or date.

## It learns your corrections

Fix a shop name or a category in the spreadsheet, save it, and tell the tool:

```bash
receipt-reader scan ~/Receipts -o receipts.csv
# ...fix "WAL-MART #1007" to "Walmart", "other" to "groceries", save...
receipt-reader learn receipts.csv
```

From then on, that shop gets your name and your category. Once you have corrected about 15
categories, a small word-counting model (naive Bayes) also suggests categories for shops it hasn't
seen, changing the model's guess only when it is at least 80% sure. Every change is in the `notes`
column. The memory is one file on your computer (`~/.receipt-reader/memory.json`, or `RECEIPT_MEMORY`).

## Measure it

```bash
receipt-reader samples samples/   # 30 practice receipts with their correct answers
receipt-reader eval samples/      # how many it reads right, and how many mistakes the check caught
receipt-reader eval samples/ --details why.json   # also save each wrong reading next to the right answer
```

The practice receipts are drawn by code: fictional shops in Canada, the USA, Europe, India and
Australia, with each region's taxes and date formats, a slight tilt, blur and JPEG noise. They are
easier than crumpled real receipts. To test on your own, put a photo next to a `<same name>.json`
with the correct answer (same fields as the practice ones) and run `eval` on that folder.

### Our results

On an Intel NUC with no graphics card, with `gemma4:26b`, 30 practice receipts (October 2026):

| Field | Right |
|---|---|
| date | 30/30 |
| total | 30/30 |
| tax | 30/30 |
| shop | 30/30 |
| currency | 28/30 |

The two currency misses were Australian practice receipts that printed only "$" and "GST incl.",
with no city or ABN to tell Australia from Canada or New Zealand. Practice receipts now carry those,
as real ones do. The arithmetic check can't catch a wrong currency, so use `--currency` for your own
receipts. Time: about 100 seconds a receipt. With the model's "thinking" left on, it was 216.

**On a real receipt** (a crumpled Walmart grocery receipt from Kitchener, Ontario), testing found
five mistakes the practice set never showed. All five are now handled:

- the model read the store's GST/HST and QST **registration numbers** as tax amounts. Code now drops
  any "tax" bigger than the total, or a whole number of 7+ digits, and says so in the `notes` column;
- a check for tax included in prices accepted **any** tax. Taxes now have limits (included at most
  22% of the total, added at most 30%);
- one reading turned the receipt's **"10/17/26" into 2023**. A date more than a year before the photo
  was taken now gets a second look, and is marked CHECK if it stays;
- the same receipt **scanned with Adobe Scan** came out with the shop as "RED CARROT", one of the items.
  The PDF carried text the app had guessed ("Walmart" as "Walmartsa", mixed with survey ads), and that
  text was all the model saw. Scans are now read from the picture, and a shop name that matches an item
  gets a second look;
- read from the picture, the shop was right but a **tax of 3.74 appeared** on a receipt that prints no
  tax amount, and passed as "tax included in the prices". Canadian and US receipts add tax on top, so
  an included tax on a CAD or USD receipt is now flagged unless the receipt says "incl.". The second
  look repeated the 3.74, so when the items, subtotal and total all agree (no room for a tax), code
  removes it and says so in `notes`.

The final reading of that receipt was right in every field.

## Inside (about 1,000 lines of Python)

| File | Job |
|---|---|
| `schema.py` | the fields asked for, and the prompt |
| `model.py` | one request to Ollama's `/api/chat` with the image and the JSON schema |
| `files.py` | photos made upright and smaller; PDF text, or PDF pages as images |
| `checks.py` | the arithmetic check |
| `reader.py` | read, check, one second look |
| `output.py` | CSV and JSON |
| `evaluate.py`, `samples.py` | accuracy on receipts with known answers |
| `memory.py` | your corrections: shop names, categories, a small naive Bayes model |

```bash
pip install -e ".[test]" && pytest     # the tests use a stand-in model: no Ollama needed
```

## Limits

- One receipt per photo. A photo of several receipts reads as one.
- Handwritten receipts and very faded thermal paper are hard for any model: expect `CHECK`.
- The category is the model's best guess. Check it before using it for taxes.
- It reads what is printed. It doesn't know your tax rules: it's for your records, not tax advice.

## Licence

MIT. Use it, change it, sell what you build with it.
