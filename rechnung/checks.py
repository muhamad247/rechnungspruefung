"""Prüfregeln für Eingangsrechnungen.

Rechtliche Grundlage der Pflichtangaben ist § 11 UStG (Österreich):
- bis 400 EUR brutto (Kleinbetragsrechnung): vereinfachte Angaben genügen
- über 400 EUR: alle Rechnungsmerkmale, u. a. Empfänger, fortlaufende Nummer, UID des Lieferanten
- über 10.000 EUR: zusätzlich die UID des Empfängers

Jede Regel liefert Findings mit Schweregrad:
- FEHLER: so nicht zahlen (Rechnung zurückweisen oder Korrektur anfordern)
- WARNUNG: vor der Zahlung von einem Menschen prüfen lassen
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .checksums import iban_valid, normalize_iban, uid_valid
from .model import Invoice, money

KLEINBETRAG = Decimal("400")
UID_EMPFAENGER_AB = Decimal("10000")
STEUERSAETZE = {0, 10, 13, 20}
PREIS_TOLERANZ = Decimal("0.02")  # 2 %
CENT_TOLERANZ = Decimal("0.01")


@dataclass(frozen=True)
class Finding:
    source: str
    code: str
    severity: str  # FEHLER oder WARNUNG
    message: str


@dataclass
class MasterData:
    own: dict
    suppliers: dict[str, dict]  # nach Name
    orders: dict[str, list[dict]]  # nach Bestellnummer

    @classmethod
    def load(cls, folder: str | Path) -> MasterData:
        import json

        folder = Path(folder)
        own = json.loads((folder / "eigene_firma.json").read_text(encoding="utf-8"))
        with open(folder / "lieferanten.csv", encoding="utf-8") as f:
            suppliers = {row["name"]: row for row in csv.DictReader(f)}
        orders: dict[str, list[dict]] = {}
        with open(folder / "bestellungen.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                orders.setdefault(row["po_number"], []).append(row)
        return cls(own, suppliers, orders)


def check_invoice(inv: Invoice, master: MasterData) -> list[Finding]:
    found: list[Finding] = []

    def add(code: str, severity: str, message: str) -> None:
        found.append(Finding(inv.source, code, severity, message))

    gross = inv.gross_total or Decimal("0")

    # Pflichtangaben nach Betrag
    required = {"Lieferant": inv.supplier_name, "Rechnungsdatum": inv.invoice_date, "Gesamtbetrag": inv.gross_total}
    if gross > KLEINBETRAG:
        required |= {"Empfänger": inv.recipient_name, "Rechnungsnummer": inv.number,
                     "Leistungsdatum": inv.service_date, "UID des Lieferanten": inv.supplier_uid}
    missing = [name for name, value in required.items() if not value]
    if missing:
        add("PFLICHTANGABE_FEHLT", "FEHLER", "Fehlende Pflichtangabe nach § 11 UStG: " + ", ".join(missing))
    if gross > UID_EMPFAENGER_AB and not inv.recipient_uid:
        add("UID_EMPFAENGER_FEHLT", "FEHLER", f"Über {UID_EMPFAENGER_AB:,.0f} EUR muss unsere UID auf der Rechnung stehen")

    # UID-Nummern
    if inv.supplier_uid and not uid_valid(inv.supplier_uid):
        add("UID_UNGUELTIG", "FEHLER", f"UID des Lieferanten {inv.supplier_uid} hat eine falsche Prüfziffer")
    if inv.recipient_uid and inv.recipient_uid != master.own["uid"]:
        add("UID_EMPFAENGER_FALSCH", "FEHLER", f"Empfänger-UID {inv.recipient_uid} ist nicht unsere ({master.own['uid']})")

    # Rechnerische Richtigkeit
    for pos, item in enumerate(inv.items, start=1):
        if abs(money(item.quantity * item.unit_price) - item.net) > CENT_TOLERANZ:
            add("POSITION_FALSCH", "FEHLER", f"Position {pos}: {item.quantity} × {item.unit_price} ≠ {item.net}")
        if item.vat_rate not in STEUERSAETZE:
            add("STEUERSATZ_UNGUELTIG", "FEHLER", f"Position {pos}: {item.vat_rate} % ist kein österreichischer Steuersatz")
    if inv.items and inv.net_total is not None and abs(money(sum(i.net for i in inv.items)) - inv.net_total) > CENT_TOLERANZ:
        add("SUMME_FALSCH", "FEHLER", "Summe der Positionen weicht von der Nettosumme ab")
    bases: dict[int, Decimal] = {}
    for item in inv.items:
        bases[item.vat_rate] = bases.get(item.vat_rate, Decimal("0")) + item.net
    for rate, base in bases.items():
        stated = inv.vat.get(rate)
        if stated is None or abs(money(base * rate / 100) - stated) > CENT_TOLERANZ:
            add("UST_FALSCH", "FEHLER", f"USt {rate} % sollte {money(base * rate / 100)} sein, steht {stated}")
    if inv.net_total is not None and inv.gross_total is not None:
        if abs(inv.net_total + inv.vat_total - inv.gross_total) > CENT_TOLERANZ:
            add("SUMME_FALSCH", "FEHLER", f"Netto {inv.net_total} + USt {inv.vat_total} ≠ Gesamtbetrag {inv.gross_total}")

    # Bankverbindung gegen Stammdaten
    supplier = master.suppliers.get(inv.supplier_name or "")
    if inv.iban and not iban_valid(inv.iban):
        add("IBAN_UNGUELTIG", "FEHLER", f"IBAN {inv.iban} hat eine falsche Prüfsumme")
    elif supplier and normalize_iban(inv.iban) != normalize_iban(supplier["iban"]):
        add("IBAN_GEAENDERT", "WARNUNG",
            "IBAN weicht von den Stammdaten ab. Vor der Zahlung telefonisch beim Lieferanten bestätigen "
            "(typisches Muster bei Rechnungsbetrug)")

    # Abgleich mit der Bestellung (Kleinbeträge ohne Bestellnummer sind erlaubt)
    if inv.po_number or gross > KLEINBETRAG:
        order = master.orders.get(inv.po_number or "")
        if not order:
            add("OHNE_BESTELLUNG", "WARNUNG", f"Keine passende Bestellung zu {inv.po_number or 'fehlender Bestellnummer'}")
        else:
            ordered = {row["description"]: row for row in order}
            for item in inv.items:
                row = ordered.get(item.description)
                if row is None:
                    add("OHNE_BESTELLUNG", "WARNUNG", f"'{item.description}' wurde nicht bestellt")
                    continue
                if item.quantity > Decimal(row["quantity"]):
                    add("MENGE_UEBERSCHRITTEN", "WARNUNG",
                        f"'{item.description}': {item.quantity} berechnet, {row['quantity']} bestellt")
                po_price = Decimal(row["unit_price"])
                if item.unit_price > po_price * (1 + PREIS_TOLERANZ):
                    add("PREIS_ABWEICHUNG", "WARNUNG",
                        f"'{item.description}': {item.unit_price} statt bestellter {po_price} "
                        f"(+{(item.unit_price / po_price - 1) * 100:.1f} %)")
    return found
