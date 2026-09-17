# Context — ontwikkelproces apparatenkeur

Dit bestand is geen handleiding (zie `README.md`) maar een logboek van *waarom*
het systeem eruitziet zoals het eruitziet: architectuurkeuzes, dingen die zijn
uitgezocht/getest, en bugs met hun grondoorzaak. Bedoeld om te voorkomen dat
een volgende sessie (mens of AI) dezelfde paden opnieuw moet uitzoeken.

## Architectuurkeuzes

**Flask, niet FastAPI/uvicorn.** Oorspronkelijk gebouwd op FastAPI. Overgestapt
naar Flask omdat dat in andere projecten al gebruikt wordt, en omdat een kaal
`uvicorn
app:app`-commando gevoelig bleek voor PATH-verwarring tussen meerdere Python-
omgevingen op zijn Mac (PlatformIO's eigen venv claimde het `uvicorn`-commando).
`python app.py` gebruikt altijd de actief geactiveerde Python, wat dat probleem
structureel voorkomt.

**CSV-bestanden, geen database.** Bewuste keuze: leesbaar, makkelijk te back-
uppen, makkelijk te openen in Excel voor een snelle blik, en sluit aan bij de
al bestaande werkwijze (Zoho WorkDrive-spreadsheets). Nadeel (geaccepteerd): geen
gelijktijdige-schrijfbeveiliging — voor een handjevol gebruikers geen
praktisch probleem.

**jsQR lokaal gevendord, niet via CDN.** Eerste versie verwees naar
`cdnjs.cloudflare.com/.../jsQR.min.js` — bleek niet te bestaan (jsQR staat
niet op cdnjs). Even overgestapt naar jsDelivr (`cdn.jsdelivr.net/npm/jsqr@1.4.0/...`),
maar uiteindelijk het bestand zelf in `static/vendor/jsQR.js` gezet: geen
externe afhankelijkheid meer, werkt ook zonder internetverbinding (relevant
voor een werkplaats-app). Zie "Bugs en grondoorzaken" hieronder voor het
volledige verhaal.

**Matchen op nummer, nooit op volgorde (EazyPAT-import).** De EazyPAT 3140USB
heeft geen instelbaar testobjectnummer — alleen een automatisch
geheugenlocatienummer (1-999), bevestigd doordat het apparaat fysiek geen
toetsenbord/cijferinvoer heeft (zie handleiding-doorzoeking hieronder). Een
gemiste of dubbele meting zou een positie-gebaseerde koppeling stilzwijgend
laten verschuiven. Daarom: exacte match op nummer, en bij geen match altijd
een expliciete handmatige koppelstap — nooit een aanname op basis van volgorde
of aantal.

**Automatische HTTPS via mkcert, met bestandsgebaseerde config.** Eerst een
handmatige `ssl_context=(...)`-regel in `app.py` — ging twee keer stuk
doordat een volledige herbouw van `app.py` die regel overschreef. Opgelost door de HTTPS-config te laten afhangen van
bestanden in `certs/` (gedetecteerd via meerdere naampatronen, zie
`netwerk_setup.py`) in plaats van een regel code — overleeft toekomstige
herbouwstukken van `app.py` per definitie.

## Uitgezocht / gereverse-engineerd

**EazyPAT 3140 USB-protocol.** Statische analyse van de officiële "EazyPAT
3140 Link"-installer (een NSIS-installer, uitgepakt met `7z`) leverde op:
- USB-chip: Silicon Labs CP210x (staat letterlijk in de Nederlandse hulptekst
  in de installer) — heeft ingebouwde Linux-kernelsupport, geen driver nodig.
- Seriële instellingen: 9600 baud, 8 databits, geen pariteit, 1 stopbit,
  bevestigd via disassembly (`objdump`) van een `push 0x2580` (=9600)
  instructiereeks gevolgd door vergelijkbare setter-aanroepen.
- Protocol: puur eenrichtingsverkeer. De software stuurt niets; de gebruiker
  houdt "Oproepen" 5 seconden ingedrukt op de tester zelf, die dan de
  opgeslagen metingen als platte, puntkomma-gescheiden tekst stuurt (bevestigd
  met een echte export: 43 kolommen, decimale komma's, `<`/`>` als
  grenswaarde-aanduiding).
- Geheugen: 999 metingen, bevestigd via de handleiding en twee onafhankelijke
  retailer-productpagina's.
- Geen instelbaar testobjectnummer: bevestigd doordat de volledige
  (nieuwere, completere) handleiding een knoppenlijst toont zonder enige
  vorm van cijfer-/tekstinvoer op het apparaat zelf.

**NEN3140-rekenlogica, twee correctierondes.** Eerste versie gebruikte een Rpe-
drempel van 0.3Ω met een onvolledige lengte/diameter-tabel — bleek bij het
doorlezen van een completere versie van de handleiding fout: de echte
drempel is 0.2Ω, met een fijnmaziger tabel (extra kolommen voor 1.5mm² en
25mm², eerste lengte-bucket "<2m" i.p.v. "<5m"). Herstel gevalideerd door de
volledige logica terug te rekenen tegen een echte EazyPAT-export
(27 deeloordelen, allemaal exact overeenkomend met wat de tester zelf al had
opgeslagen). Belangrijke nuance die daarbij aan het licht kwam: voor
Aarde-waarden tussen 0.2-1.0Ω kan geen enkele software zelfstandig goed/fout
bepalen zonder snoerlengte + diameter — dat weet alleen de tester op het
moment zelf, via een tabel die de gebruiker op het display bevestigt. De app
vraagt daarom expliciet om die twee waarden in plaats van te doen alsof een
import dat automatisch kan afleiden.

Ontdekt via diezelfde echte export: er bestaan **drie** soorten
lekstroommeting (Lekstroom/reëel, Aanraaklekstroom, Vervangende Lekstroom),
niet twee zoals aanvankelijk aangenomen.

**Web NFC-ondersteuning (browserlandschap).** Uitgezocht welke browsers Web
NFC ondersteunen: Chrome, Edge, Opera en Samsung Internet voor Android — al­tijd
Chromium-gebaseerd, nooit Firefox, nooit een desktopbrowser (ook niet
desktop-Chrome). Vereist bovendien een secure context (`https://` of
letterlijk `localhost`) — een gewoon lokaal IP-adres via `http://` telt niet
mee, ongeacht de browser. Op Murena/e-OS (Fairphone 5, gebaseerd op het nu
gestopte Bromite-project) bleek Opera de NFC-permissie-aanvraag niet netjes
te implementeren (geen instelling ervoor te vinden, altijd "geweigerd") —
niet verder uitgezocht of dit ook voor Edge geldt. Alternatief onderzocht
maar niet gebouwd: `termux-nfc` (Termux:API) leest NFC native via Android's
eigen framework, buiten elke browser om — bevestigd dat dit bestaat en
werkt, maar de exacte commandoregel-syntax is nooit geverifieerd tegen een
echt toestel.

**mkcert + Firefox.** Firefox op desktop houdt een eigen, van het
besturingssysteem onafhankelijke certificaatopslag bij — `mkcert -install`
voegt de CA alleen toe aan de macOS-systeem-sleutelhanger, waar Chrome/Edge/
Opera/Safari wél naar kijken. Firefox toont daardoor `SEC_ERROR_UNKNOWN_ISSUER`
tenzij die CA daar apart geïmporteerd wordt (Instellingen > Privacy en beveiliging
> Certificaten) of steeds handmatig doorklikt.

**Flask sorteert JSON-sleutels standaard alfabetisch** (`app.json.sort_keys`),
wat de kolomvolgorde in `/api/apparaten` en `/api/keuringen` door elkaar
gooide t.o.v. de bedoelde volgorde (nummer eerst). Uitgezet met
`app.json.sort_keys = False`. Beïnvloedt niet de xlsx/ods-export, die heeft
zijn eigen vaste kolomvolgorde via `APPARAAT_VELDEN`/`KEURING_VELDEN`.

## Bugs en grondoorzaken (voor het geval iets vergelijkbaars terugkomt)

- **Camera-toegang faalde stil op de MacBook.** `getUserMedia({video:
  {facingMode: "environment"}})` kan stil falen op een toestel zonder
  achtercamera. Opgelost met een expliciete val-terug naar `{video: true}` en
  een zichtbare statusregel op de pagina zelf (niet alleen een `alert()`, die
  makkelijk gemist wordt).
- **QR-knop deed niets, geen foutmelding zichtbaar.** Bleek de gevendorde
  library te zijn die nog naar een niet-bestaande CDN-URL verwees.
  Les: nooit een externe library-URL aannemen zonder hem te verifiëren
  (`web_fetch`/`web_search`) — in dit geval leidde dat tot twee ronde reparaties
  voor het klopte.
- **Emoji's/tekens toonden als letterlijke `\uXXXX`-tekst.** JavaScript-stijl
  unicode-escapes gebruikt in kale HTML-tekstinhoud — HTML kent die
  schrijfwijze niet (dat is alleen geldig binnen JS-stringliteralen). Sindsdien:
  gewoon de echte UTF-8-tekens direct in HTML-bestanden zetten, geen escapes.
- **Invoerveld naast een knop was veel te smal.** Knoppen hadden standaard
  `width:100%`; binnen een flex-rij verdrukte dat het naastgelegen invoerveld.
  Fix: knoppen in een `.rij`-container expliciet `flex:0 0 auto` geven.
- **HTTPS viel stil terug op http na een update van `app.py`.** Twee keer
  gebeurd: eerst doordat een volledige herbouw van `app.py` de handmatige
  `ssl_context`-regel niet meenam, daarna doordat het certificaat in de
  hoofdmap stond terwijl de code alleen in `certs/` zocht. Structureel
  opgelost door certificaatdetectie los te trekken van `app.py`'s code (zie
  `netwerk_setup.py`) en op meerdere plekken/naamconventies te laten zoeken.
- **Flask's debug-herlader dreigde de opstart-QR-code dubbel te tonen.**
  Opgelost met een `WERKZEUG_RUN_MAIN`-check: certificaat genereren en QR
  tonen gebeurt alleen in het eerste (bewakende) proces.
- **odfpy: vetgedrukte tekst werkte niet via een stijl op het paragraaf-
  niveau.** Moet via een `text:span` binnen de paragraaf, niet via
  `P(stylename=...)` direct. Bevestigd door de output te renderen met
  LibreOffice en visueel te vergelijken.

## Getest en bevestigd (zodat het niet opnieuw hoeft)

- NEN3140-rekenlogica teruggerekend tegen een echte EazyPAT-export (27/27
  deeloordelen kwamen overeen).
- jsQR-decodelogica getest met een zelf gegenereerde QR-code (round-trip
  gaf exact dezelfde tekst terug).
- Alle vier certificaat-detectiescenario's van `netwerk_setup.py` getest:
  schone start (genereert), herstart (hergebruikt), bestanden in de hoofdmap
  met oorspronkelijke mkcert-namen, en zonder `mkcert` geïnstalleerd (nette
  terugval + instructie).
- Apparaten-bulkimport getest met een bestand dat alle vier situaties
  bevatte: nieuw, conflict, ontbrekend nummer, ongeldige klasse, niet-
  numerieke waarde — elke situatie kwam in de juiste categorie terecht,
  zowel voor .xlsx als .ods.
- EazyPAT-CSV-importlogica getest met echte voorbeelddata,
  inclusief het klaar/grijze-zone/onbekend-onderscheid.
- Overzicht-tabel se sorteer-/filterlogica getest (inclusief een test-
  artefact-valkuil: gedeelde array-referenties tussen gestubte fetch-calls
  gaven schijnbaar verkeerde sortering — bleek een JavaScript
  in-place-`.sort()`-bijwerking in `vulDropdown()`, onschadelijk in het echt
  omdat elke `fetch()` daar zijn eigen, verse array teruggeeft).

## Open vragen / niet (verder) uitgezocht

- **Apparaatcode-patroon (8 cijfers)** is een aanname op basis van tot nu toe
  geziene nummers (bv. `30011004`), niet expliciet bevestigd als
  hét vaste formaat. Staat in `APPARAATCODE_PATROON` in `app.js` — een plek
  om aan te passen mocht het toch anders blijken te zijn.
- **`termux-nfc`-syntax** nooit geverifieerd tegen een echt toestel — alleen
  bevestigd dat de functionaliteit bestaat.
- **Edge voor Android + NFC-permissie op Murena/e-OS** nooit getest (alleen
  Opera bleek problematisch); onbekend of dit een Opera-specifiek probleem is
  of dieper in het besturingssysteem zit.
- **EazyPAT 3140 Link-software (origineel, van cd)** is uitgepakt en
  geanalyseerd, maar nooit werkend gedraaid — de reverse-engineering ging
  volledig via statische analyse van de installer, niet via het observeren
  van echt netwerkverkeer/seriële data vanuit de software zelf.