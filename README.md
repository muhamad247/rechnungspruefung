# Prüfung von Eingangsrechnungen

Liest Rechnungs-PDFs aus und prüft sie, bevor sie bezahlt werden: Pflichtangaben nach § 11 UStG, Rechenfehler, Steuersätze, UID- und IBAN-Prüfziffern, geänderte Bankverbindungen, doppelte Rechnungen und den Abgleich mit der Bestellung. Am Ende steht pro Rechnung *freigeben*, *prüfen* oder *zurückweisen*.

## Prüfregeln

| Code | Schwere | Regel |
|---|---|---|
| `PFLICHTANGABE_FEHLT` | Fehler | Pflichtangaben je nach Betrag: bis 400 EUR brutto genügt eine Kleinbetragsrechnung, darüber u. a. Empfänger, Rechnungsnummer, Leistungsdatum und UID des Lieferanten |
| `UID_EMPFAENGER_FEHLT` | Fehler | über 10.000 EUR brutto muss unsere UID auf der Rechnung stehen |
| `UID_EMPFAENGER_FALSCH` | Fehler | Empfänger-UID ist nicht unsere |
| `UID_UNGUELTIG` | Fehler | Prüfziffer der Lieferanten-UID stimmt nicht |
| `POSITION_FALSCH` | Fehler | Menge × Einzelpreis ≠ Positionsbetrag |
| `SUMME_FALSCH` | Fehler | Positionen ≠ Nettosumme oder Netto + USt ≠ Gesamtbetrag |
| `UST_FALSCH` | Fehler | Steuerbetrag passt nicht zu Satz und Bemessungsgrundlage |
| `STEUERSATZ_UNGUELTIG` | Fehler | kein österreichischer Satz (20, 13, 10 oder 0 %) |
| `IBAN_UNGUELTIG` | Fehler | Prüfsumme der IBAN falsch (Modulo 97) |
| `DUBLETTE` | Fehler | gleicher Lieferant und gleiche Rechnungsnummer wurde schon geprüft |
| `IBAN_GEAENDERT` | Warnung | IBAN weicht von den Stammdaten ab |
| `PREIS_ABWEICHUNG` | Warnung | Einzelpreis mehr als 2 % über dem bestellten |
| `MENGE_UEBERSCHRITTEN` | Warnung | mehr berechnet als bestellt |
| `OHNE_BESTELLUNG` | Warnung | keine passende Bestellung (Kleinbeträge ohne Bestellnummer sind erlaubt) |

Fehler heißt: so nicht zahlen. Warnung heißt: ein Mensch schaut vor der Zahlung drauf. Die geänderte IBAN ist bewusst nur eine Warnung, aber die wichtigste: Gefälschte Rechnungen mit der Bankverbindung des Betrügers sind ein häufiges Betrugsmuster. Die Gegenmaßnahme ist ein Rückruf beim Lieferanten unter der bekannten Nummer.

## Testdaten

Die 25 Rechnungen in `data/rechnungen` stammen von fünf erfundenen Lieferanten. 14 davon enthalten absichtlich genau einen Fehler, einer pro Regel. Welcher, steht in `data/erwartet.json`. Die Tests prüfen, dass genau diese Befunde kommen, und bei den elf sauberen Rechnungen keiner. Darunter ist auch eine Kleinbetragsrechnung ohne Empfänger und Rechnungsnummer, die korrekt durchgehen muss.

```
python -m rechnung pruefen

freigeben       11
zurückweisen    10
prüfen           4
```

Alle Firmen, UID-Nummern und IBANs sind frei erfunden. Die Nummern haben gültige Prüfziffern, damit nur die absichtlich falschen auffallen.

## Starten

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

python -m rechnung pruefen                      # Bericht in der Konsole
python -m rechnung pruefen --csv befunde.csv    # zusätzlich als CSV (öffnet sauber in Excel)
python -m rechnung erzeugen                     # Testdaten neu erzeugen
streamlit run app.py                            # Oberfläche mit Upload
pytest
```

## Aufbau

```
rechnung/
  model.py       Rechnung und Positionen, Beträge als Decimal statt float
  extract.py     PDF-Text auslesen und Felder erkennen
  checks.py      Prüfregeln, Dublettenprüfung, Status
  checksums.py   Prüfziffern für UID (ATU) und IBAN
  generate.py    Testdaten: Lieferanten, Bestellungen, Rechnungs-PDFs, erwartete Befunde
app.py           Streamlit-Oberfläche
data/            Stammdaten, Bestellungen, Testrechnungen
```

## Grenzen

- **Die Extraktion passt nur auf das Layout der Testrechnungen.** Echte Rechnungen sehen bei jedem Lieferanten anders aus. In der Praxis nimmt man strukturierte E-Rechnungen (in Österreich ebInterface, sonst ZUGFeRD oder XRechnung) oder ein trainiertes Extraktionsmodell. Die Prüfregeln arbeiten nur mit dem `Invoice`-Objekt und bleiben dabei gleich.
- **Eine gültige Prüfziffer heißt nicht, dass die UID vergeben ist.** Dafür braucht es eine Abfrage in VIES oder FinanzOnline.
- **Keine Steuerberatung:** Sonderfälle wie Reverse Charge oder innergemeinschaftliche Lieferungen sind nicht abgebildet.

Beträge werden durchgehend als `Decimal` gerechnet. Mit `float` würde z. B. `0.1 + 0.2` nicht genau `0.3` ergeben, und Cent-Vergleiche würden zufällig scheitern.
