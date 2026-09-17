"""
Apparatenkeur - standalone Python-applicatie (Flask + lokale CSV-bestanden)

Draai lokaal met:  python app.py
Open dan in een browser: http://localhost:8000
"""

import csv
import io
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from flask import Flask, request, jsonify, send_file, send_from_directory, abort

import nen3140
import eazypat_import
import import_apparaten

BASE = Path(__file__).parent
DATA = BASE / "data"
FOTOS = DATA / "fotos"
APPARATEN_CSV = DATA / "apparaten.csv"
KEURINGEN_CSV = DATA / "keuringen.csv"

DATA.mkdir(exist_ok=True)
FOTOS.mkdir(exist_ok=True)

APPARAAT_VELDEN = [
    "nummer", "categorie", "omschrijving", "fabrikant", "serienummer", "keurmerk",
    "klasse", "keuringstermijn_maanden", "kabellengte_m", "kabeldiameter_mm2",
    "aanschaf", "laatst_gekeurd", "volgende_keuring", "status",
]

KEURING_VELDEN = [
    "nummer", "datum_tijd", "keurmeester", "bron",
    "visuele_inspectie_tekst", "visuele_inspectie_akkoord",
    "rpe_ohm", "rpe_lengte_m", "rpe_diameter_mm2", "rpe_oordeel",
    "riso_mohm", "riso_oordeel",
    "lekstroom_ma", "lekstroom_type", "keramisch_vermogen_kw", "lekstroom_oordeel",
    "eindoordeel", "eindoordeel_reden",
    "foto_apparaat", "foto_mankementen", "opmerkingen",
]


def _ensure_csv(path: Path, velden: list[str]):
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=velden).writeheader()


def _read_csv(path: Path, velden: list[str]) -> list[dict]:
    _ensure_csv(path, velden)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _append_csv(path: Path, velden: list[str], row: dict):
    _ensure_csv(path, velden)
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=velden).writerow(row)


def _rewrite_csv(path: Path, velden: list[str], rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=velden)
        w.writeheader()
        w.writerows(rows)


def _get_apparaat(nummer: str) -> Optional[dict]:
    for r in _read_csv(APPARATEN_CSV, APPARAAT_VELDEN):
        if r["nummer"] == nummer:
            return r
    return None


app = Flask(__name__, static_folder="static", static_url_path="/static")
app.json.sort_keys = False  # kolomvolgorde in de JSON-API's moet de logische
                             # volgorde uit APPARAAT_VELDEN/KEURING_VELDEN volgen,
                             # niet alfabetisch (belangrijk voor de tabelweergave)


@app.get("/")
def root():
    return send_from_directory(BASE / "static", "index.html")


@app.get("/api/apparaten")
def lijst_apparaten():
    q = request.args.get("q")
    rows = _read_csv(APPARATEN_CSV, APPARAAT_VELDEN)
    if q:
        q = q.lower()
        rows = [r for r in rows if q in r["nummer"].lower() or q in r["omschrijving"].lower()]
    return jsonify(rows)


@app.get("/api/apparaat/<nummer>")
def get_apparaat(nummer):
    apparaat = _get_apparaat(nummer)
    if apparaat is None:
        abort(404, description="Apparaat niet gevonden")
    keuringen = [k for k in _read_csv(KEURINGEN_CSV, KEURING_VELDEN) if k["nummer"] == nummer]
    keuringen.sort(key=lambda k: k["datum_tijd"], reverse=True)
    return jsonify({"apparaat": apparaat, "laatste_keuringen": keuringen[:5]})


@app.get("/api/keuringen")
def lijst_keuringen():
    nummer = request.args.get("nummer", "").strip()
    eindoordeel = request.args.get("eindoordeel", "").strip()
    vanaf = request.args.get("vanaf", "").strip()
    tot = request.args.get("tot", "").strip()

    rows = _read_csv(KEURINGEN_CSV, KEURING_VELDEN)
    if nummer:
        rows = [r for r in rows if nummer.lower() in r["nummer"].lower()]
    if eindoordeel:
        rows = [r for r in rows if r["eindoordeel"] == eindoordeel]
    if vanaf:
        rows = [r for r in rows if r["datum_tijd"][:10] >= vanaf]
    if tot:
        rows = [r for r in rows if r["datum_tijd"][:10] <= tot]

    rows.sort(key=lambda r: r["datum_tijd"], reverse=True)
    return jsonify(rows)


@app.post("/api/apparaat")
def maak_apparaat():
    f = request.form
    nummer = f["nummer"]
    rows = _read_csv(APPARATEN_CSV, APPARAAT_VELDEN)
    if any(r["nummer"] == nummer for r in rows):
        abort(400, description=f"Nummer {nummer} bestaat al")
    row = {
        "nummer": nummer,
        "categorie": f.get("categorie", ""),
        "omschrijving": f.get("omschrijving", ""),
        "fabrikant": f.get("fabrikant", ""),
        "serienummer": f.get("serienummer", ""),
        "keurmerk": f.get("keurmerk", ""),
        "klasse": f["klasse"],
        "keuringstermijn_maanden": f.get("keuringstermijn_maanden", "12"),
        "kabellengte_m": f.get("kabellengte_m", ""),
        "kabeldiameter_mm2": f.get("kabeldiameter_mm2", ""),
        "aanschaf": f.get("aanschaf", ""),
        "laatst_gekeurd": "", "volgende_keuring": "", "status": "actief",
    }
    _append_csv(APPARATEN_CSV, APPARAAT_VELDEN, row)
    return jsonify(row)


def _verwerk_keuring(
    nummer: str, keurmeester: str, bron: str,
    visuele_inspectie_tekst: str, visuele_inspectie_akkoord: bool,
    rpe_ohm: Optional[float], riso_mohm: Optional[float],
    lekstroom_ma: Optional[float], lekstroom_type: str,
    keramisch_vermogen_kw: Optional[float], opmerkingen: str,
    foto_apparaat_naam: str = "", foto_mankement_namen: Optional[list[str]] = None,
    datum: Optional[date] = None,
) -> dict:
    apparaten = _read_csv(APPARATEN_CSV, APPARAAT_VELDEN)
    apparaat = next((r for r in apparaten if r["nummer"] == nummer), None)
    if apparaat is None:
        abort(404, description=f"Apparaat {nummer} niet gevonden - registreer het eerst")

    klasse = apparaat["klasse"]
    lengte = float(apparaat["kabellengte_m"]) if apparaat.get("kabellengte_m") else None
    diameter = float(apparaat["kabeldiameter_mm2"]) if apparaat.get("kabeldiameter_mm2") else None

    rpe_oordeel = nen3140.beoordeel_rpe(rpe_ohm, lengte, diameter)
    riso_oordeel = nen3140.beoordeel_riso(riso_mohm, klasse)
    lekstroom_oordeel = nen3140.beoordeel_lekstroom(lekstroom_ma, klasse, keramisch_vermogen_kw)
    eind = nen3140.bepaal_eindoordeel(visuele_inspectie_akkoord, klasse, rpe_oordeel, riso_oordeel, lekstroom_oordeel)

    datum_tijd = datetime.combine(datum, datetime.now().time()) if datum else datetime.now()

    keuring_row = {
        "nummer": nummer,
        "datum_tijd": datum_tijd.isoformat(timespec="seconds"),
        "keurmeester": keurmeester,
        "bron": bron,
        "visuele_inspectie_tekst": visuele_inspectie_tekst,
        "visuele_inspectie_akkoord": visuele_inspectie_akkoord,
        "rpe_ohm": rpe_ohm if rpe_ohm is not None else "",
        "rpe_lengte_m": lengte if lengte is not None else "",
        "rpe_diameter_mm2": diameter if diameter is not None else "",
        "rpe_oordeel": rpe_oordeel.toelichting,
        "riso_mohm": riso_mohm if riso_mohm is not None else "",
        "riso_oordeel": riso_oordeel.toelichting,
        "lekstroom_ma": lekstroom_ma if lekstroom_ma is not None else "",
        "lekstroom_type": lekstroom_type,
        "keramisch_vermogen_kw": keramisch_vermogen_kw if keramisch_vermogen_kw is not None else "",
        "lekstroom_oordeel": lekstroom_oordeel.toelichting,
        "eindoordeel": eind.status,
        "eindoordeel_reden": eind.reden,
        "foto_apparaat": foto_apparaat_naam,
        "foto_mankementen": ";".join(foto_mankement_namen or []),
        "opmerkingen": opmerkingen,
    }
    _append_csv(KEURINGEN_CSV, KEURING_VELDEN, keuring_row)

    vandaag = datum_tijd.date()
    termijn = int(apparaat.get("keuringstermijn_maanden") or 12)
    maand = vandaag.month - 1 + termijn
    jaar = vandaag.year + maand // 12
    maand = maand % 12 + 1
    dag = min(vandaag.day, 28)
    volgende = date(jaar, maand, dag).isoformat()

    for r in apparaten:
        if r["nummer"] == nummer:
            r["laatst_gekeurd"] = vandaag.isoformat()
            r["volgende_keuring"] = volgende
            r["status"] = "actief" if eind.status == "GOEDGEKEURD" else (
                "afgekeurd" if eind.status == "AFGEKEURD" else r["status"])
    _rewrite_csv(APPARATEN_CSV, APPARAAT_VELDEN, apparaten)

    return {"keuring": keuring_row, "eindoordeel": eind.status, "reden": eind.reden}


@app.post("/api/keuring")
def nieuwe_keuring():
    f = request.form
    nummer = f["nummer"]

    tijdstempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    map_pad = FOTOS / nummer
    map_pad.mkdir(exist_ok=True)

    foto_apparaat_naam = ""
    foto_apparaat = request.files.get("foto_apparaat")
    if foto_apparaat is not None and foto_apparaat.filename:
        ext = Path(foto_apparaat.filename).suffix or ".jpg"
        foto_apparaat_naam = f"{tijdstempel}_apparaat{ext}"
        foto_apparaat.save(map_pad / foto_apparaat_naam)

    mankement_namen = []
    for i, foto in enumerate(request.files.getlist("foto_mankementen")):
        if foto and foto.filename:
            ext = Path(foto.filename).suffix or ".jpg"
            naam = f"{tijdstempel}_mankement{i+1}{ext}"
            foto.save(map_pad / naam)
            mankement_namen.append(naam)

    resultaat = _verwerk_keuring(
        nummer,
        f.get("keurmeester", ""),
        "app",
        f.get("visuele_inspectie_tekst", ""),
        f.get("visuele_inspectie_akkoord") == "true",
        f.get("rpe_ohm", type=float),
        f.get("riso_mohm", type=float),
        f.get("lekstroom_ma", type=float),
        f.get("lekstroom_type", ""),
        f.get("keramisch_vermogen_kw", type=float),
        f.get("opmerkingen", ""),
        foto_apparaat_naam, mankement_namen,
    )
    return jsonify(resultaat)


@app.post("/api/import/apparaten/analyseer")
def import_apparaten_analyseer():
    bestand = request.files["bestand"]
    extensie = Path(bestand.filename).suffix or ".xlsx"
    tijdelijk_pad = DATA / f"_tmp_apparaten_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}{extensie}"
    bestand.save(tijdelijk_pad)

    try:
        ruwe_rijen = import_apparaten.parse_apparatenbestand(tijdelijk_pad)
    except Exception as e:
        tijdelijk_pad.unlink(missing_ok=True)
        return jsonify({"fout": f"Kon bestand niet lezen: {e}"}), 400
    tijdelijk_pad.unlink(missing_ok=True)

    bestaande_nummers = {r["nummer"] for r in _read_csv(APPARATEN_CSV, APPARAAT_VELDEN)}
    geziene_nummers = set()

    nieuw, conflict, fout = [], [], []
    for i, ruwe_rij in enumerate(ruwe_rijen):
        resultaat = import_apparaten.valideer_rij(ruwe_rij, i, APPARAAT_VELDEN)
        nummer = resultaat["genormaliseerd"]["nummer"]

        if resultaat["fouten"]:
            fout.append(resultaat)
            continue
        if nummer in geziene_nummers:
            resultaat["fouten"].append("dubbel nummer binnen het geimporteerde bestand zelf")
            fout.append(resultaat)
            continue
        geziene_nummers.add(nummer)

        if nummer in bestaande_nummers:
            conflict.append(resultaat)
        else:
            nieuw.append(resultaat)

    return jsonify({"nieuw": nieuw, "conflict": conflict, "fout": fout, "totaal": len(ruwe_rijen)})


@app.post("/api/import/apparaten/bevestig")
def import_apparaten_bevestig():
    """Body: lijst van {genormaliseerd: {...apparaat_velden...}, actie: 'toevoegen'|'overschrijven'|'overslaan'}"""
    items = request.get_json()
    apparaten = _read_csv(APPARATEN_CSV, APPARAAT_VELDEN)
    apparaten_bij_nummer = {a["nummer"]: a for a in apparaten}

    resultaten = []
    for item in items:
        actie = item.get("actie", "toevoegen")
        data = item.get("genormaliseerd", {})
        nummer = (data.get("nummer") or "").strip()

        if actie == "overslaan" or not nummer:
            resultaten.append({"nummer": nummer, "status": "OVERGESLAGEN"})
            continue

        volledige_rij = {veld: (data.get(veld) or "") for veld in APPARAAT_VELDEN}
        if not volledige_rij.get("status"):
            volledige_rij["status"] = "actief"
        if not volledige_rij.get("keuringstermijn_maanden"):
            volledige_rij["keuringstermijn_maanden"] = "12"

        apparaten_bij_nummer[nummer] = volledige_rij
        resultaten.append({"nummer": nummer, "status": "OK"})

    _rewrite_csv(APPARATEN_CSV, APPARAAT_VELDEN, list(apparaten_bij_nummer.values()))
    return jsonify({"resultaten": resultaten, "aantal_ok": sum(1 for r in resultaten if r["status"] == "OK")})


def _kies_lekstroom(m: eazypat_import.EazyPatMeting):
    if m.lekstroom.waarde is not None:
        return m.lekstroom.waarde, "reeel"
    if m.aanraaklekstroom.waarde is not None:
        return m.aanraaklekstroom.waarde, "aanraak"
    if m.vervangende_lekstroom.waarde is not None:
        return m.vervangende_lekstroom.waarde, "vervangend"
    return None, ""


@app.post("/api/import/analyseer")
def import_analyseer():
    bestand = request.files["bestand"]
    tijdelijk_pad = DATA / f"_tmp_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    bestand.save(tijdelijk_pad)

    try:
        metingen = eazypat_import.parse_eazypat_csv(tijdelijk_pad)
    finally:
        tijdelijk_pad.unlink(missing_ok=True)

    apparaten = {r["nummer"]: r for r in _read_csv(APPARATEN_CSV, APPARAAT_VELDEN)}
    klaar, grijze_zone, onbekend = [], [], []

    for m in metingen:
        lek_waarde, lek_type = _kies_lekstroom(m)
        basis = {
            "eazypat_nummer": m.testobject_nummer,
            "omschrijving": m.omschrijving,
            "klasse_eazypat": m.klasse,
            "laatste_testdatum": m.laatste_testdatum.isoformat() if m.laatste_testdatum else "",
            "apparaat_oordeel": m.laatste_testresultaat,
            "aarde_ohm": m.aarde.waarde,
            "isolatie_mohm": m.isolatie.waarde,
            "lekstroom_ma": lek_waarde,
            "lekstroom_type": lek_type,
        }

        apparaat = apparaten.get(m.testobject_nummer)
        if apparaat is None:
            onbekend.append({**basis, "apparaat_nummer": None})
            continue

        lengte = float(apparaat["kabellengte_m"]) if apparaat.get("kabellengte_m") else None
        diameter = float(apparaat["kabeldiameter_mm2"]) if apparaat.get("kabeldiameter_mm2") else None

        grijze_zone_actief = (
            m.aarde.waarde is not None and 0.2 <= m.aarde.waarde <= 1.0
            and (lengte is None or diameter is None)
        )

        item = {**basis, "apparaat_nummer": apparaat["nummer"],
                "kabellengte_m": lengte, "kabeldiameter_mm2": diameter}

        if grijze_zone_actief:
            grijze_zone.append(item)
        else:
            klaar.append(item)

    return jsonify({"klaar": klaar, "grijze_zone": grijze_zone, "onbekend": onbekend,
                     "totaal": len(metingen)})


@app.post("/api/import/bevestig")
def import_bevestig():
    rijen = request.get_json()
    resultaten = []
    for rij in rijen:
        apparaat_nummer = rij.get("apparaat_nummer")
        if not apparaat_nummer:
            resultaten.append({"eazypat_nummer": rij.get("eazypat_nummer"), "status": "OVERGESLAGEN"})
            continue

        if rij.get("kabellengte_m") or rij.get("kabeldiameter_mm2"):
            apparaten = _read_csv(APPARATEN_CSV, APPARAAT_VELDEN)
            for a in apparaten:
                if a["nummer"] == apparaat_nummer:
                    if rij.get("kabellengte_m"):
                        a["kabellengte_m"] = str(rij["kabellengte_m"])
                    if rij.get("kabeldiameter_mm2"):
                        a["kabeldiameter_mm2"] = str(rij["kabeldiameter_mm2"])
            _rewrite_csv(APPARATEN_CSV, APPARAAT_VELDEN, apparaten)

        datum = None
        if rij.get("laatste_testdatum"):
            try:
                datum = date.fromisoformat(rij["laatste_testdatum"])
            except ValueError:
                pass

        try:
            resultaat = _verwerk_keuring(
                apparaat_nummer,
                rij.get("keurmeester", ""),
                "eazypat_import",
                rij.get("opmerkingen", f"Geimporteerd uit EazyPAT (testobject {rij.get('eazypat_nummer')})"),
                bool(rij.get("visuele_inspectie_akkoord", False)),
                rij.get("aarde_ohm"),
                rij.get("isolatie_mohm"),
                rij.get("lekstroom_ma"),
                rij.get("lekstroom_type", ""),
                rij.get("keramisch_vermogen_kw"),
                rij.get("opmerkingen", ""),
                datum=datum,
            )
            resultaten.append({"eazypat_nummer": rij.get("eazypat_nummer"),
                                "apparaat_nummer": apparaat_nummer,
                                "status": "OK",
                                "eindoordeel": resultaat["eindoordeel"]})
        except Exception as e:
            resultaten.append({"eazypat_nummer": rij.get("eazypat_nummer"),
                                "status": "FOUT", "reden": str(e)})

    return jsonify({"resultaten": resultaten,
                     "aantal_ok": sum(1 for r in resultaten if r["status"] == "OK")})


@app.get("/api/export/xlsx")
def exporteer_xlsx():
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "apparaten-export"
    kop = APPARAAT_VELDEN + ["laatste_keuring_eindoordeel", "laatste_keuring_datum"]
    ws.append(kop)
    for c in ws[1]:
        c.font = Font(bold=True)

    apparaten = _read_csv(APPARATEN_CSV, APPARAAT_VELDEN)
    keuringen = _read_csv(KEURINGEN_CSV, KEURING_VELDEN)
    for a in apparaten:
        laatste = [k for k in keuringen if k["nummer"] == a["nummer"]]
        laatste.sort(key=lambda k: k["datum_tijd"], reverse=True)
        laatste_oordeel = laatste[0]["eindoordeel"] if laatste else ""
        laatste_datum = laatste[0]["datum_tijd"] if laatste else ""
        ws.append([a.get(v, "") for v in APPARAAT_VELDEN] + [laatste_oordeel, laatste_datum])

    ws2 = wb.create_sheet("keuringen-log")
    ws2.append(KEURING_VELDEN)
    for c in ws2[1]:
        c.font = Font(bold=True)
    for k in keuringen:
        ws2.append([k.get(v, "") for v in KEURING_VELDEN])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True, download_name=f"apparatenkeur_export_{date.today().isoformat()}.xlsx",
    )


@app.get("/api/export/ods")
def exporteer_ods():
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableRow, TableCell
    from odf.text import P, Span
    from odf.style import Style, TextProperties

    doc = OpenDocumentSpreadsheet()
    vet = Style(name="Vet", family="text")
    vet.addElement(TextProperties(fontweight="bold", fontweightasian="bold", fontweightcomplex="bold"))
    doc.automaticstyles.addElement(vet)

    def voeg_rij_toe(table, waarden, koprij=False):
        row = TableRow()
        for w in waarden:
            cell = TableCell(valuetype="string")
            tekst = str(w) if w is not None else ""
            p = P()
            if koprij:
                p.addElement(Span(stylename=vet, text=tekst))
            else:
                p.addText(tekst)
            cell.addElement(p)
            row.addElement(cell)
        table.addElement(row)

    apparaten = _read_csv(APPARATEN_CSV, APPARAAT_VELDEN)
    keuringen = _read_csv(KEURINGEN_CSV, KEURING_VELDEN)

    t1 = Table(name="apparaten-export")
    kop1 = APPARAAT_VELDEN + ["laatste_keuring_eindoordeel", "laatste_keuring_datum"]
    voeg_rij_toe(t1, kop1, koprij=True)
    for a in apparaten:
        laatste = [k for k in keuringen if k["nummer"] == a["nummer"]]
        laatste.sort(key=lambda k: k["datum_tijd"], reverse=True)
        laatste_oordeel = laatste[0]["eindoordeel"] if laatste else ""
        laatste_datum = laatste[0]["datum_tijd"] if laatste else ""
        voeg_rij_toe(t1, [a.get(v, "") for v in APPARAAT_VELDEN] + [laatste_oordeel, laatste_datum])
    doc.spreadsheet.addElement(t1)

    t2 = Table(name="keuringen-log")
    voeg_rij_toe(t2, KEURING_VELDEN, koprij=True)
    for k in keuringen:
        voeg_rij_toe(t2, [k.get(v, "") for v in KEURING_VELDEN])
    doc.spreadsheet.addElement(t2)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return send_file(
        buf, mimetype="application/vnd.oasis.opendocument.spreadsheet",
        as_attachment=True, download_name=f"apparatenkeur_export_{date.today().isoformat()}.ods",
    )


@app.get("/api/foto/<nummer>/<bestandsnaam>")
def get_foto(nummer, bestandsnaam):
    pad = FOTOS / nummer / bestandsnaam
    if not pad.exists():
        abort(404)
    return send_file(pad)


if __name__ == "__main__":
    import os
    from netwerk_setup import detecteer_lokaal_ip, vind_bestaand_certificaat, genereer_certificaat_met_mkcert, toon_qr_in_terminal

    ip = detecteer_lokaal_ip()
    certs_map = BASE / "certs"
    cert_pad, sleutel_pad = vind_bestaand_certificaat(certs_map, ip)

    # Flask's debug-herlader voert dit bestand een tweede keer uit in een
    # subproces zodra je code wijzigt (WERKZEUG_RUN_MAIN staat dan aan). We
    # willen het certificaat maar een keer aanmaken en de QR-code maar een
    # keer tonen - dat gebeurt dus alleen in het eerste (bewakende) proces.
    # Het subproces vindt het certificaat vervolgens gewoon terug op schijf.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        if cert_pad:
            print(f"Bestaand certificaat hergebruikt: {cert_pad}")
        else:
            cert_pad, sleutel_pad = genereer_certificaat_met_mkcert(certs_map, ip)
        protocol = "https" if cert_pad else "http"
        toon_qr_in_terminal(f"{protocol}://{ip}:8000")

    if cert_pad:
        app.run(host="0.0.0.0", port=8000, debug=True, ssl_context=(str(cert_pad), str(sleutel_pad)))
    else:
        app.run(host="0.0.0.0", port=8000, debug=True)