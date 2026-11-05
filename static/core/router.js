import { videosAlsGesehenMerken } from "../features/home.js";
import { aktRolle, eigeneSpielerId } from "./konto.js";
import { _segment, nutzungMelden, segmentStarten } from "./tracking.js";
import { $, escape } from "./ui.js";

export const initFuer = (ober, unter) => routenTabelle[ober + "/" + unter];
export let aktOber = "home";
export let aktUnter = "home";     // aktiver Unterpunkt (für „zurück" aus Detailansichten)
function sichtbareOber() { return NavKonfig.oberFuer(aktRolle, !!eigeneSpielerId()); }
function sichtbareUnter(o) { return o.unter; }
// ---------------------------------------------------------------- Verlauf ---
//  Ohne Verlaufseintraege schliesst die Android-Zurueck-Taste in der TWA die
//  App, statt eine Ebene zurueckzugehen. Jede Navigation legt einen Eintrag an;
//  eine Detailansicht merkt sich, aus welcher Liste sie geoeffnet wurde.
export let _ausVerlauf = false;   // true, solange popstate den Zustand wiederherstellt
export function setzeAusVerlauf(wert) { _ausVerlauf = wert; return wert; }
let _inGehe = false;       // true, solange gehe() die View umschaltet
function verlaufMerken(zustand) {
  if (_ausVerlauf) return;
  try { history.pushState(zustand, ""); } catch (_) {}
}
// View des aktuellen Unterpunkts – dorthin fuehren die "zurueck"-Knoepfe.
function navView() {
  const ziel = NavKonfig.finde(aktRolle, !!eigeneSpielerId(), aktOber, aktUnter);
  return ziel && ziel.unter.view;
}
window.addEventListener("popstate", (e) => {
  const z = e.state;
  _ausVerlauf = true;
  try { mitScrollRueckkehr(() => gehe(z && z.ober, z && z.unter)); } finally { _ausVerlauf = false; }
});
// ---- Scroll-Position beim Zurueckgehen ---------------------------------------
//  Wer aus einer Liste (z. B. Videos) in eine Detailansicht geht und zurueckkehrt,
//  soll wieder an der alten Stelle landen. zeigeView() merkt sich beim Verlassen
//  die Scrollhoehe je View; nur bei einer Rueckkehr (Zurueck-Knopf, Android-Zurueck,
//  iOS-Wischgeste) wird sie wieder eingestellt, ein Klick im Menue startet oben.
let _rueckkehr = false;          // true, solange eine Rueckkehr laeuft
let _scrollNachRender = null;    // Ziel, falls die Liste erst nach dem Laden wieder voll hoch ist
const scrollMerk = {};           // view-id -> letzte Scrollhoehe
export function mitScrollRueckkehr(fn) {
  _rueckkehr = true;
  try { fn(); } finally { _rueckkehr = false; }
}
// Nach asynchronem Neuzeichnen einer Liste erneut einstellen (vorher war sie evtl. zu kurz).
export function scrollNachRenderAnwenden() {
  if (_scrollNachRender == null) return;
  window.scrollTo(0, _scrollNachRender);
  _scrollNachRender = null;
}
export function zeigeView(id) {
  const sichtbar = document.querySelector(".view:not(.hidden)");
  if (sichtbar) scrollMerk[sichtbar.id] = window.scrollY;
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  const el = $("#" + id);
  if (el) el.classList.remove("hidden");
  // Video verlassen (Zurueck-Knopf, nicht ueber gehe): die Zeit zaehlt wieder dem Bereich
  if (id !== "view-video-detail" && _segment && /^[a-z]+:\d+$/.test(_segment.ziel)) {
    segmentStarten(aktOber + "/" + aktUnter);
  }
  const ziel = _rueckkehr ? (scrollMerk[id] || 0) : 0;
  _scrollNachRender = ziel || null;
  window.scrollTo(0, ziel);
  // Detail geoeffnet (nicht ueber die Navigation, nicht zurueck zur Liste)
  // -> Verlaufseintrag, damit Zurueck wieder auf der Liste landet.
  if (!_ausVerlauf && !_inGehe && id !== navView()) {
    verlaufMerken({ typ: "detail", ober: aktOber, unter: aktUnter });
  }
}
// Zu einem Reiter wechseln; optional direkt zu einem bestimmten Unterpunkt.
export function gehe(oberKey, unterKey) {
  const profil = !!eigeneSpielerId();
  const ziel = NavKonfig.finde(aktRolle, profil, oberKey, unterKey)
            || NavKonfig.finde(aktRolle, profil, "home", "home");
  const { ober, unter } = ziel;
  aktOber = ober.key;
  aktUnter = unter.key;
  document.querySelectorAll("#tableiste button").forEach((b) =>
    b.classList.toggle("aktiv", b.dataset.ober === aktOber));
  const pk = document.getElementById("profil-knopf");
  if (pk) pk.classList.toggle("aktiv", aktOber === "ich" || aktOber === "konto");
  renderSubnav(ober, aktUnter);
  _inGehe = true;
  try { zeigeView(unter.view); } finally { _inGehe = false; }
  const init = initFuer(ober.key, unter.key);
  try { init && init(); } catch (_) {}
  verlaufMerken({ typ: "nav", ober: aktOber, unter: aktUnter });
  nutzungMelden("bereich", aktOber + "/" + aktUnter);
  if (aktOber === "videos" && aktRolle === "spieler") videosAlsGesehenMerken();
}
// Unter-Navigation zeichnen; bei nur einem sichtbaren Unterpunkt ausblenden (kein Nutzen).
function renderSubnav(ober, aktUnterKey) {
  const nav = $("#subnav");
  const unterListe = NavKonfig.subnav(ober);
  if (unterListe.length <= 1) { nav.innerHTML = ""; nav.classList.add("leer"); return; }
  nav.classList.remove("leer");
  nav.innerHTML = "";
  for (const u of unterListe) {
    const b = document.createElement("button");
    b.textContent = u.label;
    b.className = u.key === aktUnterKey ? "aktiv" : "";
    b.addEventListener("click", () => gehe(ober.key, u.key));
    nav.appendChild(b);
  }
}
// ----------------------------------------------------------------- Symbole ----
//  Eigene Linien-Symbole statt Emoji: sehen auf jedem Gerät gleich aus und
//  übernehmen die Textfarbe (currentColor), auch im Dunkelmodus. Ohne Netz laden.
const SYMBOLE = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  clipboard: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9zM9 12h6M9 16h4"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><circle cx="17" cy="9" r="2.5"/><path d="M17 14c2.8 0 4.5 1.8 4.5 4.5"/>',
  trophy: '<path d="M8 4h8v6a4 4 0 01-8 0V4z"/><path d="M8 6H4c0 3 1.5 4 4 4M16 6h4c0 3-1.5 4-4 4M12 14v4M8 20h8"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
  chart: '<path d="M5 20V11M12 20V4M19 20v-6M3 20h18"/>',
  checklist: '<path d="M4 6l2 2 3-3M4 14l2 2 3-3M13 7h8M13 15h8"/>',
  bell: '<path d="M6 16v-5a6 6 0 0112 0v5l2 2H4l2-2zM10 21h4"/>',
  play: '<path d="M7 4l13 8-13 8z"/>',
  alert: '<path d="M12 3l10 18H2L12 3zM12 10v5M12 18v.5"/>',
  notes: '<path d="M6 3h9l4 4v14H6zM9 12h6M9 16h4"/>',
  check: '<path d="M5 12l5 5 9-10"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  refresh: '<path d="M20 11a8 8 0 00-14-4L4 9M4 4v5h5M4 13a8 8 0 0014 4l2-2M20 20v-5h-5"/>',
};
export const icon = (name) =>
  `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${SYMBOLE[name] || ""}</svg>`;
// Reiter der unteren Leiste nach Rolle aufbauen (Spielerin vier, Trainer fünf).
export function renderBottomNav() {
  const leiste = $("#tableiste");
  leiste.innerHTML = "";
  for (const o of NavKonfig.tabs(aktRolle, !!eigeneSpielerId())) {
    const b = document.createElement("button");
    b.dataset.ober = o.key;
    b.className = o.key === aktOber ? "aktiv" : "";
    b.innerHTML = `<span class="t-icon">${icon(o.icon)}</span><span class="t-text">${escape(o.label)}</span>`;
    b.addEventListener("click", () => gehe(o.key));
    leiste.appendChild(b);
  }
}

let routenTabelle = {};
// Was beim Oeffnen eines Unterpunkts geladen wird, weiss nur main.js (sonst muesste der Router alle Features kennen).
export function setzeInit(tabelle) { routenTabelle = tabelle; }

