import { ladeSpieler } from "../features/einteilung.js";
import { aktRolle, eigeneSpielerId } from "./konto.js";
import { aktualisiertText, ladeNutzung } from "../features/nutzung.js";
import { aktOber, aktUnter, initFuer } from "./router.js";
import { ladeRangliste } from "../features/spieler.js";
import { toast } from "./ui.js";
import { ladeVideos } from "../features/videos.js";

export function vorZeit(iso) {
  if (!iso) return "noch nie";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 2) return "gerade eben";
  if (min < 60) return "vor " + min + " Min.";
  const std = Math.round(min / 60);
  if (std < 24) return "vor " + std + " Std.";
  const tage = Math.round(std / 24);
  if (tage === 1) return "gestern";
  if (tage < 14) return "vor " + tage + " Tagen";
  return new Date(iso).toLocaleDateString("de-DE");
}
// ---- ↻ Aktualisieren: Nutzung und Videos (Trainer) frisch vom Server holen ----
//  Der Zeitstempel gilt nur fuer ERFOLGREICHES Laden; schlaegt es fehl, steht dort weiter der alte Stand.
const _geladenAm = { nutzung: null, videos: null };
export function zeigeAktualisiert() {
  for (const art of Object.keys(_geladenAm)) {
    const el = document.getElementById("aktual-" + art);
    if (el) el.textContent = aktualisiertText(_geladenAm[art], Date.now(), Sync.serverOnline);
  }
}
export function merkeGeladen(art) { _geladenAm[art] = Date.now(); zeigeAktualisiert(); }
setInterval(zeigeAktualisiert, 30 * 1000);        // "vor 2 Min." weiterlaufen lassen
document.addEventListener("server:status", zeigeAktualisiert);       // online <-> offline sofort anzeigen
export async function aktualisiereAnsicht() {
  const sichtbar = document.querySelector(".view:not(.hidden)");
  const id = sichtbar && sichtbar.id;
  const knoepfe = document.querySelectorAll(".aktual-knopf");
  knoepfe.forEach((b) => { b.disabled = true; b.classList.add("laeuft"); });
  try {
    await Sync.pingServer();                       // ehrlich zeigen, ob der Server erreichbar ist
    if (!Sync.serverOnline) { toast("Offline – es bleibt der letzte Stand."); zeigeAktualisiert(); return; }
    if (id === "view-nutzung") await ladeNutzung();
    else if (id === "view-videos") await ladeVideos();
    else if (id === "view-rangliste") await ladeRangliste();
    else if (id === "view-anwesenheit") await ladeSpieler();
    else {                                         // andere Seiten: ihr normaler Lader (Bereich/Unterpunkt)
      const ziel = NavKonfig.finde(aktRolle, !!eigeneSpielerId(), aktOber, aktUnter);
      const init = initFuer(aktOber, aktUnter);
      if (ziel && ziel.unter.view === id && init) await init();
    }
    zeigeAktualisiert();
  } finally { knoepfe.forEach((b) => { b.disabled = false; b.classList.remove("laeuft"); }); }
}
document.addEventListener("click", (e) => { if (e.target.closest("[data-aktualisieren]")) aktualisiereAnsicht(); });
