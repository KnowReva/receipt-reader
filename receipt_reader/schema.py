"""What we ask the model for: one JSON object per receipt.

Ollama's "structured outputs" make the model answer in exactly this shape (the `format` field of the
request), so we never have to dig numbers out of free text."""

CATEGORIES = ["groceries", "restaurant", "fuel", "travel", "office", "utilities", "health", "other"]

MONEY = {"type": ["number", "null"]}  # null when the receipt doesn't print it

SCHEMA = {
    "type": "object",
    "properties": {
        "vendor": {"type": "string"},
        "date": {"type": "string"},  # asked for as YYYY-MM-DD
        "currency": {"type": "string"},  # a 3-letter code: CAD, USD, EUR, INR, AUD...
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"description": {"type": "string"}, "quantity": {"type": "number"}, "amount": {"type": "number"}},
                "required": ["description", "quantity", "amount"],
            },
        },
        "subtotal": MONEY,
        "taxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "amount": {"type": "number"}},
                "required": ["name", "amount"],
            },
        },
        "tip": MONEY,
        "total": {"type": "number"},
        "payment_method": {"type": "string"},
        "category": {"type": "string", "enum": CATEGORIES},
    },
    "required": ["vendor", "date", "currency", "items", "subtotal", "taxes", "tip", "total", "payment_method", "category"],
}

PROMPT = """Read this receipt or invoice and return its details as JSON.
- vendor: the shop or company name as printed.
- date: the purchase or invoice date as YYYY-MM-DD. If the receipt writes 03/04/2026, use the country's
  usual order (day first in Europe, India and Australia; month first in the USA; Canada uses both, so
  prefer the order the receipt itself makes clear).
- currency: the 3-letter code (CAD, USD, EUR, GBP, INR, AUD...), from the symbol, the country or the tax names.
- items: every line item with its quantity (1 if not shown) and the line amount as printed.
- subtotal: before tax, or null if not printed. taxes: each tax line (GST, HST, PST, QST, VAT, CGST, SGST,
  sales tax...) with its amount; [] if none. tip: or null.
- total: the final amount paid. payment_method: cash, card, debit... or "" if not shown.
- category: the best fit from the list.
Copy numbers exactly as printed; never guess a number that isn't on the receipt."""
