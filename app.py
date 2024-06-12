"""Streamlit-Oberfläche: streamlit run app.py"""

import tempfile
from pathlib import Path

import streamlit as st

from rechnung.__main__ import report
from rechnung.generate import DATA, write_all

st.set_page_config(page_title="Rechnungsprüfung", layout="wide")
st.title("Eingangsrechnungen prüfen")
st.caption("Pflichtangaben nach § 11 UStG, Rechenfehler, UID und IBAN, Dubletten, Abgleich mit Bestellungen")

if not (DATA / "rechnungen").exists():
    write_all()

with st.sidebar:
    uploads = st.file_uploader("Eigene Rechnungs-PDFs", type="pdf", accept_multiple_files=True)
    st.caption("Ohne Upload werden die 25 Testrechnungen geprüft. Stammdaten und Bestellungen kommen aus data/.")

folder = DATA / "rechnungen"
if uploads:
    folder = Path(tempfile.mkdtemp())
    for f in uploads:
        (folder / Path(f.name).name).write_bytes(f.getvalue())

overview, detail = report(folder, DATA)

counts = overview["status"].value_counts()
c1, c2, c3 = st.columns(3)
c1.metric("freigeben", int(counts.get("freigeben", 0)))
c2.metric("prüfen", int(counts.get("prüfen", 0)))
c3.metric("zurückweisen", int(counts.get("zurückweisen", 0)))

COLORS = {"freigeben": "#dcfce7", "prüfen": "#fef9c3", "zurückweisen": "#fee2e2"}
st.dataframe(
    overview.style.map(lambda v: f"background-color: {COLORS.get(v, '')}", subset=["status"]),
    hide_index=True,
)

st.subheader("Befunde im Detail")
choice = st.selectbox("Rechnung", overview["datei"])
rows = detail[detail["source"] == choice]
if rows.empty:
    st.success("Keine Auffälligkeiten.")
for _, r in rows.iterrows():
    (st.error if r["severity"] == "FEHLER" else st.warning)(f"**{r['code']}**: {r['message']}")

st.download_button("Befunde als CSV", detail.to_csv(index=False).encode("utf-8-sig"), "befunde.csv", "text/csv")
