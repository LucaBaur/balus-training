import { aktBenutzer } from "./konto.js";
import { verweilSegment } from "../features/nutzung.js";
import { aktOber, aktUnter } from "./router.js";
import { APP_VERSION } from "./version.js";

// ---------------------------------------------------------------- Nutzung ----
//  Meldet dem Server, wann jemand die App oeffnet, welchen Bereich sie/er
//  besucht und welches Video angesehen wird (siehe Team -> Nutzung). Die
//  Ereignisse werden gesammelt und gebuendelt gesendet; schlaegt das fehl
//  (kein Netz), bleiben sie im localStorage und gehen beim naechsten Mal mit.
//  Im "Ansicht als"-Modus wird nichts gemeldet.
let _nutzungQ = [];
try { _nutzungQ = JSON.parse(localStorage.getItem("nutzung_q") || "[]"); } catch (_) {}
let _nutzungTimer = null;
let _nutzungSendet = false;
let _letzterBesuch = 0;
function nutzungSpeichern() {
  try { localStorage.setItem("nutzung_q", JSON.stringify(_nutzungQ)); } catch (_) {}
}
//  Verweildauer: Ein Segment laeuft, solange ein Bereich oder Video offen und die App
//  im Vordergrund ist. Es endet beim naechsten Wechsel oder wenn die App in den
//  Hintergrund geht und wird als Ereignis "verweil" in dieselbe Warteschlange gelegt.
export let _segment = null;            // { ziel, start } - laeuft gerade
let _segmentPause = null;       // Ziel, das beim Zurueckkehren weiterlaeuft
function segmentBeenden() {
  if (!_segment) return;
  const s = verweilSegment(_segment.start, Date.now());
  const ziel = _segment.ziel;
  _segment = null;
  if (s) nutzungMelden("verweil", ziel, null, s);
}
export function segmentStarten(ziel) {
  segmentBeenden();
  _segmentPause = null;
  _segment = ziel ? { ziel, start: Date.now() } : null;
}
export function nutzungMelden(typ, ziel, info, dauer_s) {
  if (!aktBenutzer || aktBenutzer.ansicht_als) { _segment = null; return; }
  if (typ === "bereich" || typ === "video") segmentStarten(ziel);
  _nutzungQ.push({ typ, ziel: ziel || null, info: info || null, ...(dauer_s ? { dauer_s } : {}) });
  if (_nutzungQ.length > 200) _nutzungQ.splice(0, _nutzungQ.length - 200);
  nutzungSpeichern();
  clearTimeout(_nutzungTimer);
  _nutzungTimer = setTimeout(nutzungSenden, 2000);
}
export function besuchMelden() {
  if (Date.now() - _letzterBesuch < 30 * 60 * 1000) return;   // wie der Server: 30 Min. = ein Besuch
  _letzterBesuch = Date.now();
  nutzungMelden("besuch");
  geraetMelden();
}
export async function nutzungSenden() {
  if (_nutzungSendet || !_nutzungQ.length || !aktBenutzer || aktBenutzer.ansicht_als) return;
  _nutzungSendet = true;
  try {
    const paket = _nutzungQ.slice(0, 50);
    const res = await fetch("/api/nutzung", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ereignisse: paket }), keepalive: true,
    });
    if (res.ok) {
      _nutzungQ.splice(0, paket.length);
      nutzungSpeichern();
    } else if (res.status === 401) {          // abgemeldet: nichts fremden Konten zuordnen
      _nutzungQ = [];
      nutzungSpeichern();
    }
  } catch (_) { /* kein Netz: bleibt in der Warteschlange */ }
  finally { _nutzungSendet = false; }
  if (_nutzungQ.length >= 50) nutzungSenden();
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    _segmentPause = _segment && _segment.ziel;   // Hintergrund zaehlt nicht als Verweildauer
    segmentBeenden();
    nutzungSenden();                             // vor dem Wegwischen noch abschicken
  } else {
    if (_segmentPause) _segment = { ziel: _segmentPause, start: Date.now() };
    _segmentPause = null;
    besuchMelden();
  }
});
setInterval(nutzungSenden, 60 * 1000);        // Reste nach einem Funkloch nachsenden
// ----------------------------------------------------- Geraet & Fehler ----
//  Grobe Geraeteangaben (System, Browser, installiert oder nicht, Bildschirm,
//  Modell falls der Browser es nennt) und Fehlerberichte - damit ein Problem
//  zu "Android 13 / Chrome 126" passt. Keine IP, kein Standort, keine Kennung.
//  Fehlertexte gehen nur an den eigenen Server (Team -> Nutzung).
let _geraet = null;
async function geraetInfo() {
  if (!_geraet) {
    const ua = navigator.userAgent || "";
    const m = (re) => (ua.match(re) || [])[1];
    const major = (v) => String(v || "").split(/[._]/)[0];
    const hoch = {};
    try {
      if (navigator.userAgentData && navigator.userAgentData.getHighEntropyValues) {
        Object.assign(hoch, await navigator.userAgentData.getHighEntropyValues(["model", "platformVersion"]));
      }
    } catch (_) {}
    // Chrome meldet im User-Agent nur noch "Android 10" - die echte Version steckt in platformVersion.
    let os = "";
    if (/Android/.test(ua)) os = "Android " + (major(hoch.platformVersion) || m(/Android (\d+)/) || "");
    else if (/iPhone|iPad|iPod/.test(ua)) os = "iOS " + major(m(/OS (\d+[_\d]*)/));
    else if (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) os = "iPadOS";
    else if (/Windows/.test(ua)) os = "Windows" + (hoch.platformVersion ? (parseInt(major(hoch.platformVersion), 10) >= 13 ? " 11" : " 10") : "");
    else if (/Mac OS X/.test(ua)) os = "macOS";
    else if (/Linux/.test(ua)) os = "Linux";
    let browser = "";
    for (const [name, re] of [["Edge", /Edg(?:e|A|iOS)?\/(\d+)/], ["Opera", /OPR\/(\d+)/],
        ["Samsung Internet", /SamsungBrowser\/(\d+)/], ["Chrome", /(?:Chrome|CriOS)\/(\d+)/],
        ["Firefox", /(?:Firefox|FxiOS)\/(\d+)/], ["Safari", /Version\/(\d+)[^]*Safari/]]) {
      const v = m(re);
      if (v) { browser = name + " " + v; break; }
    }
    if (/; wv\)/.test(ua)) browser = "WebView " + (m(/Chrome\/(\d+)/) || "");
    let modus = "Browser";
    if ((document.referrer || "").startsWith("android-app://")) modus = "Android-App";
    else if (navigator.standalone === true
             || (window.matchMedia && matchMedia("(display-mode: standalone)").matches)) modus = "installiert";
    _geraet = { os: os.trim(), browser: browser.trim(), modus,
                bildschirm: screen.width + "x" + screen.height, modell: hoch.model || "" };
  }
  return { ..._geraet, app_version: APP_VERSION,
           sw: !!(navigator.serviceWorker && navigator.serviceWorker.controller) };
}
const geraetKurz = (g) => [g.os, g.browser, g.modus].filter(Boolean).join(" · ");
async function nutzungPost(pfad, daten) {
  return fetch(pfad, { method: "POST", headers: { "Content-Type": "application/json" },
                       body: JSON.stringify(daten), keepalive: true });
}
async function geraetMelden() {
  if (!aktBenutzer || aktBenutzer.ansicht_als) return;
  try { await nutzungPost("/api/geraet", await geraetInfo()); } catch (_) {}
}
// Hoechstens 10 verschiedene Fehler je Sitzung, jeder nur einmal - eine Fehlerschleife
// soll weder den Akku noch den Server beschaeftigen.
const _fehlerGemeldet = new Set();
const FEHLER_IGNORIEREN = /ResizeObserver|Failed to fetch|Load failed|NetworkError|Network request failed|AbortError|^Script error/i;
async function fehlerMelden(quelle, meldung) {
  meldung = String(meldung || "").slice(0, 300);
  if (!meldung || FEHLER_IGNORIEREN.test(meldung)) return;       // Netzfehler sind normal, kein Bug
  if (!aktBenutzer || aktBenutzer.ansicht_als) return;
  if (_fehlerGemeldet.has(meldung) || _fehlerGemeldet.size >= 10) return;
  _fehlerGemeldet.add(meldung);
  try {
    const g = await geraetInfo();
    await nutzungPost("/api/fehler", { quelle, meldung, ort: aktOber + "/" + aktUnter,
                                       app_version: APP_VERSION, geraet: geraetKurz(g) });
  } catch (_) {}
}
window.addEventListener("error", (e) => {
  if (!(e instanceof ErrorEvent)) return;                         // fehlende Bilder/Skripte: kein JS-Fehler
  const datei = String(e.filename || "").split("/").pop().split("?")[0];
  fehlerMelden("script", (e.message || "Fehler") + (datei ? " @" + datei + ":" + e.lineno : ""));
});
window.addEventListener("unhandledrejection", (e) => {
  const r = e.reason;
  fehlerMelden("promise", "Promise: " + (r && r.message ? r.message : String(r)));
});
{
  const vp = document.getElementById("vd-player");
  if (vp) vp.addEventListener("error", () => {
    if (!vp.getAttribute("src")) return;                          // Zuruecksetzen beim Schliessen ist kein Fehler
    const er = vp.error;
    fehlerMelden("video", "Video nicht abspielbar (Code " + (er ? er.code : "?") + ") "
                          + vp.getAttribute("src").replace(/^.*\/api\//, "/api/"));
  });
}
export function nutzungBereichName(key) {
  const [o, u] = String(key).split("/");
  // Gleiche Schlüssel gibt es für beide Rollen (Training/Termine); der erste Treffer reicht für den Namen.
  const ober = NavKonfig.NAV.find((x) => x.key === o && x.unter.some((y) => y.key === u));
  const unter = ober && ober.unter.find((x) => x.key === u);
  return ober && unter ? ober.label + " → " + unter.label : key;
}
