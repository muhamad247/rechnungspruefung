from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from rechnung.checks import MasterData, check_batch, check_invoice, status
from rechnung.checksums import iban_valid, make_at_iban, make_uid, uid_valid
from rechnung.extract import read_pdf
from rechnung.generate import build, render_pdf, write_all
from rechnung.model import format_amount, parse_amount

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("daten")
    expected = write_all(out)
    invoices = [read_pdf(p) for p in sorted((out / "rechnungen").glob("*.pdf"))]
    return out, expected, invoices, MasterData.load(out)


def test_real_uid_is_valid_and_typo_is_not():
    assert uid_valid("ATU14189108")  # OMV AG, öffentlich bekannt
    assert not uid_valid("ATU14189109")
    assert not uid_valid("ATU1418910")
    assert not uid_valid("DE14189108")


def test_generated_uids_are_valid():
    assert all(uid_valid(make_uid(f"{n:07d}")) for n in range(0, 10_000_000, 777_777))


def test_iban_checksum():
    assert iban_valid("AT61 1904 3002 3457 3201")  # Beispiel-IBAN aus der Norm
    assert not iban_valid("AT61 1904 3002 3457 3202")
    assert not iban_valid("AT61190430023457320")  # eine Stelle zu kurz
    assert iban_valid(make_at_iban("20111", "28440011100"))


def test_amount_format_roundtrip():
    assert parse_amount("1.234,56") == Decimal("1234.56")
    assert format_amount(Decimal("1234567.8")) == "1.234.567,80"


def test_pdf_extraction_returns_what_was_written(tmp_path):
    for name, original in build()[1]:
        path = tmp_path / name
        render_pdf(original, path)
        assert read_pdf(path) == replace(original, source=name), name


@pytest.mark.parametrize("name", [f"rechnung_{n:02d}.pdf" for n in range(1, 26)])
def test_findings_match_injected_errors(generated, name):
    _, expected, invoices, master = generated
    findings = check_batch(invoices, master)
    got = sorted({f.code for f in findings if f.source == name})
    assert got == sorted(expected[name])


def test_status_follows_severity(generated):
    _, expected, invoices, master = generated
    findings = check_batch(invoices, master)
    by_file = {inv.source: [f for f in findings if f.source == inv.source] for inv in invoices}
    assert status(by_file["rechnung_01.pdf"]) == "freigeben"
    assert status(by_file["rechnung_20.pdf"]) == "prüfen"  # IBAN geändert: nur Warnung
    assert status(by_file["rechnung_12.pdf"]) == "zurückweisen"  # Summe falsch


def test_small_invoice_may_omit_recipient_and_number(generated):
    _, _, invoices, master = generated
    small = next(i for i in invoices if i.source == "rechnung_11.pdf")
    assert small.gross_total <= 400 and small.number is None and small.recipient_name is None
    assert check_invoice(small, master) == []
    # dieselbe Rechnung über 400 EUR wäre unvollständig
    bigger = replace(small, gross_total=Decimal("500.00"))
    assert "PFLICHTANGABE_FEHLT" in {f.code for f in check_invoice(bigger, master)}


def test_cli_and_streamlit_app_run():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    app.run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["11", "4", "10"]
