# Apparatenkeur — standalone Python-applicatie

Lokale, stand-alone Flask-app voor het registreren en keuren van apparatuur
volgens NEN3140: NFC/QR-identificatie, foto's, automatische goed/afkeur-
berekening, EazyPAT-import, bulk-apparateninport, rapportages en een
doorzoekbare tabelweergave. Data staat in platte CSV-bestanden — geen
database nodig, alles zelf te back-uppen of te bekijken.

## Installeren en starten

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Bij het starten:
1. Het LAN-IP-adres van deze machine wordt automatisch bepaald.
2. Is er al een HTTPS-certificaat voor dat IP (in `certs/`), dan wordt dat
   hergebruikt. Zo niet, en is `mkcert` geïnstalleerd, dan wordt er automatisch
   een nieuw certificaat gegenereerd. Zonder `mkcert` draait de server via
   gewone `http://`, met een duidelijke melding waarom.
3. Er verschijnt een **scanbare QR-code direct in de terminal** die naar de
   juiste `https://<ip>:8000` (of `http://`) wijst — scan die met de telefoon
   om er meteen te zijn.

Eenmalig, voor HTTPS (nodig voor NFC en camera-toegang op de telefoon):
```bash
brew install mkcert && mkcert -install
```
Zie `netwerk_setup.py` voor de details; dit overleeft toekomstige aanpassingen
aan `app.py`, want het hangt af van bestanden in `certs/`, niet van code die
overschreven kan worden.

## De vier tabbladen

### Keuren
Een apparaat identificeren kan op vier manieren:
- **NFC-scan** — Web NFC, werkt alleen in Chrome/Edge/Opera/Samsung Internet
  op Android, nooit op desktop. Vereist `https://` of `localhost`.
- **QR-scan** — werkt in elke browser met camera (ook Firefox, ook desktop).
  De QR-bibliotheek (`static/vendor/jsQR.js`) zit lokaal in het project, geen
  internetverbinding nodig. Bij het starten wordt een camera gekozen
  (achtercamera bij voorkeur, met terugval en handmatige keuze via de
  dropdown die verschijnt — handig op een laptop met maar één camera).
- **Dropdown** — direct gevuld vanuit de bestaande apparatenlijst.
- **Handmatig nummer intypen.**

Gescande inhoud (NFC/QR) wordt eerst opgeschoond (een `TEL:`/`SMS:`/`MAILTO:`-
voorvoegsel wordt gestript, zoals bij QR-tags die als telefoonnummer zijn
gecodeerd) en dan gecontroleerd tegen het verwachte apparaatcode-patroon
(`APPARAATCODE_PATROON` in `app.js`, nu: exact 8 cijfers). Drie uitkomsten:
- geen match → "Onherkende code"-scherm, gaat niet door naar registratie;
- match, onbekend apparaat → nieuw apparaat registreren;
- match, bekend apparaat → gegevens + eerdere keuringen, keuring starten.

Handmatige invoer en de dropdown slaan deze check bewust over — dat is altijd
een bewuste keuze.

Bij de keuring: foto van het apparaat en eventuele mankementen, visuele
inspectie (met verplicht expliciet akkoord-vinkje), en de EazyPAT-meetwaarden
met live feedback. Rekenlogica in `nen3140.py`: Rpe < 0.2Ω altijd goed,
> 1.0Ω altijd afgekeurd, daartussen de volledige lengte/diameter-tabel uit de
handleiding; Riso > 1.0MΩ (klasse I/snoer) of > 2.0MΩ (klasse II); lekstroom
< 1.00mA (klasse I) of < 0.50mA (klasse II), met een aparte grens voor een
keramisch verwarmingselement. Er zijn drie lekstroom-varianten (reëel,
aanraak, vervangend) — de EazyPAT-export gebruikt ze alle drie, afhankelijk
van klasse en meetmethode.

### Rapportages
Zoek/filter keuringen op apparaatnummer, eindoordeel en datumbereik. Klik een
rij open voor het volledige rapport, inclusief foto's.

### Overzicht
Dezelfde twee tabellen als de Excel/ODS-export (Apparaten / Keuringen),
maar doorzoekbaar en sorteerbaar in de app zelf. Klik een kolomkop om te
sorteren, typ in het filterveld om over alle kolommen tegelijk te zoeken.
In de Apparaten-weergave is elk nummer een link naar de meest recente
keuring van dat apparaat.

### Importeren
Twee onafhankelijke import-flows, allebei volgens hetzelfde patroon: eerst
analyseren (nooit direct wegschrijven), dan expliciet bevestigen.

- **Apparatenbestand (Excel/ODS)** — voor bulk-registratie. Herkent bij
  voorkeur een blad genaamd "apparaten-export" (zoals de eigen export het
  noemt, dus round-tripping werkt), anders het eerste blad. Verplicht:
  `nummer` en `klasse` (I/II/snoer); de rest optioneel. Elke rij valt in een
  van drie groepen: **nieuw** (klaar om toe te voegen), **conflict**
  (nummer bestaat al — jij kiest overschrijven of overslaan, nooit
  stilzwijgend), of **fout** (ontbrekend nummer, ongeldige klasse, een
  niet-numerieke waarde in een getalveld, of een dubbel nummer binnen het
  bestand zelf — wordt nooit geïmporteerd).
- **EazyPAT-export** — voor het CSV-bestand dat `eazypat_lezen.py`
  wegschrijft (zie hieronder). De EazyPAT kent geen instelbaar
  testobjectnummer, alleen een automatisch geheugenlocatienummer (1-999),
  dus koppeling gebeurt **nooit automatisch op volgorde** — alleen op een
  exacte match van het testobjectnummer met een bestaand apparaatnummer.
  Groepen: **klaar** (exacte match, genoeg info voor een oordeel), **grijze
  zone** (Aarde-waarde tussen 0.2-1.0Ω, snoerlengte/diameter nog nodig), of
  **onbekend** (geen match — handmatig koppelen of overslaan). Visuele
  inspectie wordt hier nooit aangenomen (staat niet in de EazyPAT-export) —
  altijd een expliciete bevestiging per rij.

## EazyPAT 3140 USB uitlezen (los van de webapp)

`eazypat_lezen.py` (in de projectroot, niet onder `static/`) leest de tester
rechtstreeks via de seriële poort uit — 9600 baud, 8N1, Silicon Labs CP210x
(ingebouwde Linux-kernelsupport). Geen commando's nodig: de EazyPAT stuurt
zelf de opgeslagen metingen zodra je 5 seconden "Oproepen" ingedrukt houdt.
Zie de code-comments daar voor het exacte gebruik.

## Data en bestanden

```
data/apparaten.csv       — stamgegevens per apparaat
data/keuringen.csv       — logboek, 1 rij per keuring (kolom 'bron': "app" of "eazypat_import")
data/fotos/<nummer>/     — foto's per apparaat
certs/                   — HTTPS-certificaten (per IP-adres), automatisch beheerd
static/vendor/jsQR.js    — lokaal gehoste QR-bibliotheek (Apache-2.0, zie jsQR.LICENSE.txt)
```

"Exporteer naar Excel" / "Exporteer naar ODS" (onderaan Keuren) maken een
bestand met twee tabbladen (apparaten-export, keuringen-log) — hetzelfde
bestand dat de apparaten-import bij voorkeur weer inleest.

## Bestandsoverzicht

| Bestand | Functie |
|---|---|
| `app.py` | Flask-app: alle routes/endpoints |
| `nen3140.py` | Beoordelingslogica (Rpe/Riso/lekstroom-grenzen) |
| `eazypat_import.py` | Parser voor de ruwe EazyPAT-CSV |
| `import_apparaten.py` | Parser + validatie voor apparaten-bulkimport (xlsx/ods) |
| `netwerk_setup.py` | IP-detectie, automatisch mkcert-certificaatbeheer, QR-code in terminal |
| `eazypat_lezen.py` | Los script: EazyPAT via seriële poort uitlezen |
| `static/index.html` / `app.js` / `style.css` | Frontend, vier tabbladen |
| `static/vendor/jsQR.js` | Lokaal gehoste QR-scanbibliotheek |

## Bekende beperkingen

- Geen authenticatie — prima voor een lokale pilot.
- CSV-opslag zonder gelijktijdige-schrijfbeveiliging — voor een handjevol
  gebruikers in de praktijk geen probleem.
- Zoho-koppeling blijft bewust handmatig (export/import).
- Apparaatcode-patroon (nu: 8 cijfers) staat in `APPARAATCODE_PATROON` in
  `app.js` — pas die regel aan als jullie nummering anders is.

Zie `context.md` voor de achterliggende keuzes, uitgezochte technische
details en testresultaten uit het ontwikkelproces.