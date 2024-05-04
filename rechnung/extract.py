"""Liest Rechnungsfelder aus dem Text eines PDFs.

Die Regeln passen auf das Layout der Testrechnungen. Echte Eingangsrechnungen
sehen bei jedem Lieferanten anders aus; dafür nimmt man in der Praxis
strukturierte E-Rechnungen (in Österreich ebInterface, sonst ZUGFeRD oder
XRechnung) oder ein trainiertes Extraktionsmodell. Die Prüflogik in
checks.py ist davon unabhängig und arbeitet nur mit dem Invoice-Objekt.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

from .model import Invoice, LineItem, parse_amount

AMOUNT = r"(-?[\d.]+,\d{2})"
ITEM = re.compile(r"^(\d+)\s+(.+?)\s{2,}([\d.,]+)\s+" + AMOUNT + r"\s+(\d+)%\s+" + AMOUNT + r"\s*$")


def _search(pattern: str, text: str) -> str | None:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _date(value: str | None):
    return datetime.strptime(value, "%d.%m.%Y").date() if value else None


def parse_text(text: str, source: str = "") -> Invoice:
    lines = [line.rstrip() for line in text.splitlines()]
    inv = Invoice(source=source)
    inv.supplier_name = lines[0].strip() if lines else None
    inv.supplier_address = lines[1].strip() if len(lines) > 1 else None
    inv.supplier_uid = _search(r"^UID:\s*(\S+)", text)

    if "Rechnung an:" in lines:
        i = lines.index("Rechnung an:")
        inv.recipient_name = lines[i + 1].strip() if i + 1 < len(lines) else None
        inv.recipient_address = lines[i + 2].strip() if i + 2 < len(lines) else None
    inv.recipient_uid = _search(r"^Ihre UID:\s*(\S+)", text)

    inv.number = _search(r"^Rechnungsnummer:\s*(\S+)", text)
    inv.invoice_date = _date(_search(r"^Rechnungsdatum:\s*([\d.]+)", text))
    inv.service_date = _date(_search(r"^Leistungsdatum:\s*([\d.]+)", text))
    inv.po_number = _search(r"^Bestellnummer:\s*(\S+)", text)

    for line in lines:
        m = ITEM.match(line.strip())
        if m:
            inv.items.append(LineItem(
                description=m.group(2).strip(),
                quantity=parse_amount(m.group(3)) if "," in m.group(3) else parse_amount(m.group(3) + ",00"),
                unit_price=parse_amount(m.group(4)),
                vat_rate=int(m.group(5)),
                net=parse_amount(m.group(6)),
            ))

    net = _search(r"^Summe netto:\s*" + AMOUNT, text)
    inv.net_total = parse_amount(net) if net else None
    for rate, amount in re.findall(r"^USt (\d+) %:\s*" + AMOUNT, text, re.MULTILINE):
        inv.vat[int(rate)] = parse_amount(amount)
    gross = _search(r"^Gesamtbetrag:\s*" + AMOUNT, text)
    inv.gross_total = parse_amount(gross) if gross else None
    iban = _search(r"IBAN\s+([A-Z]{2}[\d ]{10,40}\d)", text)
    inv.iban = iban.replace(" ", "") if iban else None
    return inv


def read_pdf(path: str | Path) -> Invoice:
    path = Path(path)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return parse_text(text, source=path.name)
