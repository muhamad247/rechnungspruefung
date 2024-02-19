"""Prüfziffern für österreichische UID-Nummern und IBANs.

Eine gültige Prüfziffer heißt nur, dass die Nummer richtig aufgebaut ist.
Ob die UID tatsächlich vergeben ist, zeigt erst eine Abfrage im
EU-System VIES oder in FinanzOnline.
"""

from __future__ import annotations

import re

_UID = re.compile(r"^ATU\d{8}$")
_WEIGHTS = (1, 2, 1, 2, 1, 2, 1)


def _uid_check_digit(seven_digits: str) -> int:
    total = 0
    for digit, weight in zip(seven_digits, _WEIGHTS):
        product = int(digit) * weight
        total += product // 10 + product % 10  # Quersumme
    return (10 - (total + 4) % 10) % 10


def uid_valid(uid: str | None) -> bool:
    """ATU + 8 Ziffern, die letzte ist die Prüfziffer."""
    if not uid:
        return False
    uid = uid.replace(" ", "").upper()
    return bool(_UID.match(uid)) and _uid_check_digit(uid[3:10]) == int(uid[10])


def make_uid(seven_digits: str) -> str:
    """Baut aus 7 Ziffern eine formal gültige UID (für Testdaten)."""
    return f"ATU{seven_digits}{_uid_check_digit(seven_digits)}"


def _iban_number(iban: str) -> int:
    rearranged = iban[4:] + iban[:4]
    return int("".join(str(int(ch, 36)) for ch in rearranged))


def normalize_iban(iban: str | None) -> str:
    return (iban or "").replace(" ", "").upper()


def iban_valid(iban: str | None) -> bool:
    """Prüfsumme nach ISO 13616 (Modulo 97). Österreich: AT + 2 Prüfziffern + 16 Ziffern."""
    iban = normalize_iban(iban)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    if iban.startswith("AT") and len(iban) != 20:
        return False
    return _iban_number(iban) % 97 == 1


def make_at_iban(bank_code: str, account: str) -> str:
    """Formal gültige österreichische IBAN aus Bankleitzahl (5) und Kontonummer (11)."""
    bban = f"{bank_code:0>5}{account:0>11}"
    check = 98 - _iban_number(f"AT00{bban}") % 97
    return f"AT{check:02d}{bban}"


def format_iban(iban: str) -> str:
    iban = normalize_iban(iban)
    return " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))
