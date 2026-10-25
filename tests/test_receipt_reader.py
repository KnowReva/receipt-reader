"""receipt-reader, all offline: a stand-in model answers instead of Ollama."""

import csv
import datetime as dt
import io
import json
import urllib.error

import pytest
from PIL import Image

from receipt_reader import checks, cli, evaluate, files, model, output, reader, samples

TODAY = dt.date(2026, 10, 25)
GOOD = {"vendor": "Maple Corner Grocery", "date": "2026-10-20", "currency": "CAD",
        "items": [{"description": "Bread", "quantity": 1, "amount": 3.29}, {"description": "Eggs", "quantity": 2, "amount": 11.98}],
        "subtotal": 15.27, "taxes": [{"name": "HST 13%", "amount": 1.99}], "tip": None, "total": 17.26,
        "payment_method": "VISA", "category": "groceries"}  # fmt: skip


def stand_in(*answers):
    """A fake model: gives the answers in turn and remembers what it was asked."""
    calls = []

    def chat(messages, schema, **kw):
        calls.append({"messages": messages, "schema": schema, **kw})
        return json.loads(json.dumps(answers[min(len(calls) - 1, len(answers) - 1)]))

    chat.calls = calls
    return chat


@pytest.fixture
def photo(tmp_path):
    p = tmp_path / "r.jpg"
    Image.new("RGB", (3000, 1200), "white").save(p)
    return p


# ---------------------------------------------------------------- the arithmetic check
def test_a_receipt_that_adds_up_passes():
    assert checks.problems(GOOD, TODAY) == []


def test_tax_included_in_the_prices_passes():
    vat = dict(GOOD, subtotal=None, taxes=[{"name": "MwSt 7% incl.", "amount": 1.0}], total=15.27, currency="EUR")
    assert checks.problems(vat, TODAY) == []


def test_misreadings_are_caught():
    assert "items add up to 15.27, not the subtotal 15.72" in checks.problems(dict(GOOD, subtotal=15.72), TODAY)[0]
    assert "not the total 71.26" in checks.problems(dict(GOOD, total=71.26), TODAY)[0]
    assert "in the future" in checks.problems(dict(GOOD, date="2027-01-01"), TODAY)[0]
    assert "isn't a date" in checks.problems(dict(GOOD, date="20/10/2026"), TODAY)[0]
    assert "3-letter" in checks.problems(dict(GOOD, currency="$"), TODAY)[0]
    assert checks.problems(dict(GOOD, total=0), TODAY)[0] == "no total"


# ---------------------------------------------------------------- reading one receipt
def test_a_second_look_fixes_a_misread_total(photo):
    chat = stand_in(dict(GOOD, total=71.26), GOOD)
    r = reader.read(photo, chat=chat, today=TODAY)
    assert r["status"] == "ok" and r["total"] == 17.26 and len(chat.calls) == 2
    second = chat.calls[1]["messages"][0]["content"]
    assert "not the total 71.26" in second and "Look again" in second
    assert chat.calls[0]["messages"][0]["images"] and chat.calls[0]["schema"]["required"][0] == "vendor"


def test_a_worse_second_look_is_not_kept(photo):
    worse = dict(GOOD, total=71.26, date="2027-01-01")
    r = reader.read(photo, chat=stand_in(dict(GOOD, total=71.26), worse), today=TODAY)
    assert r["status"] == "check" and r["date"] == "2026-10-20" and len(r["problems"]) == 1


def test_nothing_to_check_is_flagged(photo):
    r = reader.read(photo, chat=stand_in(dict(GOOD, items=[], subtotal=None)), today=TODAY)
    assert r["status"] == "check" and "couldn't be checked" in r["problems"][0]


# ---------------------------------------------------------------- files
def test_files_photos_text_pdfs_and_scanned_pdfs(tmp_path, photo):
    img = files.load(photo)["images"][0]
    with Image.open(io.BytesIO(__import__("base64").b64decode(img))) as back:
        assert max(back.size) == 1600  # made smaller before it is sent
    samples.write(tmp_path / "s", count=10)
    text = files.load(tmp_path / "s" / "receipt-10-eu.pdf")
    assert "text" in text and "TOTAL" in text["text"]
    scanned = files.load(tmp_path / "s" / "receipt-05-in.pdf")
    assert len(scanned["images"]) == 1
    found = files.find([str(tmp_path / "s")])
    assert len(found) == 10 and not any(f.suffix == ".json" for f in found)
    with pytest.raises(ValueError):
        files.load(tmp_path / "s" / "receipt-01-on.json")


def test_text_pdf_is_sent_as_text(tmp_path):
    samples.write(tmp_path, count=10)
    chat = stand_in(GOOD)
    reader.read(tmp_path / "receipt-10-eu.pdf", chat=chat, today=TODAY)
    msg = chat.calls[0]["messages"][0]
    assert "images" not in msg and "THE RECEIPT (text from a PDF)" in msg["content"]


def test_every_practice_answer_adds_up(tmp_path):
    made = samples.write(tmp_path, count=30)
    assert len(made) == 30
    for p in made:
        assert checks.problems(json.loads(p.with_suffix(".json").read_text()), dt.date.today(), files.taken_on(p)) == [], p.name


# ---------------------------------------------------------------- output
def test_csv_rows_and_items(tmp_path):
    r = {"file": "a.jpg", **GOOD, "status": "ok", "problems": []}
    output.write_csv([r], tmp_path / "out.csv")
    output.write_items([r], tmp_path / "items.csv")
    row = next(csv.DictReader((tmp_path / "out.csv").read_text().splitlines()))
    assert row["vendor"] == "Maple Corner Grocery" and row["tax"] == "1.99" and row["total"] == "17.26" and row["tip"] == ""
    assert len((tmp_path / "items.csv").read_text().splitlines()) == 3


# ---------------------------------------------------------------- accuracy
def test_eval_counts_and_flags(tmp_path):
    samples.write(tmp_path, count=4)
    truths = [json.loads(p.read_text()) for p in sorted(tmp_path.glob("*.json"))]
    wrong_total = dict(truths[1], total=truths[1]["total"] + 10)  # caught by the arithmetic
    wrong_vendor = dict(truths[2], vendor="Something Else")  # adds up, so not caught
    answers = [truths[0], wrong_total, wrong_total, wrong_vendor, truths[3]]
    s = evaluate.run(tmp_path, chat=stand_in(*answers), today=dt.date.today(), say=lambda m: None)
    assert s["receipts"] == 4 and s["all_right"] == 2 and s["wrong"] == 2 and s["wrong_but_flagged"] == 1
    assert s["fields"]["vendor"] == 3 and s["fields"]["total"] == 3
    text = evaluate.report(s)
    assert "All five fields right: 2/4 (50%)" in text and "flagged 1" in text


# ---------------------------------------------------------------- talking to Ollama
class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_request_ollama_gets(monkeypatch):
    sent = {}

    def urlopen(req, timeout):
        sent.update(url=req.full_url, body=json.loads(req.data))
        return FakeResponse(json.dumps({"message": {"content": json.dumps(GOOD)}}).encode())

    monkeypatch.setattr(model.urllib.request, "urlopen", urlopen)
    got = model.chat([{"role": "user", "content": "hi", "images": ["abc"]}], {"type": "object"}, model="m", url="http://x:1/")
    assert got["total"] == 17.26 and sent["url"] == "http://x:1/api/chat"
    assert sent["body"]["format"] == {"type": "object"} and sent["body"]["options"]["temperature"] == 0
    assert sent["body"]["stream"] is False and sent["body"]["messages"][0]["images"] == ["abc"]
    assert sent["body"]["think"] is False  # thinking models answer straight away


def test_plain_errors_from_ollama(monkeypatch):
    def missing(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 404, "x", {}, io.BytesIO(b'{"error":"model \'m\' not found"}'))

    monkeypatch.setattr(model.urllib.request, "urlopen", missing)
    with pytest.raises(model.ModelError, match="ollama pull m"):
        model.chat([], {}, model="m")

    def down(req, timeout):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(model.urllib.request, "urlopen", down)
    with pytest.raises(model.ModelError, match="Is it running"):
        model.chat([], {})


def test_the_command_line(tmp_path, photo, monkeypatch, capsys):
    monkeypatch.setattr(model, "chat", stand_in(GOOD))
    out = tmp_path / "out.csv"
    assert cli.main(["scan", str(photo), "-o", str(out), "--items", str(tmp_path / "i.csv")]) == 0
    assert "Maple Corner Grocery 17.26 CAD OK" in capsys.readouterr().out and out.exists()
    assert cli.main(["samples", str(tmp_path / "s"), "--count", "3"]) == 0
    assert len(list((tmp_path / "s").glob("*.json"))) == 3


def test_errors_are_counted_apart_from_misreadings(tmp_path):
    samples.write(tmp_path, count=3)
    truths = [json.loads(p.read_text()) for p in sorted(tmp_path.glob("*.json"))]
    calls = {"n": 0}

    def flaky(messages, schema, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise model.ModelError("Ollama took longer than 600 seconds")
        return truths[0] if calls["n"] == 1 else truths[2]

    said = []
    s = evaluate.run(tmp_path, chat=flaky, today=dt.date.today(), say=said.append)
    assert s["receipts"] == 2 and s["errors"] == 1 and s["all_right"] == 2
    assert any("COULDN'T READ IT (ModelError: Ollama took longer" in x for x in said)
    assert "Couldn't read 1 (errors, not misreadings)" in evaluate.report(s)


def test_a_timeout_is_explained(monkeypatch):
    def slow(req, timeout):
        raise TimeoutError()

    monkeypatch.setattr(model.urllib.request, "urlopen", slow)
    with pytest.raises(model.ModelError, match="smaller model"):
        model.chat([], {}, timeout=5)


def test_your_usual_currency(photo):
    chat = stand_in(dict(GOOD, currency="$"))
    r = reader.read(photo, chat=chat, today=TODAY, currency="cad")
    assert r["currency"] == "CAD" and r["status"] == "ok"
    assert "it is CAD" in chat.calls[0]["messages"][0]["content"]
    r = reader.read(photo, chat=stand_in(dict(GOOD, currency="USD")), today=TODAY, currency="CAD")
    assert r["currency"] == "USD"  # a receipt that says otherwise keeps its own


def test_a_registration_number_read_as_tax_is_caught(photo):
    """The real Walmart receipt: groceries with no tax, total 38.96; the model put 23.92 in taxes."""
    walmart = dict(GOOD, vendor="Walmart", subtotal=38.96, total=38.96,
                   items=[{"description": d, "quantity": 1, "amount": a} for d, a in
                          [("YFM POT YLW", 5.94), ("PANEER", 4.98), ("ASTRO YOGURT", 3.67), ("4L HOMO MILK", 11.78),
                           ("RED CARROT", 2.97), ("GARLIC 3PK", 0.98), ("RED ONION", 3.94), ("TOMATO ROMA", 4.70)]],
                   taxes=[{"name": "GST/HST", "amount": 23.92}])  # fmt: skip
    found = checks.problems(walmart, TODAY)
    assert found and "CAD receipts don't include tax" in found[0] and len(found) == 1
    in_euros = dict(walmart, currency="EUR", taxes=[{"name": "MwSt incl.", "amount": 23.92}])
    assert "can't be included in a total of 38.96" in checks.problems(in_euros, TODAY)[0]  # the limit, elsewhere
    assert checks.problems(dict(walmart, taxes=[]), TODAY) == []  # read right: no tax
    big = dict(GOOD, taxes=[{"name": "HST", "amount": 9.99}], total=25.26)  # adds up, but 65% tax
    assert checks.problems(big, TODAY)[0].startswith("tax 9.99 is more than 30%")
    r = reader.read(photo, chat=stand_in(walmart, dict(walmart, taxes=[])), today=TODAY)
    assert r["status"] == "ok" and r["taxes"] == []  # the second look, told why, fixes it
    from receipt_reader.schema import PROMPT

    assert "registration number" in PROMPT


def test_practice_grocery_receipts_in_canada_have_no_tax_but_print_registration_numbers(tmp_path):
    made = samples.write(tmp_path, count=30)
    grocery = [p for p in made if p.suffix == ".jpg" and json.loads(p.with_suffix(".json").read_text())["category"] == "groceries"
               and p.stem.endswith(("-on", "-qc"))]
    assert grocery and all(json.loads(p.with_suffix(".json").read_text())["taxes"] == [] for p in grocery)
    text = files.load(next(p for p in made if p.name.endswith("-qc.pdf") or p.name.endswith("-on.pdf")))
    assert "RT 0001" in text.get("text", "RT 0001")


def test_registration_numbers_read_as_tax_are_dropped_with_a_note(photo, tmp_path):
    """gemma4 on the real Walmart receipt: both registration numbers as tax, even after a second look."""
    walmart = dict(GOOD, vendor="Walmart", subtotal=38.96, total=38.96, items=[{"description": "Groceries", "quantity": 1, "amount": 38.96}],
                   taxes=[{"name": "GST/HST", "amount": 137466199}, {"name": "QST", "amount": 1016551356}])  # fmt: skip
    r = reader.read(photo, chat=stand_in(walmart), today=TODAY)
    assert r["status"] == "ok" and r["taxes"] == [] and len(r["notes"]) == 2 and "registration number" in r["notes"][0]
    output.write_csv([r], tmp_path / "w.csv")
    row = next(csv.DictReader((tmp_path / "w.csv").read_text().splitlines()))
    assert row["tax"] == "" and "137466199" in row["notes"] and row["status"] == "ok"
    # a real tax is never touched
    keep = dict(GOOD)
    assert checks.drop_impossible_taxes(keep) == [] and keep["taxes"] == GOOD["taxes"]


def test_a_misread_year_is_caught_against_the_photos_date(photo):
    """The real Walmart receipt says 10/17/26; one reading gave 2023-10-17."""
    import os

    os.utime(photo, (dt.datetime(2026, 10, 25).timestamp(),) * 2)
    assert files.taken_on(photo) == dt.date(2026, 10, 25)
    misread = dict(GOOD, date="2023-10-17")
    found = checks.problems(misread, TODAY, files.taken_on(photo))
    assert found == ["date 2023-10-17 is 3 year(s) before this photo or file (2026-10-25): check the year"]
    chat = stand_in(misread, dict(GOOD, date="2026-10-17"))
    r = reader.read(photo, chat=chat, today=TODAY)
    assert r["status"] == "ok" and r["date"] == "2026-10-17"
    assert "check the year" in chat.calls[1]["messages"][0]["content"]  # the second look was told why
    from receipt_reader.schema import PROMPT

    assert '"10/17/26" is 2026-10-17' in PROMPT


def test_a_net_subtotal_on_a_tax_included_receipt_is_right():
    """VAT or GST included: items 19.90 = total; a subtotal of 18.60 (before the 1.30 tax) is right too."""
    vat = dict(GOOD, currency="EUR", items=[{"description": "Bread", "quantity": 1, "amount": 19.90}],
               subtotal=18.60, taxes=[{"name": "MwSt 7% incl.", "amount": 1.30}], total=19.90)
    assert checks.problems(vat, TODAY) == []
    assert checks.problems(dict(vat, subtotal=17.00), TODAY)  # but a subtotal that fits nothing is still flagged


def test_practice_receipts_say_where_they_are(tmp_path):
    made = samples.write(tmp_path, count=12)
    text = files.load(next(p for p in made if p.name.endswith("-au.pdf") or p.suffix == ".pdf"))
    au = [p for p in made if "-au" in p.name]
    assert au
    r = samples.make(__import__("random").Random(1), "au")
    printed = " ".join(str(t) for _, t in r["lines"])
    assert "ABN " in printed and any(s in printed for s in ("NSW", "VIC", "QLD"))
    assert text  # still readable


def test_a_phone_scan_with_guessed_text_is_read_from_the_picture(tmp_path, monkeypatch):
    """The real Walmart receipt came as an Adobe Scan PDF: a photo plus text the app guessed ("Walmartsa").
    Read as text, the shop came out as an item, "RED CARROT". Now the picture goes to the model."""
    samples.write(tmp_path, count=10)
    scan = tmp_path / "receipt-05-in.pdf"  # a page that is one picture
    guessed = "Walmartsa How did we do today? SURVEY.WALMART.CA\nRED CARROT 686201966610 $2.97 D\nTOTAL $38.96"
    monkeypatch.setattr(files, "pdf_text", lambda p: guessed)
    assert files.scanned(scan) and not files.scanned(tmp_path / "receipt-10-eu.pdf")
    content = files.load(scan)
    assert content["images"] and content["scan_text"] == guessed and "text" not in content
    chat = stand_in(GOOD)
    reader.read(scan, chat=chat, today=TODAY)
    msg = chat.calls[0]["messages"][0]
    assert msg["images"] and "TEXT A SCANNER APP GUESSED" in msg["content"] and "Walmartsa" in msg["content"]


def test_a_shop_name_that_is_one_of_the_items_gets_a_second_look(photo):
    item_as_shop = dict(GOOD, vendor="EGGS")
    assert checks.problems(item_as_shop, TODAY) == ["the shop name 'EGGS' is one of the items: check the shop"]
    assert checks.problems(dict(GOOD, vendor=""), TODAY) == ["no shop name"]
    chat = stand_in(item_as_shop, dict(GOOD, vendor="Walmart"))
    r = reader.read(photo, chat=chat, today=TODAY)
    assert r["status"] == "ok" and r["vendor"] == "Walmart"
    assert "check the shop" in chat.calls[1]["messages"][0]["content"]


def test_a_made_up_included_tax_on_a_canadian_receipt_is_caught(photo):
    """The Walmart scan, read again: shop right, but taxes 3.74 on a receipt that prints no tax amount.
    The items reached the total, so it passed as tax "included", which Canadian receipts don't do."""
    made_up = dict(GOOD, vendor="Walmart", subtotal=38.96, total=38.96,
                   items=[{"description": "4L HOMO MILK", "quantity": 1, "amount": 38.96}],
                   taxes=[{"name": "HST", "amount": 3.74}])  # fmt: skip
    found = checks.problems(made_up, TODAY)
    assert len(found) == 1 and found[0].startswith("tax 3.74 isn't on top of the prices")
    assert checks.problems(dict(made_up, taxes=[]), TODAY) == []
    assert checks.problems(dict(made_up, taxes=[{"name": "GST incl.", "amount": 1.86}]), TODAY) == []  # it says so
    assert checks.problems(dict(made_up, currency="AUD", taxes=[{"name": "GST", "amount": 3.54}]), TODAY) == []
    # The real run: the second look repeated the 3.74. Items, subtotal and total all say 38.96, so code
    # removes it and says so (only on CAD/USD, only when all three agree, never an "incl." line).
    r = reader.read(photo, chat=stand_in(made_up), today=TODAY)
    assert r["status"] == "ok" and r["taxes"] == [] and "no tax was added" in r["notes"][0]
    no_subtotal = dict(made_up, subtotal=None)
    assert reader.read(photo, chat=stand_in(no_subtotal), today=TODAY)["status"] == "check"  # not proven: flagged
    euro = dict(made_up, currency="EUR", taxes=[{"name": "MwSt", "amount": 3.74}])
    assert checks.drop_unprinted_tax(euro) == [] and euro["taxes"]


def test_a_broken_or_cut_off_answer_gets_the_second_look(photo, monkeypatch):
    def reply(content, reason="stop"):
        return FakeResponse(json.dumps({"message": {"content": content}, "done_reason": reason}).encode())

    answers = [reply('{"vendor": "Wal', "length"), reply(json.dumps(GOOD))]
    sent = []
    monkeypatch.setattr(model.urllib.request, "urlopen", lambda req, timeout: sent.append(json.loads(req.data))
                        or answers.pop(0))  # fmt: skip
    r = reader.read(photo, chat=model.chat, today=TODAY)
    assert r["status"] == "ok" and r["vendor"] == "Maple Corner Grocery" and len(sent) == 2
    assert "cut off (done_reason: length)" in sent[1]["messages"][0]["content"]
    assert sent[0]["options"]["num_ctx"] == model.CONTEXT == 8192
    assert len(sent[1]["messages"]) == 1  # a new single-message request, not a growing conversation
    monkeypatch.setattr(model.urllib.request, "urlopen", lambda req, timeout: reply("not json"))
    with pytest.raises(model.BadAnswer, match="wasn't valid JSON"):
        reader.read(photo, chat=model.chat, today=TODAY)  # broken twice: counted as an error, not a reading


def test_two_cents_is_two_cents():
    assert 1.02 - 1.00 > 0.02  # floating point
    assert checks.close(1.02, 1.00) and not checks.close(1.03, 1.00)


def test_iphone_photos(tmp_path):
    from pillow_heif import register_heif_opener  # noqa: F401 (installed with receipt-reader)

    p = tmp_path / "IMG_0001.HEIC"
    Image.new("RGB", (2000, 3000), "white").save(p, format="HEIF")
    assert files.find([str(tmp_path)]) == [p]
    with Image.open(io.BytesIO(__import__("base64").b64decode(files.load(p)["images"][0]))) as back:
        assert back.format == "JPEG" and max(back.size) == 1600
