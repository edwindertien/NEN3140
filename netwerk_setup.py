"""
Netwerkopzet voor het lokaal draaien van de apparatenkeur-server.

Doet drie dingen bij het opstarten:
  1. Bepaalt het LAN-IP-adres van deze machine (waarmee de telefoon verbinding maakt).
  2. Zorgt voor een geldig, vertrouwd HTTPS-certificaat voor dat IP-adres, via
     mkcert - zonder dat je zelf iets hoeft te genereren of te hernoemen.
  3. Toont een scanbare QR-code in de terminal die direct naar de juiste
     https://<ip>:8000 wijst.

Vereist eenmalig (op de Mac): `brew install mkcert && mkcert -install`.
Die stap installeert een lokale CA in de systeem-sleutelhanger; daarna
ondertekent mkcert stilzwijgend elk certificaat dat deze module aanvraagt,
en wordt dat door elk toestel vertrouwd waar diezelfde CA ooit op is
geinstalleerd (dus ook je telefoon, als je die stap eerder hebt gedaan).

Zonder mkcert werkt de server nog steeds - dan gewoon via http:// in plaats
van https://, met een duidelijke melding waarom en hoe dat te verhelpen is.
"""

import shutil
import socket
import subprocess
from pathlib import Path
from typing import Optional


def detecteer_lokaal_ip() -> str:
    """LAN-IP-adres van deze machine, zonder daadwerkelijk iets te versturen."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def vind_bestaand_certificaat(certs_map: Path, ip: str):
    """Hergebruikt een certificaat als er al eentje is opgeslagen voor dit IP,
    of - voor de overgang - een certificaat dat je zelf handmatig hebt
    neergezet (in certs/ of in de projectmap zelf, onder cert.pem/key.pem of
    de oorspronkelijke mkcert-bestandsnaam met -key.pem)."""
    project_map = certs_map.parent

    cert_pad = certs_map / f"{ip}.pem"
    sleutel_pad = certs_map / f"{ip}-key.pem"
    if cert_pad.exists() and sleutel_pad.exists():
        return cert_pad, sleutel_pad

    for map_pad in (certs_map, project_map):
        vaste_cert = map_pad / "cert.pem"
        vaste_sleutel = map_pad / "key.pem"
        if vaste_cert.exists() and vaste_sleutel.exists():
            return vaste_cert, vaste_sleutel

    for map_pad in (certs_map, project_map):
        if not map_pad.exists():
            continue
        for sleutel_bestand in map_pad.glob("*-key.pem"):
            cert_bestand = map_pad / sleutel_bestand.name.replace("-key.pem", ".pem")
            if cert_bestand.exists():
                return cert_bestand, sleutel_bestand

    return None, None


def genereer_certificaat_met_mkcert(certs_map: Path, ip: str):
    """Roept mkcert aan om een nieuw certificaat te maken voor dit IP-adres
    (plus localhost/127.0.0.1), opgeslagen als certs/<ip>.pem + <ip>-key.pem.
    Geeft (None, None) terug als mkcert niet geinstalleerd is."""
    mkcert_pad = shutil.which("mkcert")
    if not mkcert_pad:
        print("Geen certificaat gevonden en mkcert niet geinstalleerd.")
        print("Voor HTTPS (nodig voor NFC/camera op de telefoon), eenmalig op de Mac:")
        print("  brew install mkcert && mkcert -install")
        return None, None

    certs_map.mkdir(exist_ok=True)
    cert_pad = certs_map / f"{ip}.pem"
    sleutel_pad = certs_map / f"{ip}-key.pem"

    print(f"Nieuw certificaat genereren voor {ip} met mkcert...")
    resultaat = subprocess.run(
        [mkcert_pad, "-cert-file", str(cert_pad), "-key-file", str(sleutel_pad),
         ip, "localhost", "127.0.0.1"],
        capture_output=True, text=True,
    )
    if resultaat.returncode != 0:
        print("mkcert-fout:", resultaat.stderr.strip())
        return None, None
    return cert_pad, sleutel_pad


def toon_qr_in_terminal(url: str):
    try:
        import qrcode
    except ImportError:
        print(f"(voor een scanbare QR-code hier: pip install qrcode)")
        print(f"Open handmatig op de telefoon: {url}")
        return
    print(f"\nScan met de telefoon om direct naar de app te gaan:\n")
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make()
    qr.print_ascii(invert=True)
    print(f"\nOf typ handmatig over: {url}\n")