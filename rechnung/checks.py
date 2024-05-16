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
