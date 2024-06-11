"""Kommandozeile.

  python -m rechnung erzeugen                      Testdaten nach data/ schreiben
  python -m rechnung pruefen data/rechnungen       Prüfbericht, optional --csv bericht.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from .checks import MasterData, check_batch, status
from .extract import read_pdf
from .generate import DATA, write_all


def report(folder: Path, master_folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    invoices = [read_pdf(p) for p in sorted(folder.glob("*.pdf"))]
    findings = check_batch(invoices, MasterData.load(master_folder))
    detail = pd.DataFrame([f.__dict__ for f in findings], columns=["source", "code", "severity", "message"])
    overview = pd.DataFrame([{
        "datei": inv.source,
        "lieferant": inv.supplier_name,
        "nummer": inv.number,
        "brutto": inv.gross_total,
        "status": status([f for f in findings if f.source == inv.source]),
        "befunde": ", ".join(sorted({f.code for f in findings if f.source == inv.source})),
    } for inv in invoices])
    return overview, detail


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m rechnung")
    sub = parser.add_subparsers(dest="befehl", required=True)
    sub.add_parser("erzeugen", help="Testrechnungen und Stammdaten erzeugen")
    p = sub.add_parser("pruefen", help="Rechnungs-PDFs prüfen")
    p.add_argument("ordner", nargs="?", default=str(DATA / "rechnungen"))
    p.add_argument("--stammdaten", default=str(DATA))
    p.add_argument("--csv", help="Befunde als CSV speichern")
    args = parser.parse_args()

    if args.befehl == "erzeugen":
        expected = write_all()
        print(f"{len(expected)} Rechnungen in {DATA / 'rechnungen'}, davon {sum(bool(v) for v in expected.values())} mit Fehler")
        return 0

    overview, detail = report(Path(args.ordner), Path(args.stammdaten))
    pd.set_option("display.width", 160, "display.max_colwidth", 80)
    print(overview.to_string(index=False))
    print()
    print(overview["status"].value_counts().to_string())
    if args.csv:
        detail.to_csv(args.csv, index=False, encoding="utf-8-sig")  # mit BOM, damit Excel die Umlaute erkennt
        print(f"\nBefunde gespeichert: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
