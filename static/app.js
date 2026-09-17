const $ = (id) => document.getElementById(id);

// ========================= TABS =========================
$("nav-keuren").addEventListener("click", () => wisselTab("keuren"));
$("nav-rapportages").addEventListener("click", () => wisselTab("rapportages"));
$("nav-overzicht").addEventListener("click", () => wisselTab("overzicht"));
$("nav-import").addEventListener("click", () => wisselTab("import"));

function wisselTab(naam) {
  $("tab-keuren").classList.toggle("verborgen", naam !== "keuren");
  $("tab-rapportages").classList.toggle("verborgen", naam !== "rapportages");
  $("tab-overzicht").classList.toggle("verborgen", naam !== "overzicht");
  $("tab-import").classList.toggle("verborgen", naam !== "import");
  $("nav-keuren").classList.toggle("actief", naam === "keuren");
  $("nav-rapportages").classList.toggle("actief", naam === "rapportages");
  $("nav-overzicht").classList.toggle("actief", naam === "overzicht");
  $("nav-import").classList.toggle("actief", naam === "import");
  if (naam === "rapportages") zoekRapportages();
  if (naam === "overzicht") toonOverzichtTabel(ovHuidigeDataset);
}

// ========================= KEUREN: status =========================
let huidigApparaat = null;

function toon(id) {
  ["stap-identificatie", "stap-gevonden", "stap-onherkend", "stap-nieuw", "stap-keuring", "stap-resultaat"]
    .forEach((s) => $(s).classList.toggle("verborgen", s !== id));
}

// ---------- dropdown met bestaande apparaten ----------
async function vulDropdown() {
  try {
    const resp = await fetch("/api/apparaten");
    const apparaten = await resp.json();
    const select = $("select-apparaat");
    select.innerHTML = '<option value="">-- kies apparaat --</option>';
    apparaten
      .sort((a, b) => a.nummer.localeCompare(b.nummer, undefined, { numeric: true }))
      .forEach((a) => {
        const opt = document.createElement("option");
        opt.value = a.nummer;
        opt.textContent = `${a.nummer} - ${a.omschrijving || "(geen omschrijving)"}`;
        select.appendChild(opt);
      });
  } catch (err) {
    console.error("Kon apparatenlijst niet laden:", err);
  }
}
vulDropdown();

$("select-apparaat").addEventListener("change", (e) => {
  if (e.target.value) zoekApparaat(e.target.value);
});

// ---------- opschonen van gescande inhoud ----------
// Sommige QR/NFC-tags zijn gecodeerd als telefoonnummer (bv. "TEL:30011007")
// of een ander veelgebruikt URI-schema. Strip dat, hou alleen het nummer over.
function opschonenGescandeCode(tekst) {
  tekst = (tekst || "").trim();
  const schemaMatch = tekst.match(/^(tel|sms|smsto|mailto):(.+)$/i);
  if (schemaMatch) return schemaMatch[2].trim();
  return tekst;
}

// Patroon van onze eigen apparaatcodes. Pas dit hier aan als jullie codes
// een andere vorm hebben - dit is de enige plek waar dat hoeft te gebeuren.
// Huidige aanname: precies 8 cijfers (bv. 30011004).
const APPARAATCODE_PATROON = /^\d{8}$/;

function isGeldigeApparaatcode(tekst) {
  return APPARAATCODE_PATROON.test(tekst);
}

// Gedeelde afhandeling voor gescande (NFC/QR) inhoud: onderscheidt drie
// gevallen - onherkende code (geen match met ons patroon), geldige code van
// een onbekend apparaat (-> registreren), en geldige code van een bestaand
// apparaat (-> record bekijken). Handmatige invoer en de dropdown slaan deze
// check bewust over, want dat is altijd een bewuste, vertrouwde keuze.
function verwerkGescandeCode(ruweTekst, bron) {
  const opgeschoond = opschonenGescandeCode(ruweTekst);
  if (!isGeldigeApparaatcode(opgeschoond)) {
    toonOnherkend(ruweTekst, opgeschoond, bron);
    return;
  }
  zoekApparaat(opgeschoond);
}

function toonOnherkend(ruw, opgeschoond, bron) {
  $("onherkend-ruw").textContent = opgeschoond === ruw.trim() ? ruw : `${ruw}  (opgeschoond: ${opgeschoond})`;
  $("onherkend-bron").textContent = bron;
  toon("stap-onherkend");
}

$("btn-onherkend-terug").addEventListener("click", resetNaarStart);

// ---------- NFC ----------
const nfcBadge = $("nfc-status");
if ("NDEFReader" in window) {
  nfcBadge.textContent = "NFC beschikbaar";
  nfcBadge.classList.add("ok");
} else {
  nfcBadge.textContent = "NFC niet beschikbaar in deze browser - gebruik QR, de lijst, of handmatige invoer";
  nfcBadge.classList.add("fout");
  $("btn-scan").disabled = true;
}

$("btn-scan").addEventListener("click", async () => {
  try {
    const reader = new NDEFReader();
    await reader.scan();
    nfcBadge.textContent = "Houd de telefoon tegen de tag...";
    reader.onreading = (event) => {
      const decoder = new TextDecoder();
      for (const record of event.message.records) {
        if (record.recordType === "text") {
          const ruw = decoder.decode(record.data);
          nfcBadge.textContent = "Tag gelezen: " + ruw;
          verwerkGescandeCode(ruw, "NFC-tag");
          return;
        }
      }
    };
  } catch (err) {
    nfcBadge.textContent = "NFC-scan mislukt: " + err;
    nfcBadge.classList.add("fout");
  }
});

$("btn-zoek").addEventListener("click", () => zoekApparaat($("input-nummer").value.trim()));
$("input-nummer").addEventListener("keydown", (e) => {
  if (e.key === "Enter") zoekApparaat($("input-nummer").value.trim());
});

// ---------- QR-code (universeel alternatief, werkt in elke browser) ----------
let qrStream = null;

function qrStatus(tekst, soort) {
  const el = $("qr-status");
  el.textContent = tekst;
  el.className = "feedback " + (soort || "onbekend");
  el.classList.remove("verborgen");
}

$("btn-scan-qr").addEventListener("click", startQrScan);
$("btn-stop-qr").addEventListener("click", stopQrScan);

async function startQrScan() {
  if (typeof jsQR !== "function") {
    qrStatus("QR-bibliotheek kon niet geladen worden (static/vendor/jsQR.js ontbreekt?).", "fout");
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    qrStatus("Camera-toegang wordt niet ondersteund in deze browser/context (controleer of de pagina via https:// of localhost geladen is).", "fout");
    return;
  }

  qrStatus("Camera wordt gestart...", "onbekend");

  let voorkeurDeviceId = null;
  try {
    voorkeurDeviceId = await opStartenCamera({ facingMode: { ideal: "environment" } });
  } catch (err1) {
    try {
      voorkeurDeviceId = await opStartenCamera({});
    } catch (err2) {
      qrStatus("Camera-toegang mislukt: " + err2.name + " - " + err2.message, "fout");
      return;
    }
  }

  $("qr-scanner-wrap").classList.remove("verborgen");
  qrStatus("Richt de camera op de QR-code...", "onbekend");
  await vulCameraLijst(voorkeurDeviceId);
  requestAnimationFrame(qrTick);
}

async function opStartenCamera(videoConstraints) {
  const stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraints });
  if (qrStream) qrStream.getTracks().forEach((t) => t.stop());
  qrStream = stream;
  const video = $("qr-video");
  video.srcObject = qrStream;
  await video.play();
  const track = qrStream.getVideoTracks()[0];
  return track ? track.getSettings().deviceId : null;
}

async function vulCameraLijst(huidigeDeviceId) {
  const select = $("camera-select");
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const camerasList = devices.filter((d) => d.kind === "videoinput");
    select.innerHTML = "";
    camerasList.forEach((cam, i) => {
      const opt = document.createElement("option");
      opt.value = cam.deviceId;
      opt.textContent = cam.label || `Camera ${i + 1}`;
      if (cam.deviceId === huidigeDeviceId) opt.selected = true;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error("Kon cameralijst niet ophalen:", err);
  }
}

$("camera-select").addEventListener("change", async (e) => {
  qrStatus("Camera wisselen...", "onbekend");
  try {
    await opStartenCamera({ deviceId: { exact: e.target.value } });
    qrStatus("Richt de camera op de QR-code...", "onbekend");
  } catch (err) {
    qrStatus("Camera wisselen mislukt: " + err.message, "fout");
  }
});

function stopQrScan() {
  if (qrStream) {
    qrStream.getTracks().forEach((t) => t.stop());
    qrStream = null;
  }
  $("qr-scanner-wrap").classList.add("verborgen");
}

function qrTick() {
  if (!qrStream) return; // scan is gestopt of geannuleerd
  const video = $("qr-video");
  const canvas = $("qr-canvas");
  if (video.readyState === video.HAVE_ENOUGH_DATA) {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const code = jsQR(imageData.data, imageData.width, imageData.height);
    if (code && code.data) {
      qrStatus("Gevonden: " + code.data, "goed");
      stopQrScan();
      verwerkGescandeCode(code.data, "QR-code");
      return;
    }
  }
  requestAnimationFrame(qrTick);
}

// ---------- opzoeken ----------
async function zoekApparaat(nummer) {
  if (!nummer) return;
  const resp = await fetch(`/api/apparaat/${encodeURIComponent(nummer)}`);
  if (resp.status === 404) {
    $("nieuw-nummer-tonen").textContent = nummer;
    $("form-nieuw").dataset.nummer = nummer;
    toon("stap-nieuw");
    return;
  }
  const data = await resp.json();
  huidigApparaat = data.apparaat;
  $("apparaat-info").innerHTML = `
    <div><strong>${huidigApparaat.omschrijving}</strong> (${huidigApparaat.categorie})</div>
    <div>Fabrikant: ${huidigApparaat.fabrikant || "-"}</div>
    <div>Klasse: ${huidigApparaat.klasse} | Keurmerk: ${huidigApparaat.keurmerk || "-"}</div>
    <div>Laatst gekeurd: ${huidigApparaat.laatst_gekeurd || "nog niet"}</div>
    <div>Volgende keuring: ${huidigApparaat.volgende_keuring || "-"}</div>
  `;
  toonApparaatGeschiedenis(data.laatste_keuringen || []);
  toon("stap-gevonden");
}

function toonApparaatGeschiedenis(keuringen) {
  const container = $("apparaat-geschiedenis");
  if (keuringen.length === 0) {
    container.innerHTML = '<p class="uitleg">Nog geen eerdere keuringen voor dit apparaat.</p>';
    return;
  }
  container.innerHTML = "<p class=\"uitleg\">Eerdere keuringen:</p>" + keuringen.map((k, idx) => `
    <div class="import-rij ${k.eindoordeel === 'GOEDGEKEURD' ? 'klaar' : (k.eindoordeel === 'AFGEKEURD' ? 'onbekend' : 'grijs')}"
         data-idx="${idx}" style="cursor:pointer;">
      <div class="rij-kop">
        <span>${k.datum_tijd.replace("T", " ")}</span>
        <span class="badge ${k.eindoordeel === 'GOEDGEKEURD' ? 'ok' : (k.eindoordeel === 'AFGEKEURD' ? 'fout' : '')}">${k.eindoordeel}</span>
      </div>
    </div>
  `).join("");
  container.querySelectorAll(".import-rij").forEach((el) => {
    el.addEventListener("click", () => {
      wisselTab("rapportages");
      toonRapportageDetail(keuringen[parseInt(el.dataset.idx, 10)]);
    });
  });
}

$("btn-annuleer-gevonden").addEventListener("click", resetNaarStart);
$("btn-annuleer-nieuw").addEventListener("click", resetNaarStart);
$("btn-annuleer-keuring").addEventListener("click", resetNaarStart);
$("btn-nieuwe-keuring").addEventListener("click", resetNaarStart);

function resetNaarStart() {
  huidigApparaat = null;
  $("input-nummer").value = "";
  $("select-apparaat").value = "";
  $("form-keuring").reset();
  toon("stap-identificatie");
}

$("form-nieuw").addEventListener("submit", async (e) => {
  e.preventDefault();
  const nummer = e.target.dataset.nummer;
  const fd = new FormData(e.target);
  fd.append("nummer", nummer);
  const resp = await fetch("/api/apparaat", { method: "POST", body: fd });
  if (!resp.ok) { alert("Registreren mislukt: " + (await resp.text())); return; }
  huidigApparaat = await resp.json();
  vulDropdown();
  startKeuring();
});

$("btn-start-keuring").addEventListener("click", startKeuring);

function startKeuring() {
  $("keuring-nummer-tonen").textContent = `${huidigApparaat.nummer} - ${huidigApparaat.omschrijving}`;
  $("keuring-nummer-veld").value = huidigApparaat.nummer;
  $("fieldset-rpe").style.display = (huidigApparaat.klasse === "I" || huidigApparaat.klasse === "snoer") ? "" : "none";
  $("fieldset-lekstroom").style.display = (huidigApparaat.klasse === "snoer") ? "none" : "";
  toon("stap-keuring");
}

const RISO_MIN = { I: 1.0, II: 2.0, snoer: 1.0 };
const LEK_MAX = { I: 1.00, II: 0.50 };

function toonFeedback(elId, ok, tekst) {
  const el = $(elId);
  el.textContent = tekst;
  el.className = "feedback " + (ok === true ? "goed" : ok === false ? "fout" : "onbekend");
}

$("input-rpe").addEventListener("input", () => {
  const v = parseFloat($("input-rpe").value);
  if (isNaN(v)) return toonFeedback("rpe-feedback", null, "");
  if (v < 0.2) return toonFeedback("rpe-feedback", true, "< 0.2 Ω - goed");
  if (v > 1.0) return toonFeedback("rpe-feedback", false, "> 1.0 Ω - afgekeurd");
  toonFeedback("rpe-feedback", null, "tussen 0.2-1.0 Ω - grenswaarde hangt af van snoerlengte/diameter, definitief oordeel na opslaan");
});

$("input-riso").addEventListener("input", () => {
  const v = parseFloat($("input-riso").value);
  const klasse = huidigApparaat ? huidigApparaat.klasse : "I";
  const grens = RISO_MIN[klasse];
  if (isNaN(v)) return toonFeedback("riso-feedback", null, "");
  toonFeedback("riso-feedback", v > grens, `grens: > ${grens} MΩ (klasse ${klasse})`);
});

$("input-lekstroom").addEventListener("input", () => {
  const v = parseFloat($("input-lekstroom").value);
  const klasse = huidigApparaat ? huidigApparaat.klasse : "I";
  if (klasse === "snoer") return;
  const grens = LEK_MAX[klasse];
  if (isNaN(v)) return toonFeedback("lekstroom-feedback", null, "");
  toonFeedback("lekstroom-feedback", v < grens, `grens: < ${grens} mA (klasse ${klasse})`);
});

$("form-keuring").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  fd.set("visuele_inspectie_akkoord", $("visueel-akkoord").checked ? "true" : "false");
  const resp = await fetch("/api/keuring", { method: "POST", body: fd });
  if (!resp.ok) { alert("Opslaan mislukt: " + (await resp.text())); return; }
  const data = await resp.json();
  const titel = $("resultaat-titel");
  titel.textContent = data.eindoordeel;
  titel.style.color = data.eindoordeel === "GOEDGEKEURD" ? "#2e7d32"
    : data.eindoordeel === "AFGEKEURD" ? "#c62828" : "#777";
  $("resultaat-reden").textContent = data.reden;
  toon("stap-resultaat");
});

// ========================= IMPORT-TAB =========================
let laatsteAnalyse = null;

$("btn-analyseer").addEventListener("click", async () => {
  const bestand = $("import-bestand").files[0];
  if (!bestand) { alert("Kies eerst een bestand."); return; }
  const fd = new FormData();
  fd.append("bestand", bestand);
  const resp = await fetch("/api/import/analyseer", { method: "POST", body: fd });
  if (!resp.ok) { alert("Analyseren mislukt: " + (await resp.text())); return; }
  laatsteAnalyse = await resp.json();
  toonAnalyse(laatsteAnalyse);
});

function toonAnalyse(data) {
  $("import-resultaat").classList.remove("verborgen");
  vulGroep("groep-klaar", "groep-klaar-sectie", data.klaar, "klaar");
  vulGroep("groep-grijs", "groep-grijs-sectie", data.grijze_zone, "grijs");
  vulGroep("groep-onbekend", "groep-onbekend-sectie", data.onbekend, "onbekend");
}

function vulGroep(containerId, sectieId, rijen, soort) {
  const container = $(containerId);
  const sectie = $(sectieId);
  container.innerHTML = "";
  if (!rijen || rijen.length === 0) {
    sectie.classList.add("verborgen");
    return;
  }
  sectie.classList.remove("verborgen");
  rijen.forEach((rij, idx) => {
    const div = document.createElement("div");
    div.className = `import-rij ${soort}`;
    div.dataset.idx = idx;

    const metingTekst = [
      rij.aarde_ohm != null ? `Aarde: ${rij.aarde_ohm}Ω` : null,
      rij.isolatie_mohm != null ? `Riso: ${rij.isolatie_mohm}MΩ` : null,
      rij.lekstroom_ma != null ? `Lek(${rij.lekstroom_type}): ${rij.lekstroom_ma}mA` : null,
    ].filter(Boolean).join(" · ");

    let apparaatKoppelHtml = "";
    if (soort === "onbekend") {
      apparaatKoppelHtml = `
        <label>Koppel aan apparaatnummer (leeg = overslaan)
          <input type="text" class="veld-apparaat-nummer" placeholder="bv. 30011004">
        </label>`;
    }

    let grijsHtml = "";
    if (soort === "grijs") {
      grijsHtml = `
        <div class="mini-rij">
          <div><label>Snoerlengte (m) <input type="number" step="0.1" class="veld-lengte"></label></div>
          <div><label>Diameter (mm²) <input type="number" step="0.1" class="veld-diameter"></label></div>
        </div>`;
    }

    div.innerHTML = `
      <div class="rij-kop">
        <span>EazyPAT #${rij.eazypat_nummer} -> ${rij.apparaat_nummer || "geen match"}</span>
        <label class="checkbox"><input type="checkbox" class="veld-importeren" ${soort === "klaar" ? "checked" : ""}> importeren</label>
      </div>
      <div class="rij-details">
        ${rij.omschrijving || ""} - ${metingTekst} - datum: ${rij.laatste_testdatum || "?"}
        - apparaat zelf zei: ${rij.apparaat_oordeel || "?"}
      </div>
      ${apparaatKoppelHtml}
      ${grijsHtml}
      <label class="checkbox">
        <input type="checkbox" class="veld-visueel-akkoord">
        Visuele inspectie akkoord (EazyPAT registreert dit niet - jij moet dit bevestigen)
      </label>
    `;
    container.appendChild(div);
  });
}

$("btn-bevestig-import").addEventListener("click", async () => {
  if (!laatsteAnalyse) return;

  const teVerzenden = [];
  document.querySelectorAll(".import-rij").forEach((div) => {
    const magImporteren = div.querySelector(".veld-importeren").checked;
    if (!magImporteren) return;

    const soort = [...div.classList].find((c) => ["klaar", "grijs", "onbekend"].includes(c));
    const idx = parseInt(div.dataset.idx, 10);
    const bron = soort === "klaar" ? laatsteAnalyse.klaar
      : soort === "grijs" ? laatsteAnalyse.grijze_zone
      : laatsteAnalyse.onbekend;
    const basis = bron[idx];

    const visueelAkkoord = div.querySelector(".veld-visueel-akkoord").checked;

    let apparaatNummer = basis.apparaat_nummer;
    if (soort === "onbekend") {
      const veld = div.querySelector(".veld-apparaat-nummer");
      apparaatNummer = veld.value.trim() || null;
    }
    if (!apparaatNummer) return;

    let lengte = basis.kabellengte_m;
    let diameter = basis.kabeldiameter_mm2;
    if (soort === "grijs") {
      lengte = parseFloat(div.querySelector(".veld-lengte").value) || null;
      diameter = parseFloat(div.querySelector(".veld-diameter").value) || null;
    }

    teVerzenden.push({
      eazypat_nummer: basis.eazypat_nummer,
      apparaat_nummer: apparaatNummer,
      aarde_ohm: basis.aarde_ohm,
      isolatie_mohm: basis.isolatie_mohm,
      lekstroom_ma: basis.lekstroom_ma,
      lekstroom_type: basis.lekstroom_type,
      laatste_testdatum: basis.laatste_testdatum,
      kabellengte_m: lengte,
      kabeldiameter_mm2: diameter,
      visuele_inspectie_akkoord: visueelAkkoord,
      opmerkingen: `Geimporteerd uit EazyPAT (testobject ${basis.eazypat_nummer}, apparaat zei: ${basis.apparaat_oordeel})`,
    });
  });

  if (teVerzenden.length === 0) { alert("Niets geselecteerd om te importeren."); return; }

  const resp = await fetch("/api/import/bevestig", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(teVerzenden),
  });
  const data = await resp.json();
  $("import-samenvatting").innerHTML = `<strong>${data.aantal_ok} van ${teVerzenden.length} succesvol geimporteerd.</strong><br>` +
    data.resultaten.map((r) => `#${r.eazypat_nummer} -> ${r.apparaat_nummer || "-"}: ${r.status}${r.eindoordeel ? " (" + r.eindoordeel + ")" : ""}${r.reden ? " - " + r.reden : ""}`).join("<br>");
  vulDropdown();
});

// ========================= RAPPORTAGES-TAB =========================
$("btn-rap-zoek").addEventListener("click", zoekRapportages);

async function zoekRapportages() {
  const params = new URLSearchParams();
  const nummer = $("rap-filter-nummer").value.trim();
  const oordeel = $("rap-filter-oordeel").value;
  const vanaf = $("rap-filter-vanaf").value;
  const tot = $("rap-filter-tot").value;
  if (nummer) params.set("nummer", nummer);
  if (oordeel) params.set("eindoordeel", oordeel);
  if (vanaf) params.set("vanaf", vanaf);
  if (tot) params.set("tot", tot);

  const resp = await fetch("/api/keuringen?" + params.toString());
  const keuringen = await resp.json();
  toonRapportageLijst(keuringen);
}

function toonRapportageLijst(keuringen) {
  const container = $("rap-lijst");
  $("rap-detail").classList.add("verborgen");
  if (keuringen.length === 0) {
    container.innerHTML = '<p class="uitleg">Geen keuringen gevonden voor deze filters.</p>';
    return;
  }
  container.innerHTML = keuringen.map((k, idx) => `
    <div class="kaart rap-rij" data-idx="${idx}" style="cursor:pointer;">
      <div class="rij-kop">
        <span><strong>${k.nummer}</strong> - ${k.datum_tijd.replace("T", " ")}</span>
        <span class="badge ${k.eindoordeel === 'GOEDGEKEURD' ? 'ok' : (k.eindoordeel === 'AFGEKEURD' ? 'fout' : '')}">${k.eindoordeel}</span>
      </div>
      <div class="rij-details">Keurmeester: ${k.keurmeester || "-"} | bron: ${k.bron}</div>
    </div>
  `).join("");

  container.querySelectorAll(".rap-rij").forEach((el) => {
    el.addEventListener("click", () => toonRapportageDetail(keuringen[parseInt(el.dataset.idx, 10)]));
  });
}

function toonRapportageDetail(k) {
  const detail = $("rap-detail");
  detail.classList.remove("verborgen");

  const fotoHtml = (naam) => naam
    ? `<img src="/api/foto/${encodeURIComponent(k.nummer)}/${encodeURIComponent(naam)}" style="max-width:100%;border-radius:8px;margin:6px 0;">`
    : "";
  const mankementFotos = (k.foto_mankementen || "").split(";").filter(Boolean).map(fotoHtml).join("");

  detail.innerHTML = `
    <h2>${k.nummer} - ${k.datum_tijd.replace("T", " ")}</h2>
    <p><strong>Eindoordeel:</strong> ${k.eindoordeel} (${k.eindoordeel_reden})</p>
    <p><strong>Keurmeester:</strong> ${k.keurmeester || "-"} &middot; <strong>Bron:</strong> ${k.bron}</p>
    <p><strong>Visuele inspectie:</strong> ${k.visuele_inspectie_akkoord === "True" || k.visuele_inspectie_akkoord === true ? "Akkoord" : "Niet akkoord"} - ${k.visuele_inspectie_tekst || ""}</p>
    ${k.rpe_ohm ? `<p><strong>Rpe:</strong> ${k.rpe_ohm} \u03a9 - ${k.rpe_oordeel}</p>` : ""}
    ${k.riso_mohm ? `<p><strong>Riso:</strong> ${k.riso_mohm} M\u03a9 - ${k.riso_oordeel}</p>` : ""}
    ${k.lekstroom_ma ? `<p><strong>Lekstroom (${k.lekstroom_type}):</strong> ${k.lekstroom_ma} mA - ${k.lekstroom_oordeel}</p>` : ""}
    <p><strong>Opmerkingen:</strong> ${k.opmerkingen || "-"}</p>
    ${fotoHtml(k.foto_apparaat)}
    ${mankementFotos}
    <button id="btn-rap-terug" class="knop-tekst">Terug naar lijst</button>
  `;
  $("btn-rap-terug").addEventListener("click", () => detail.classList.add("verborgen"));
  detail.scrollIntoView({ behavior: "smooth" });
}

// ========================= OVERZICHT-TAB (sorteerbare tabel) =========================
let ovHuidigeDataset = "apparaten";
let ovRuweData = [];
let ovSorteerKolom = null;
let ovSorteerOmgekeerd = false;

$("ov-toon-apparaten").addEventListener("click", () => {
  ovHuidigeDataset = "apparaten";
  $("ov-toon-apparaten").className = "knop-primair";
  $("ov-toon-keuringen").className = "knop-secundair";
  toonOverzichtTabel("apparaten");
});
$("ov-toon-keuringen").addEventListener("click", () => {
  ovHuidigeDataset = "keuringen";
  $("ov-toon-keuringen").className = "knop-primair";
  $("ov-toon-apparaten").className = "knop-secundair";
  toonOverzichtTabel("keuringen");
});
$("ov-filter").addEventListener("input", () => renderOverzichtTabel());

async function toonOverzichtTabel(dataset) {
  ovHuidigeDataset = dataset;
  ovSorteerKolom = null;
  const url = dataset === "apparaten" ? "/api/apparaten" : "/api/keuringen";
  const resp = await fetch(url);
  ovRuweData = await resp.json();
  renderOverzichtTabel();
}

function renderOverzichtTabel() {
  const wrap = $("ov-tabel-wrap");
  if (ovRuweData.length === 0) {
    wrap.innerHTML = '<p class="uitleg">Geen gegevens.</p>';
    return;
  }
  const kolommen = Object.keys(ovRuweData[0]);

  const filterTekst = $("ov-filter").value.trim().toLowerCase();
  let rijen = ovRuweData;
  if (filterTekst) {
    rijen = rijen.filter((r) => kolommen.some((k) => String(r[k] ?? "").toLowerCase().includes(filterTekst)));
  }

  if (ovSorteerKolom) {
    rijen = [...rijen].sort((a, b) => {
      const av = a[ovSorteerKolom] ?? "";
      const bv = b[ovSorteerKolom] ?? "";
      const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true });
      return ovSorteerOmgekeerd ? -cmp : cmp;
    });
  }

  const kop = kolommen.map((k) => {
    const gesorteerd = k === ovSorteerKolom;
    return `<th data-kolom="${k}" class="${gesorteerd ? 'gesorteerd' : ''} ${gesorteerd && ovSorteerOmgekeerd ? 'omgekeerd' : ''}">${k}</th>`;
  }).join("");

  const body = rijen.map((r) => "<tr>" + kolommen.map((k) => {
    if (k === "nummer" && ovHuidigeDataset === "apparaten") {
      return `<td><a href="#" class="ov-nummer-link" data-nummer="${r[k]}">${r[k] ?? ""}</a></td>`;
    }
    return `<td>${r[k] ?? ""}</td>`;
  }).join("") + "</tr>").join("");

  wrap.innerHTML = `
    <p class="uitleg">${rijen.length} van ${ovRuweData.length} rijen${ovHuidigeDataset === "apparaten" ? " - klik een nummer voor de laatste keuring" : ""}</p>
    <table class="overzicht-tabel"><thead><tr>${kop}</tr></thead><tbody>${body}</tbody></table>
  `;

  wrap.querySelectorAll(".ov-nummer-link").forEach((a) => {
    a.addEventListener("click", async (e) => {
      e.preventDefault();
      const nummer = a.dataset.nummer;
      const resp = await fetch(`/api/apparaat/${encodeURIComponent(nummer)}`);
      if (!resp.ok) return;
      const data = await resp.json();
      if (!data.laatste_keuringen || data.laatste_keuringen.length === 0) {
        alert(`Apparaat ${nummer} heeft nog geen keuringen.`);
        return;
      }
      wisselTab("rapportages");
      toonRapportageDetail(data.laatste_keuringen[0]);
    });
  });

  wrap.querySelectorAll("th").forEach((th) => {
    th.addEventListener("click", () => {
      const kolom = th.dataset.kolom;
      if (ovSorteerKolom === kolom) {
        ovSorteerOmgekeerd = !ovSorteerOmgekeerd;
      } else {
        ovSorteerKolom = kolom;
        ovSorteerOmgekeerd = false;
      }
      renderOverzichtTabel();
    });
  });
}

// ========================= APPARATENBESTAND IMPORTEREN (xlsx/ods) =========================
let apparatenAnalyse = null;

$("btn-apparaten-analyseer").addEventListener("click", async () => {
  const bestand = $("apparaten-import-bestand").files[0];
  if (!bestand) { alert("Kies eerst een bestand."); return; }
  const fd = new FormData();
  fd.append("bestand", bestand);
  const resp = await fetch("/api/import/apparaten/analyseer", { method: "POST", body: fd });
  if (!resp.ok) { alert("Analyseren mislukt: " + (await resp.text())); return; }
  apparatenAnalyse = await resp.json();
  toonApparatenAnalyse(apparatenAnalyse);
});

function toonApparatenAnalyse(data) {
  $("apparaten-import-resultaat").classList.remove("verborgen");
  vulApparatenGroep("ap-groep-nieuw", "ap-groep-nieuw-sectie", data.nieuw, "nieuw");
  vulApparatenGroep("ap-groep-conflict", "ap-groep-conflict-sectie", data.conflict, "conflict");
  vulApparatenGroep("ap-groep-fout", "ap-groep-fout-sectie", data.fout, "fout");
}

function vulApparatenGroep(containerId, sectieId, items, soort) {
  const container = $(containerId);
  const sectie = $(sectieId);
  container.innerHTML = "";
  if (!items || items.length === 0) {
    sectie.classList.add("verborgen");
    return;
  }
  sectie.classList.remove("verborgen");
  items.forEach((item, idx) => {
    const g = item.genormaliseerd;
    const div = document.createElement("div");
    div.className = `import-rij ${soort === 'nieuw' ? 'klaar' : (soort === 'conflict' ? 'grijs' : 'onbekend')}`;
    div.dataset.idx = idx;

    let actieHtml = "";
    if (soort === "nieuw") {
      actieHtml = `<label class="checkbox"><input type="checkbox" class="veld-importeren" checked> toevoegen</label>`;
    } else if (soort === "conflict") {
      actieHtml = `
        <label>Actie
          <select class="veld-actie">
            <option value="overslaan">overslaan (behoud bestaand)</option>
            <option value="overschrijven">overschrijven met geimporteerde gegevens</option>
          </select>
        </label>`;
    } else {
      actieHtml = `<div class="rij-details">Fout(en): ${item.fouten.join("; ")}</div>`;
    }

    div.innerHTML = `
      <div class="rij-kop"><span>${g.nummer || "(geen nummer)"} - ${g.omschrijving || ""}</span></div>
      <div class="rij-details">Klasse: ${g.klasse || "?"} | Fabrikant: ${g.fabrikant || "-"}</div>
      ${actieHtml}
    `;
    container.appendChild(div);
  });
}

$("btn-apparaten-bevestig").addEventListener("click", async () => {
  if (!apparatenAnalyse) return;
  const teVerzenden = [];

  document.querySelectorAll("#ap-groep-nieuw .import-rij").forEach((div) => {
    const magImporteren = div.querySelector(".veld-importeren").checked;
    if (!magImporteren) return;
    const item = apparatenAnalyse.nieuw[parseInt(div.dataset.idx, 10)];
    teVerzenden.push({ genormaliseerd: item.genormaliseerd, actie: "toevoegen" });
  });

  document.querySelectorAll("#ap-groep-conflict .import-rij").forEach((div) => {
    const actie = div.querySelector(".veld-actie").value;
    const item = apparatenAnalyse.conflict[parseInt(div.dataset.idx, 10)];
    teVerzenden.push({ genormaliseerd: item.genormaliseerd, actie });
  });

  if (teVerzenden.length === 0) { alert("Niets geselecteerd om te importeren."); return; }

  const resp = await fetch("/api/import/apparaten/bevestig", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(teVerzenden),
  });
  const data = await resp.json();
  $("apparaten-import-samenvatting").innerHTML = `<strong>${data.aantal_ok} van ${teVerzenden.length} verwerkt.</strong><br>` +
    data.resultaten.map((r) => `${r.nummer}: ${r.status}`).join("<br>");
  vulDropdown();
});