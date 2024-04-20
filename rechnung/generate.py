"""Erzeugt Testdaten: Lieferanten, Bestellungen und Rechnungs-PDFs fiktiver Firmen.

Ein Teil der Rechnungen enthält absichtlich genau einen Fehler. Welcher das
ist, steht in data/erwartet.json. Die Tests prüfen, dass die Prüfung genau
diese Fehler meldet und bei den sauberen Rechnungen nichts findet.

  python -m rechnung erzeugen
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .checksums import format_iban, make_at_iban, make_uid
from .model import Invoice, LineItem, format_amount, money

DATA = Path(__file__).resolve().parent.parent / "data"
DISCLAIMER = "Testdokument - alle Firmen und Nummern sind frei erfunden"

OWN = {"name": "Musterfirma GmbH", "address": "Beispielgasse 1, 1040 Wien", "uid": make_uid("7654321")}


@dataclass(frozen=True)
class Supplier:
    id: str
    name: str
    address: str
    uid: str
    iban: str
    catalog: tuple[tuple[str, str, int], ...]  # (Beschreibung, Einzelpreis, USt-Satz)


SUPPLIERS = [
    Supplier("L01", "Alpenpapier GmbH", "Papiergasse 3, 4020 Linz", make_uid("1234567"), make_at_iban("20111", "28440011100"),
             (("Kopierpapier A4, 500 Blatt", "4.50", 20), ("Ordner breit, blau", "2.90", 20), ("Notizblock A5", "1.20", 20))),
    Supplier("L02", "Donau Elektro KG", "Industriestraße 12, 3100 St. Pölten", make_uid("2345678"), make_at_iban("12000", "51234567890"),
             (("LED-Panel 60x60", "89.00", 20), ("Montage pro Stunde", "68.00", 20), ("Kabelkanal 2 m", "7.40", 20))),
    Supplier("L03", "Kaffeerösterei Brunner e.U.", "Röstweg 5, 8010 Graz", make_uid("3456789"), make_at_iban("38000", "00012345678"),
             (("Kaffeebohnen 1 kg", "24.90", 10), ("Milch 1 l", "1.49", 10), ("Kaffeemaschine Wartung", "120.00", 20))),
    Supplier("L04", "Grünraum Pflanzen OG", "Gartenzeile 8, 1220 Wien", make_uid("4567890"), make_at_iban("14000", "02010123456"),
             (("Zimmerpflanze groß", "79.00", 13), ("Pflanzenpflege pro Monat", "150.00", 20), ("Pflanzgefäß", "45.00", 20))),
    Supplier("L05", "Softwarehaus Pichler GmbH", "Codeweg 21, 1100 Wien", make_uid("5678901"), make_at_iban("32000", "00098765432"),
             (("Lizenz Buchhaltungssoftware", "1850.00", 20), ("Schulung pro Tag", "980.00", 20), ("Support pro Stunde", "110.00", 20))),
]

# Ab hier erwartete Fehler je Szenario. Leere Liste = saubere Rechnung.
SCENARIOS = [
    ("L01", []), ("L02", []), ("L03", []), ("L04", []), ("L05", []),
    ("L01", []), ("L02", []), ("L03", []), ("L05", []), ("L04", []),
    ("L03", ["KLEINBETRAG_OK"]),
    ("L01", ["SUMME_FALSCH"]),
    ("L02", ["UST_FALSCH"]),
    ("L04", ["POSITION_FALSCH"]),
    ("L03", ["UID_UNGUELTIG"]),
    ("L05", ["UID_EMPFAENGER_FEHLT"]),
    ("L02", ["UID_EMPFAENGER_FALSCH"]),
    ("L05", ["PFLICHTANGABE_FEHLT"]),  # über 400 EUR, sonst wäre die fehlende Nummer erlaubt
    ("L02", ["DUBLETTE"]),
    ("L05", ["IBAN_GEAENDERT"]),
    ("L04", ["IBAN_UNGUELTIG"]),
    ("L01", ["PREIS_ABWEICHUNG"]),
    ("L02", ["MENGE_UEBERSCHRITTEN"]),
    ("L03", ["OHNE_BESTELLUNG"]),
    ("L04", ["STEUERSATZ_UNGUELTIG"]),
]


def _totals(items: list[LineItem]) -> tuple[Decimal, dict[int, Decimal], Decimal]:
    net = money(sum(i.net for i in items))
    vat: dict[int, Decimal] = {}
    for item in items:
        vat[item.vat_rate] = vat.get(item.vat_rate, Decimal("0")) + item.net
    vat = {rate: money(base * rate / 100) for rate, base in sorted(vat.items())}
    return net, vat, money(net + sum(vat.values()))


def build(seed: int = 42) -> tuple[list[dict], list[tuple[str, Invoice]], dict[str, list[str]]]:
    rng = random.Random(seed)
    by_id = {s.id: s for s in SUPPLIERS}
    orders, invoices, expected = [], [], {}
    first_clean_l02: Invoice | None = None

    for n, (sid, errors) in enumerate(SCENARIOS, start=1):
        sup = by_id[sid]
        po = f"PO-{1000 + n}"
        small = "KLEINBETRAG_OK" in errors
        big = "UID_EMPFAENGER_FEHLT" in errors

        if small:
            picks = [sup.catalog[0]]
        elif big:
            picks = list(sup.catalog)  # sicher über 10.000 EUR
        else:
            picks = rng.sample(sup.catalog, k=rng.randint(1, len(sup.catalog)))
        items = []
        for desc, price, rate in picks:
            qty = Decimal(rng.randint(1, 3) if small else rng.randint(2, 25))
            if big:
                qty = Decimal(8)
            unit = money(price)
            items.append(LineItem(desc, qty, unit, rate, money(qty * unit)))
            orders.append({"po_number": po, "supplier_id": sid, "description": desc,
                           "quantity": str(qty), "unit_price": str(unit), "vat_rate": rate})

        inv_date = date(2026, 10, 1) + timedelta(days=n)
        inv = Invoice(
            source=f"rechnung_{n:02d}.pdf", supplier_name=sup.name, supplier_address=sup.address, supplier_uid=sup.uid,
            recipient_name=OWN["name"], recipient_address=OWN["address"], recipient_uid=OWN["uid"],
            number=f"{sid}-2026-{100 + n}", invoice_date=inv_date, service_date=inv_date - timedelta(days=2),
            po_number=po, items=items, iban=sup.iban,
        )

        if small:  # Kleinbetragsrechnung: ohne Empfänger, Nummer und Bestellung zulässig
            inv = replace(inv, recipient_name=None, recipient_address=None, recipient_uid=None, number=None, po_number=None)
            orders = [o for o in orders if o["po_number"] != po]
        if big:
            inv.recipient_uid = None
        if "UID_EMPFAENGER_FALSCH" in errors:
            inv.recipient_uid = make_uid("1111111")
        if "UID_UNGUELTIG" in errors:
            inv.supplier_uid = sup.uid[:-1] + str((int(sup.uid[-1]) + 1) % 10)
        if "PFLICHTANGABE_FEHLT" in errors:
            inv.number = None
        if "IBAN_GEAENDERT" in errors:
            inv.iban = make_at_iban("19043", "00234573201")
        if "IBAN_UNGUELTIG" in errors:
            inv.iban = sup.iban[:-1] + str((int(sup.iban[-1]) + 1) % 10)
        if "PREIS_ABWEICHUNG" in errors:
            it = items[0]
            items[0] = replace(it, unit_price=money(it.unit_price * Decimal("1.05")), net=money(it.quantity * money(it.unit_price * Decimal("1.05"))))
        if "MENGE_UEBERSCHRITTEN" in errors:
            it = items[0]
            items[0] = replace(it, quantity=it.quantity + 5, net=money((it.quantity + 5) * it.unit_price))
        if "OHNE_BESTELLUNG" in errors:
            inv.po_number = "PO-9999"
        if "STEUERSATZ_UNGUELTIG" in errors:
            items[0] = replace(items[0], vat_rate=19)
        if "POSITION_FALSCH" in errors:
            items[0] = replace(items[0], net=items[0].net + 1)

        inv.items = items
        inv.net_total, inv.vat, inv.gross_total = _totals(items)
        if "UST_FALSCH" in errors:
            rate = next(iter(inv.vat))
            inv.vat[rate] += 5
            inv.gross_total = money(inv.net_total + inv.vat_total)
        if "SUMME_FALSCH" in errors:
            inv.gross_total += 10

        if "DUBLETTE" in errors and first_clean_l02 is not None:
            inv = replace(first_clean_l02, source=inv.source)  # dieselbe Rechnung ein zweites Mal
            orders = [o for o in orders if o["po_number"] != po]
        if sid == "L02" and not errors and first_clean_l02 is None:
            first_clean_l02 = inv

        invoices.append((inv.source, inv))
        expected[inv.source] = [e for e in errors if e != "KLEINBETRAG_OK"]
    return orders, invoices, expected


def render_pdf(inv: Invoice, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"Rechnung {inv.number or ''}".strip())
    y = A4[1] - 60

    def line(text: str, font: str = "Helvetica", size: int = 10, gap: int = 14) -> None:
        nonlocal y
        c.setFont(font, size)
        c.drawString(50, y, text)
        y -= gap

    line(inv.supplier_name, "Helvetica-Bold", 14, 18)
    line(inv.supplier_address)
    if inv.supplier_uid:
        line(f"UID: {inv.supplier_uid}")
    y -= 14
    if inv.recipient_name:
        line("Rechnung an:")
        line(inv.recipient_name)
        line(inv.recipient_address)
        if inv.recipient_uid:
            line(f"Ihre UID: {inv.recipient_uid}")
        y -= 14
    line("RECHNUNG", "Helvetica-Bold", 16, 22)
    if inv.number:
        line(f"Rechnungsnummer: {inv.number}")
    line(f"Rechnungsdatum: {inv.invoice_date:%d.%m.%Y}")
    line(f"Leistungsdatum: {inv.service_date:%d.%m.%Y}")
    if inv.po_number:
        line(f"Bestellnummer: {inv.po_number}")
    y -= 10
    line(f"{'Pos':<4}{'Beschreibung':<30}{'Menge':>7}{'Einzelpreis':>13}{'USt':>6}{'Netto':>12}", "Courier-Bold", 9, 13)
    for pos, it in enumerate(inv.items, start=1):
        line(f"{pos:<4}{it.description:<30}{format_amount(it.quantity).replace(',00', ''):>7}"
             f"{format_amount(it.unit_price):>13}{str(it.vat_rate) + '%':>6}{format_amount(it.net):>12}", "Courier", 9, 13)
    y -= 8
    line(f"Summe netto: {format_amount(inv.net_total)} EUR")
    for rate, amount in inv.vat.items():
        line(f"USt {rate} %: {format_amount(amount)} EUR")
    line(f"Gesamtbetrag: {format_amount(inv.gross_total)} EUR", "Helvetica-Bold", 11, 22)
    line(f"Zahlbar innerhalb von 14 Tagen auf IBAN {format_iban(inv.iban)}")
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(50, 40, DISCLAIMER)
    c.save()


def write_all(out: Path = DATA, seed: int = 42) -> dict[str, list[str]]:
    orders, invoices, expected = build(seed)
    pdf_dir = out / "rechnungen"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    for name, inv in invoices:
        render_pdf(inv, pdf_dir / name)

    with open(out / "lieferanten.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["supplier_id", "name", "uid", "iban"])
        for s in SUPPLIERS:
            w.writerow([s.id, s.name, s.uid, s.iban])
    with open(out / "bestellungen.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["po_number", "supplier_id", "description", "quantity", "unit_price", "vat_rate"])
        w.writeheader()
        w.writerows(orders)
    (out / "eigene_firma.json").write_text(json.dumps(OWN, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "erwartet.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
    return expected
