import { aktualisiereAnsicht } from "./aktualisieren.js";
import { ladeSpieler } from "../features/einteilung.js";
import { pruefeStand } from "./konto.js";
import { ladeRangliste } from "../features/spieler.js";
import { toast } from "./ui.js";

// --- Server-Status-Punkt (rechts oben) & Sync-Anzeige ---
let _serverOnline = false;
let _offen = 0;
function malePunkt() {
  const b = document.getElementById("sync-badge");
  if (b) {
    if (_offen > 0) { b.textContent = _offen; b.style.display = "inline-block"; }
    else { b.style.display = "none"; }
  }
  const d = document.getElementById("server-punkt");
  if (!d) return;
  const t = document.getElementById("sync-text");
  d.classList.remove("offline", "arbeitet");
  if (!_serverOnline) {
    d.classList.add("offline");
    if (t) t.textContent = "offline";
    d.title = "Offline – tippen zum Prüfen. Änderungen werden gespeichert.";
  } else if (_offen > 0) {
    d.classList.add("arbeitet");
    if (t) t.textContent = "sendet";
    d.title = _offen + " Änderung(en) werden synchronisiert…";
  } else {
    if (t) t.textContent = "synchron";
    d.title = "Mit Server verbunden – alles synchron";
  }
  const pm = document.getElementById("pm-sync-text");
  if (pm && t) pm.textContent = t.textContent.charAt(0).toUpperCase() + t.textContent.slice(1) + (_offen ? ` · ${_offen} offen` : "");
}
document.addEventListener("server:status", (e) => { _serverOnline = e.detail.online; malePunkt(); });
// sync.js laeuft VOR app.js und pingt sofort. Kommt die Antwort, bevor dieser Code zuhoert
// (beim ersten Laden oder nach einem Update ist app.js noch nicht im Cache), ist das
// Ereignis weg - und es kommt nur bei einer AENDERUNG wieder. Deshalb den Stand selbst lesen.
_serverOnline = !!(window.Sync && Sync.serverOnline);
document.addEventListener("outbox:offen", (e) => { _offen = e.detail.offen; malePunkt(); });
const _punkt = document.getElementById("server-punkt");
if (_punkt) _punkt.addEventListener("click", async () => {
  toast("Synchronisiere…");
  pruefeStand(true);
  const ok = await Sync.jetztSynchronisieren();
  if (ok) aktualisiereAnsicht();                    // auch die angezeigte Seite frisch vom Server holen
  const offen = await Sync.anzahlOffen();
  if (offen === 0) toast(ok ? "Alles synchron ✓" : "Verbunden ✓");
  else if (!ok) toast("Server nicht erreichbar – " + offen + " offen.");
  else toast("Sync-Fehler (" + offen + " offen): " + (Sync.letzterFehler || "unbekannt"));
});
function aktualisiereSichtbar() {
  const sichtbar = (id) => { const el = document.getElementById(id); return el && !el.classList.contains("hidden"); };
  if (sichtbar("view-rangliste")) ladeRangliste();
  if (sichtbar("view-anwesenheit")) ladeSpieler();
}
document.addEventListener("prefetch:fertig", aktualisiereSichtbar);
document.addEventListener("sync:fertig", aktualisiereSichtbar);
malePunkt();
// Start-Overlay (Ladebalken) steuern: Text/Balken setzen bzw. am Ende entfernen.
export function ladeStatus(text, prozent) {
  const t = document.getElementById("ladebalken-text");
  if (t && text != null) t.textContent = text;
  const b = document.getElementById("ladebalken-bar");
  if (b && prozent != null) b.style.width = prozent + "%";
}
export function ladeFertig() {
  const l = document.getElementById("ladebalken");
  if (l) l.remove();
}
