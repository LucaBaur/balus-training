import { aktRolle } from "../core/konto.js";
import { wappen } from "../core/portraits.js";
import { gehe } from "../core/router.js";
import { $, datumTeile, escape, toast } from "../core/ui.js";

// ==================================================== Aufstellung / Feld =====
//  Wer steht wo? Zwei Ansichten auf demselben Halbfeld:
//    Training - ALLE Zusagen stehen auf ihrer Position (alle Halblinken bei
//               Halblinks). Zeigt sofort, wo es duenn wird.
//    Spiel    - eine Spielerin je Position plus Wechselbank.
//  Die Spiel-Aufstellung ist eine Tafel, kein Dokument: sie liegt lokal auf
//  dem Geraet (localStorage), nicht auf dem Server.

// WICHTIG - links und rechts sind hier gespiegelt, und das ist Absicht:
// Das Tor steht UNTEN, angegriffen wird nach unten. Die Positionsnamen kommen
// aus Sicht der ANGREIFERIN, die zum Tor schaut - ihre linke Seite liegt auf
// dem Bildschirm also RECHTS. Darum sitzt Halblinks bei x=76 und Halbrechts
// bei x=24. Wer die Werte "geradezieht", dreht die Aufstellung wieder falsch
// herum. (x/y = Spielansicht, gx/gy = Trainingsansicht.)
export const POSITIONEN = [
  { k: "TW", lang: "Tor",         x: 50,   y: 88.5, gx: 50, gy: 88 },
  { k: "LA", lang: "Linksaußen",  x: 89.5, y: 79.5, gx: 85, gy: 78 },
  { k: "HL", lang: "Halblinks",   x: 76,   y: 39.5, gx: 80, gy: 36 },
  { k: "RM", lang: "Mitte",       x: 50,   y: 36.5, gx: 50, gy: 29 },
  { k: "HR", lang: "Halbrechts",  x: 24,   y: 39.5, gx: 20, gy: 36 },
  { k: "RA", lang: "Rechtsaußen", x: 10.5, y: 79.5, gx: 15, gy: 78 },
  { k: "KM", lang: "Kreis",       x: 50,   y: 62.0, gx: 50, gy: 63 },
];
const POS_LANG = Object.fromEntries(POSITIONEN.map((p) => [p.k, p.lang]));
// Die Angriffsposition steht als Freitext in der Datenbank - so kam sie aus
// Anytype ("Außen", "Rückraum", "Halblinks/kreis"). Unscharfe Angaben werden
// bewusst auf MEHRERE Positionen abgebildet: "Außen" heisst links und rechts.
const POS_ALIAS = {
  "tor": ["TW"], "tw": ["TW"], "torhüterin": ["TW"], "torhueterin": ["TW"], "torfrau": ["TW"],
  "linksaußen": ["LA"], "linksaussen": ["LA"], "la": ["LA"], "links außen": ["LA"],
  "rechtsaußen": ["RA"], "rechtsaussen": ["RA"], "ra": ["RA"], "rechts außen": ["RA"],
  "außen": ["LA", "RA"], "aussen": ["LA", "RA"], "flügel": ["LA", "RA"],
  "halblinks": ["HL"], "hl": ["HL"], "rückraum links": ["HL"], "rueckraum links": ["HL"],
  "halbrechts": ["HR"], "hr": ["HR"], "rückraum rechts": ["HR"], "rueckraum rechts": ["HR"],
  "mitte": ["RM"], "rm": ["RM"], "rückraum mitte": ["RM"], "rueckraum mitte": ["RM"],
  "rückraum": ["HL", "RM", "HR"], "rueckraum": ["HL", "RM", "HR"],
  "kreis": ["KM"], "km": ["KM"], "kreisläufer": ["KM"], "kreisläuferin": ["KM"],
};
export function positionenVon(sp) {
  const treffer = new Set();
  (sp.position_angriff || "").toLowerCase().split(/[\/,;+&]|\bund\b/).forEach((t) => {
    const s = t.trim();
    if (POS_ALIAS[s]) POS_ALIAS[s].forEach((k) => treffer.add(k));
  });
  if (!treffer.size && sp.position === "Tor") treffer.add("TW");   // grobe Angabe rettet
  return [...treffer];
}
export const initialen = (name) =>
  (name || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
// Halbfeld: 6-m-Bogen, gestrichelte 9-m-Linie, 7-m-Marke. Nach dem echten
// Hallenmass gezeichnet (15 px = 1 m), damit die Abstaende stimmen.
function feldSVG() {
  return `<svg class="feld" viewBox="0 0 300 268" aria-label="Handballfeld, Angriffshälfte">
    <defs><clipPath id="feld-cut"><rect x="0" y="0" width="300" height="268"/></clipPath></defs>
    <rect width="300" height="268" fill="var(--court)"/>
    <g clip-path="url(#feld-cut)">
      <path d="M37.5 250 A90 90 0 0 1 127.5 160 L172.5 160 A90 90 0 0 1 262.5 250 Z" fill="var(--ocker)"/>
      <path d="M37.5 250 A90 90 0 0 1 127.5 160 L172.5 160 A90 90 0 0 1 262.5 250" fill="none" stroke="#fff" stroke-width="3"/>
      <path d="M-7.5 250 A135 135 0 0 1 127.5 115 L172.5 115 A135 135 0 0 1 307.5 250" fill="none" stroke="#fff" stroke-width="3" stroke-dasharray="13 11"/>
      <line x1="142" y1="145" x2="158" y2="145" stroke="#fff" stroke-width="3"/>
      <line x1="146" y1="190" x2="154" y2="190" stroke="#fff" stroke-width="3"/>
      <line x1="0" y1="250" x2="300" y2="250" stroke="#fff" stroke-width="3"/>
      <rect x="127.5" y="250" width="45" height="9" fill="none" stroke="#fff" stroke-width="3"/>
      <rect x="4" y="4" width="292" height="260" fill="none" stroke="#fff" stroke-width="3"/>
    </g>
  </svg>`;
}
let aufTraining = null;         // geladenes Training (mit Teilnahme)
let aufModus = "training";      // "training" | "spiel"
let aufStil = "portrait";       // Trainingsansicht: "portrait" | "name"
let aufFeld = {};               // Spiel-Modus: {POS: spielerId}
let aufBankWahl = null;
const aufSchluessel = () => "aufstellung-" + (aufTraining ? aufTraining.id : "0");
function aufFeldLaden() {
  try { aufFeld = JSON.parse(localStorage.getItem(aufSchluessel()) || "{}"); }
  catch (_) { aufFeld = {}; }
  if (!Object.keys(aufFeld).length) aufFeldVorschlagen();
}
function aufFeldSichern() {
  try { localStorage.setItem(aufSchluessel(), JSON.stringify(aufFeld)); } catch (_) {}
}
// Vorschlag: je Position die Zugesagte, die dort spielt (bei mehreren die erste).
function aufFeldVorschlagen() {
  aufFeld = {};
  const belegt = new Set();
  for (const pos of POSITIONEN) {
    const k = aufZugesagt().find((p) => !belegt.has(p.id) && positionenVon(p).includes(pos.k));
    if (k) { aufFeld[pos.k] = k.id; belegt.add(k.id); }
  }
}
const aufZugesagt = () =>
  ((aufTraining && aufTraining.teilnahme) || []).filter((t) => t.status === "anwesend");
export async function ladeAufstellung() {
  const el = $("#aufstellung-inhalt");
  el.innerHTML = '<p class="hinweis">Lädt…</p>';
  try { aufTraining = await Sync.apiOffline("/api/naechstes-training"); }
  catch (_) { aufTraining = null; }
  if (!aufTraining || !aufTraining.id) {
    el.innerHTML = '<p class="hinweis">Kein anstehendes Training – sobald ein Termin da ist, steht hier die Aufstellung.</p>';
    return;
  }
  aufFeldLaden();
  renderAufstellung();
}
function renderAufstellung() {
  const el = $("#aufstellung-inhalt");
  const d = aufTraining;
  const dt = datumTeile(d.datum);
  const training = aufModus === "training";
  el.innerHTML = "";

  el.appendChild(el3("p", "hinweis",
    `${dt.wt} ${dt.tag}${d.uhrzeit ? " · " + d.uhrzeit : ""} · ${aufZugesagt().length} zugesagt`));

  // Umschalter Training / Spiel (+ Darstellung in der Trainingsansicht)
  const leiste = document.createElement("div");
  leiste.className = "modus-leiste";
  leiste.appendChild(schalter([["training", "Training"], ["spiel", "Spiel"]], aufModus,
    (v) => { aufModus = v; aufBankWahl = null; renderAufstellung(); }));
  if (training) {
    leiste.appendChild(schalter([["portrait", "Portraits"], ["name", "Namen"]], aufStil,
      (v) => { aufStil = v; renderAufstellung(); }, "leise"));
  }
  el.appendChild(leiste);

  el.appendChild(el3("p", "hinweis", training
    ? "Alle Zusagen stehen auf ihrer Position – so siehst du sofort, wo es dünn wird."
    : (aktRolle === "trainer"
        ? "Eine Spielerin je Position. Für einen Tausch: erst jemanden von der Bank wählen, dann eine Position."
        : "Die geplante Aufstellung.")));

  const feld = document.createElement("div");
  feld.className = "feld-box";
  feld.innerHTML = feldSVG();
  if (training) feldTraining(feld); else feldSpiel(feld);
  el.appendChild(feld);

  if (training) {
    const leer = POSITIONEN.filter((p) => !aufAufPosition(p.k).length).map((p) => p.lang);
    const ohne = aufZugesagt().filter((p) => !positionenVon(p).length);
    const zeile = document.createElement("div");
    zeile.className = "feld-legende";
    zeile.innerHTML =
      (leer.length ? `<span>Unbesetzt: <b>${leer.join(", ")}</b></span>`
                   : `<span>Jede Position ist besetzt</span>`) +
      (ohne.length ? `<span><b>${ohne.length}</b> ohne hinterlegte Position</span>` : "");
    el.appendChild(zeile);
    if (ohne.length && aktRolle === "trainer") {
      const b = document.createElement("button");
      b.className = "plan-edit-btn";
      b.textContent = "Positionen im Kader nachtragen";
      b.addEventListener("click", () => gehe("team", "kader"));
      el.appendChild(b);
    }
  } else {
    const imFeld = new Set(Object.values(aufFeld));
    const bank = aufZugesagt().filter((p) => !imFeld.has(p.id));
    if (bank.length) {
      el.appendChild(el3("div", "eyebrow-feld", "Wechselbank"));
      const r = document.createElement("div");
      r.className = "reihe";
      bank.forEach((p) => {
        const b = document.createElement("button");
        b.className = "bank-p" + (aufBankWahl === p.id ? " gewaehlt" : "");
        b.innerHTML = wappen(p, 48) + `<span class="bn">${escape(p.name.split(" ")[0])}</span>`;
        b.addEventListener("click", () => {
          if (aktRolle !== "trainer") return;
          aufBankWahl = aufBankWahl === p.id ? null : p.id;
          renderAufstellung();
          if (aufBankWahl) toast("Jetzt eine Position im Feld antippen.");
        });
        r.appendChild(b);
      });
      el.appendChild(r);
    }
    if (aktRolle === "trainer") {
      const b = document.createElement("button");
      b.className = "plan-edit-btn";
      b.textContent = "Aufstellung neu vorschlagen";
      b.addEventListener("click", () => {
        aufFeldVorschlagen(); aufFeldSichern(); renderAufstellung();
        toast("Vorschlag nach hinterlegten Positionen.");
      });
      el.appendChild(b);
    }
  }
}
function el3(tag, klasse, text) {
  const e = document.createElement(tag);
  e.className = klasse; e.textContent = text;
  return e;
}
function schalter(paare, aktiv, fn, extra) {
  const g = document.createElement("div");
  g.className = "modus" + (extra ? " " + extra : "");
  paare.forEach(([wert, label]) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.setAttribute("aria-pressed", aktiv === wert ? "true" : "false");
    b.addEventListener("click", () => fn(wert));
    g.appendChild(b);
  });
  return g;
}
const aufAufPosition = (k) => aufZugesagt().filter((p) => positionenVon(p).includes(k));
// Trainingsansicht: eine Gruppe je Position
function feldTraining(box) {
  const namen = aufStil === "name";
  for (const pos of POSITIONEN) {
    const leute = aufAufPosition(pos.k);
    const g = document.createElement("div");
    g.className = "gruppe-platz" + (leute.length ? "" : " leer");
    g.style.left = pos.gx + "%"; g.style.top = pos.gy + "%";
    g.appendChild(el3("span", "kopfzeile", pos.k + (leute.length ? " · " + leute.length : "")));
    const stapel = document.createElement("div");
    stapel.className = "stapel" + (namen ? " namen" : "");
    if (!leute.length) {
      const x = el3("span", "namechip", "niemand");
      x.style.background = "rgba(10,25,48,.3)";
      stapel.appendChild(x);
    }
    leute.forEach((p) => {
      const b = document.createElement("button");
      if (namen) { b.className = "namechip" + (pos.k === "TW" ? " tw" : ""); b.textContent = p.name.split(" ")[0]; }
      else { b.className = "mini"; b.innerHTML = wappen(p, 28); }
      b.title = p.name;
      b.setAttribute("aria-label", p.name + ", " + pos.lang);
      b.addEventListener("click", () => spielerZettel(p, pos));
      stapel.appendChild(b);
    });
    g.appendChild(stapel);
    box.appendChild(g);
  }
}
// Spielansicht: eine Spielerin je Position
function feldSpiel(box) {
  for (const pos of POSITIONEN) {
    const id = aufFeld[pos.k];
    const p = id ? aufZugesagt().find((x) => x.id === id) : null;
    const b = document.createElement("button");
    b.className = "platz" + (p ? "" : " frei") + (aufBankWahl ? " ziel" : "");
    b.style.left = pos.x + "%"; b.style.top = pos.y + "%";
    b.innerHTML =
      (p ? wappen(p, 46) : `<span class="wappen leer" style="--w:46px"></span>`) +
      `<span class="name">${p ? escape(p.name.split(" ")[0]) : "frei"}</span>` +
      `<span class="rolle">${pos.k}</span>`;
    b.setAttribute("aria-label", pos.lang + ": " + (p ? p.name : "nicht besetzt"));
    b.addEventListener("click", () => {
      if (aktRolle === "trainer" && aufBankWahl) {
        aufFeld[pos.k] = aufBankWahl;
        const rein = aufZugesagt().find((x) => x.id === aufBankWahl);
        aufBankWahl = null;
        aufFeldSichern(); renderAufstellung();
        toast((rein ? rein.name : "Spielerin") + " steht jetzt auf " + pos.lang + ".");
        return;
      }
      if (p) spielerZettel(p, pos); else toast(pos.lang + " ist frei.");
    });
    box.appendChild(b);
  }
}
function spielerZettel(p, pos) {
  // Im Spiel-Modus setzt ein Tipp auf eine besetzte Position die Spielerin
  // auf die Bank - der direkte Weg, ohne Zwischendialog.
  if (aufModus === "spiel" && aktRolle === "trainer" && aufFeld[pos.k] === p.id) {
    delete aufFeld[pos.k];
    aufFeldSichern(); renderAufstellung();
    toast(p.name + " sitzt auf der Bank.");
    return;
  }
  const eigene = positionenVon(p).map((k) => POS_LANG[k]).join(", ") || "keine hinterlegt";
  toast(`${p.name} – ${pos.lang} (hinterlegt: ${eigene})`);
}
