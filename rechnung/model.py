"""Datenmodell einer Rechnung und Zahlenformat."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_amount(text: str) -> Decimal:
    """'1.234,56' -> Decimal('1234.56')"""
    return money(text.strip().replace(".", "").replace(",", "."))


def format_amount(value: Decimal) -> str:
    """Decimal('1234.56') -> '1.234,56'"""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@dataclass
class LineItem:
    description: str
    quantity: Decimal
    unit_price: Decimal
    vat_rate: int  # Prozent
    net: Decimal


@dataclass
class Invoice:
    source: str = ""
    supplier_name: str | None = None
    supplier_address: str | None = None
    supplier_uid: str | None = None
    recipient_name: str | None = None
    recipient_address: str | None = None
    recipient_uid: str | None = None
    number: str | None = None
    invoice_date: date | None = None
    service_date: date | None = None
    po_number: str | None = None
    items: list[LineItem] = field(default_factory=list)
    net_total: Decimal | None = None
    vat: dict[int, Decimal] = field(default_factory=dict)  # Steuersatz -> Steuerbetrag
    gross_total: Decimal | None = None
    iban: str | None = None

    @property
    def vat_total(self) -> Decimal:
        return sum(self.vat.values(), Decimal("0.00"))
