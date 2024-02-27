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
