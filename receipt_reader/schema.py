"""What we ask the model for: one JSON object per receipt.

Ollama's "structured outputs" make the model answer in exactly this shape (the `format` field of the
request), so we never have to dig numbers out of free text."""

MONEY = {"type": ["number", "null"]}  # null: not printed on the receipt

ITEM = {"type": "object",
        "properties": {"description": {"type": "string"},
                       "quantity": {"type": "number"},
                       "amount": {"type": "number"}},
        "required": ["description", "quantity", "amount"]}  # fmt: skip
TAX = {"type": "object",
       "properties": {"name": {"type": "string"},
                      "amount": {"type": "number"}},
       "required": ["name", "amount"]}  # fmt: skip
CATEGORIES = ["groceries", "restaurant", "fuel", "travel",
              "office", "utilities", "health", "other"]  # fmt: skip

SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": {"type": "string"},
        "date": {"type": "string"},  # YYYY-MM-DD
        "currency": {"type": "string"},  # CAD, USD, EUR, INR, AUD...
        "items": {"type": "array", "items": ITEM},
        "subtotal": MONEY,
        "taxes": {"type": "array", "items": TAX},
        "tip": MONEY,
        "total": {"type": "number"},
        "payment_method": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
    },
    "required": ["vendor", "date", "currency", "items",
                 "subtotal", "taxes", "tip", "total",
                 "payment_method", "category"],  # fmt: skip
}

PROMPT = """Read this receipt or invoice and return its details as JSON.
- vendor: the shop or company name, usually the logo or the first line at the top (a chain's name such as
  Walmart, not the store number). Never a product from the item lines.
- date: the purchase or invoice date as YYYY-MM-DD. A two-digit year means 20YY: "10/17/26" is 2026-10-17,
  not 2023 or 1926. If the receipt writes 03/04/2026, use the country's
  usual order (day first in Europe, India and Australia; month first in the USA; Canada uses both, so
  prefer the order the receipt itself makes clear).
- currency: the 3-letter code (CAD, USD, EUR, GBP, INR, AUD...), from the symbol, the country or the tax names.
- items: every line item with its quantity (1 if not shown) and the line amount as printed.
- subtotal: before tax, or null if not printed. taxes: each tax line (GST, HST, PST, QST, VAT, CGST, SGST,
  sales tax...) with its amount; [] if none. A line like "GST/HST 137466199 RT 0001" or "QST 1016551356 TQ"
  is the store's tax registration number, not an amount: when the receipt prints no tax amount (groceries
  are often tax-free), taxes is []. tip: or null.
- total: the final amount paid. payment_method: cash, card, debit... or "" if not shown.
- category: the best fit from the list.
Copy numbers exactly as printed; never guess a number that isn't on the receipt."""
