"""
NEN3140-beoordelingslogica.

Bron: EazyPAT 3140USB Gebruikershandleiding (Nieaf-Smitt / Mors Smitt B.V.),
Bijlage 3 (Specificaties, fabrieksinstelling goed/fout bereiken) en
Bijlage 4 (Afkeurgrenzen volgens NEN 3140).
"""

from dataclasses import dataclass, field
from typing import Optional, Literal

Klasse = Literal["I", "II", "snoer"]

DIAMETERS_MM2 = [1.5, 2.5, 4, 6, 10, 16, 25]

# Bron: Bijlage 4 van de volledige handleiding (MAN-EazyPAT USB V1.2, 17-03-2022),
# tabel "Lengte beschermingsleiding (m) x Aderdoorsnede (S) in mm2"
RPE_TABEL = {
    (0, 2):      {1.5: 0.22, 2.5: 0.21, 4: 0.21, 6: 0.21, 10: 0.20, 16: 0.20, 25: 0.20},
    (2, 5):      {1.5: 0.26, 2.5: 0.24, 4: 0.22, 6: 0.21, 10: 0.21, 16: 0.21, 25: 0.20},
    (5, 10):     {1.5: 0.32, 2.5: 0.27, 4: 0.24, 6: 0.23, 10: 0.22, 16: 0.21, 25: 0.21},
    (10, 15):    {1.5: 0.38, 2.5: 0.31, 4: 0.27, 6: 0.24, 10: 0.23, 16: 0.22, 25: 0.21},
    (15, 20):    {1.5: 0.43, 2.5: 0.34, 4: 0.29, 6: 0.26, 10: 0.24, 16: 0.22, 25: 0.21},
    (20, 25):    {1.5: 0.49, 2.5: 0.38, 4: 0.31, 6: 0.27, 10: 0.24, 16: 0.23, 25: 0.22},
    (25, 30):    {1.5: 0.55, 2.5: 0.41, 4: 0.31, 6: 0.29, 10: 0.25, 16: 0.23, 25: 0.22},
    (30, 35):    {1.5: 0.61, 2.5: 0.45, 4: 0.35, 6: 0.30, 10: 0.26, 16: 0.24, 25: 0.22},
    (35, 40):    {1.5: 0.67, 2.5: 0.48, 4: 0.38, 6: 0.32, 10: 0.27, 16: 0.24, 25: 0.23},
    (40, 45):    {1.5: 0.73, 2.5: 0.52, 4: 0.40, 6: 0.33, 10: 0.28, 16: 0.25, 25: 0.23},
    (45, 50):    {1.5: 0.78, 2.5: 0.55, 4: 0.42, 6: 0.35, 10: 0.29, 16: 0.25, 25: 0.24},
}

RISO_MIN_MOHM = {"I": 1.0, "II": 2.0, "snoer": 1.0}
LEKSTROOM_MAX_MA = {"I": 1.00, "II": 0.50}
LEKSTROOM_MAX_MA_KERAMISCH_LAAG = 7.00
LEKSTROOM_MAX_MA_KERAMISCH_HOOG = 15.00


def _tabel_diameter(diameter_mm2: float) -> float:
    for d in DIAMETERS_MM2:
        if diameter_mm2 <= d:
            return d
    return DIAMETERS_MM2[-1]


def rpe_grenswaarde(lengte_m: float, diameter_mm2: float) -> float:
    d = _tabel_diameter(diameter_mm2)
    for (lo, hi), rij in RPE_TABEL.items():
        if lo < lengte_m <= hi:
            return rij[d]
    # buiten het tabelbereik (>50m): niet gedekt door de handleiding,
    # neem voorzichtigheidshalve de strengste (laagste) grens van de tabel
    return min(rij[d] for rij in RPE_TABEL.values())


@dataclass
class Oordeel:
    ok: Optional[bool]
    toelichting: str


def beoordeel_rpe(rpe_ohm: Optional[float], lengte_m: Optional[float] = None,
                   diameter_mm2: Optional[float] = None) -> Oordeel:
    if rpe_ohm is None:
        return Oordeel(None, "niet gemeten")
    if rpe_ohm < 0.2:
        return Oordeel(True, "< 0.2 \u03a9 \u2014 altijd goed")
    if rpe_ohm > 1.0:
        return Oordeel(False, "> 1.0 \u03a9 \u2014 afgekeurd")
    if lengte_m is None or diameter_mm2 is None:
        return Oordeel(None, "tussen 0.2 en 1.0 \u03a9: snoerlengte + aderdiameter nodig om te beoordelen")
    grens = rpe_grenswaarde(lengte_m, diameter_mm2)
    ok = rpe_ohm <= grens
    return Oordeel(ok, f"grenswaarde uit tabel: {grens} \u03a9")


def beoordeel_riso(riso_mohm: Optional[float], klasse: Klasse) -> Oordeel:
    if riso_mohm is None:
        return Oordeel(None, "niet gemeten")
    grens = RISO_MIN_MOHM[klasse]
    ok = riso_mohm > grens
    return Oordeel(ok, f"grens: > {grens} M\u03a9 (klasse {klasse})")


def beoordeel_lekstroom(ma: Optional[float], klasse: Klasse,
                         keramisch_vermogen_kw: Optional[float] = None) -> Oordeel:
    if klasse == "snoer":
        return Oordeel(None, "niet van toepassing op snoeren")
    if ma is None:
        return Oordeel(None, "niet gemeten")
    if klasse == "I" and keramisch_vermogen_kw is not None:
        grens = (LEKSTROOM_MAX_MA_KERAMISCH_LAAG if keramisch_vermogen_kw <= 6
                 else LEKSTROOM_MAX_MA_KERAMISCH_HOOG)
        ok = ma < grens
        return Oordeel(ok, f"grens: < {grens} mA (keramisch)")
    grens = LEKSTROOM_MAX_MA[klasse]
    ok = ma < grens
    return Oordeel(ok, f"grens: < {grens} mA (klasse {klasse})")


@dataclass
class Eindoordeel:
    status: str
    reden: str
    deel_oordelen: dict = field(default_factory=dict)


def bepaal_eindoordeel(visuele_inspectie_ok: bool, klasse: Klasse,
                        rpe: Oordeel, riso: Oordeel, lekstroom: Oordeel) -> Eindoordeel:
    deel = {"rpe": rpe, "riso": riso, "lekstroom": lekstroom}
    if not visuele_inspectie_ok:
        return Eindoordeel("AFGEKEURD", "visuele inspectie niet akkoord", deel)
    relevante = []
    if klasse in ("I", "snoer"):
        relevante.append(rpe)
        if rpe.ok is False:
            return Eindoordeel("AFGEKEURD", "Rpe buiten grenswaarde", deel)
    relevante.append(riso)
    if klasse != "snoer":
        relevante.append(lekstroom)
    if any(o.ok is False for o in relevante):
        return Eindoordeel("AFGEKEURD", "een of meer metingen buiten grenswaarde", deel)
    if any(o.ok is None for o in relevante):
        return Eindoordeel("ONVOLLEDIG", "niet alle verplichte metingen ingevuld", deel)
    return Eindoordeel("GOEDGEKEURD", "alle metingen binnen grenswaarde", deel)
