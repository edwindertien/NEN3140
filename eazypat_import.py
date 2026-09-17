"""
Parser voor de ruwe data die de EazyPAT 3140 USB over de seriele poort stuurt
(zie eazypat_lezen.py). Formaat vastgesteld aan de hand van een echte export:
puntkomma-gescheiden, decimale komma, en < / > als grenswaarde-aanduiding
wanneer een meting buiten het bereik van de tester valt.

Belangrijk: er bestaan DRIE soorten lekstroommeting in dit format, niet twee:
  - "Lekstroom"            : directe/reele lekstroom (klasse I)
  - "Aanraaklekstroom"     : aanraaklekstroom (gebruikelijk bij klasse II)
  - "Vervangende Lekstroom": vervangende methode (zonder netspanning)
"""

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional


@dataclass
class GemetenWaarde:
    waarde: Optional[float]      # numerieke waarde, of None als niet gemeten
    eenheid: str
    resultaat: str                # "Goed" / "Fout" / "" zoals door de tester zelf bepaald
    kwalificatie: str = ""        # "<", ">" of "" - geeft aan of de tester een grenswaarde toonde


def _parse_getal(ruw: str) -> tuple[Optional[float], str]:
    """"<0,15" -> (0.15, '<'); "0,22" -> (0.22, ''); "" -> (None, '')"""
    ruw = (ruw or "").strip()
    if not ruw:
        return None, ""
    kwalificatie = ""
    if ruw[0] in "<>":
        kwalificatie = ruw[0]
        ruw = ruw[1:]
    ruw = ruw.replace(",", ".")
    try:
        return float(ruw), kwalificatie
    except ValueError:
        return None, ""


def _parse_datum(ruw: str) -> Optional[date]:
    ruw = (ruw or "").strip()
    if not ruw:
        return None
    try:
        return datetime.strptime(ruw, "%d/%m/%Y").date()
    except ValueError:
        return None


@dataclass
class EazyPatMeting:
    testobject_nummer: str
    omschrijving: str
    laatste_testdatum: Optional[date]
    laatste_testresultaat: str
    klasse: str  # "I" of "II", afgeleid uit welke velden gevuld zijn

    aarde: GemetenWaarde
    lekstroom: GemetenWaarde
    aanraaklekstroom: GemetenWaarde
    vervangende_lekstroom: GemetenWaarde
    isolatie: GemetenWaarde

    opmerkingen: str


def parse_eazypat_csv(pad) -> list[EazyPatMeting]:
    pad = Path(pad)
    resultaten = []
    with open(pad, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for rij in reader:
            aarde_w, aarde_k = _parse_getal(rij.get("Aarde", ""))
            lek_w, lek_k = _parse_getal(rij.get("Lekstroom", ""))
            aanraak_w, aanraak_k = _parse_getal(rij.get("Aanraaklekstroom", ""))
            vervang_w, vervang_k = _parse_getal(rij.get("Vervangende Lekstroom", ""))
            iso_w, iso_k = _parse_getal(rij.get("Isolatie Weerstand", ""))

            # Klasse afleiden: Aarde ingevuld -> klasse I; anders klasse II
            # (klasse II-apparaten hebben geen beschermingsleiding, dus geen Aarde-meting)
            klasse = "I" if aarde_w is not None else "II"

            resultaten.append(EazyPatMeting(
                testobject_nummer=rij.get("Testobject nummer", "").strip(),
                omschrijving=rij.get("Omschrijving", "").strip(),
                laatste_testdatum=_parse_datum(rij.get("Laatste Testdatum", "")),
                laatste_testresultaat=rij.get("Laatste Testresultaat", "").strip(),
                klasse=klasse,
                aarde=GemetenWaarde(aarde_w, rij.get("Aarde Eenheid", ""), rij.get("Aarde resultaat", ""), aarde_k),
                lekstroom=GemetenWaarde(lek_w, rij.get("Lekstroom Eenheid", ""), rij.get("Lekstroom resultaat", ""), lek_k),
                aanraaklekstroom=GemetenWaarde(aanraak_w, rij.get("Aanraaklek Eenheid", ""), rij.get("Aanraaklek Resultaat", ""), aanraak_k),
                vervangende_lekstroom=GemetenWaarde(vervang_w, rij.get("Vervangende Lek Eenheid", ""), rij.get("Vervangende Lek resultaat", ""), vervang_k),
                isolatie=GemetenWaarde(iso_w, rij.get("Isolatie Eenheid", ""), rij.get("Isolatie resultaat", ""), iso_k),
                opmerkingen=rij.get("Opmerkingen", "").strip(),
            ))
    return resultaten


if __name__ == "__main__":
    import sys
    pad = sys.argv[1] if len(sys.argv) > 1 else "eazypat_re_test/voorbeeld_export.csv"
    for m in parse_eazypat_csv(pad):
        print(f"#{m.testobject_nummer} ({m.klasse}) {m.omschrijving} - {m.laatste_testdatum} - {m.laatste_testresultaat}")
        if m.aarde.waarde is not None:
            print(f"    Aarde: {m.aarde.kwalificatie}{m.aarde.waarde} {m.aarde.eenheid} -> {m.aarde.resultaat}")
        if m.lekstroom.waarde is not None:
            print(f"    Lekstroom: {m.lekstroom.kwalificatie}{m.lekstroom.waarde} {m.lekstroom.eenheid} -> {m.lekstroom.resultaat}")
        if m.aanraaklekstroom.waarde is not None:
            print(f"    Aanraaklekstroom: {m.aanraaklekstroom.kwalificatie}{m.aanraaklekstroom.waarde} {m.aanraaklekstroom.eenheid} -> {m.aanraaklekstroom.resultaat}")
        if m.vervangende_lekstroom.waarde is not None:
            print(f"    Vervangende lekstroom: {m.vervangende_lekstroom.kwalificatie}{m.vervangende_lekstroom.waarde} {m.vervangende_lekstroom.eenheid} -> {m.vervangende_lekstroom.resultaat}")
        if m.isolatie.waarde is not None:
            print(f"    Isolatie: {m.isolatie.kwalificatie}{m.isolatie.waarde} {m.isolatie.eenheid} -> {m.isolatie.resultaat}")
