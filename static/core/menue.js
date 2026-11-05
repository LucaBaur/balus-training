import { amtOber } from "../features/aemter.js";
import { ichDaten } from "../features/ich.js";
import { aktBenutzer, aktRolle, eigenePerson, eigeneSpielerId } from "./konto.js";
import { wappen } from "./portraits.js";
import { pushStatus } from "../features/push.js";
import { gehe, icon } from "./router.js";
import { $, escape } from "./ui.js";
import { APP_VERSION } from "./version.js";

// ============================================================ Profil-Menü ====
//  Der Kreis oben rechts öffnet Profil, To-Dos, Mitteilungen, Darstellung und Abmelden.
//  Das ersetzt den eigenen Reiter "Ich" und die Leiste mit "Abmelden" auf Home.
function profilMenueOeffnen() {
  baueProfilMenue();
  $("#profil-menue").classList.remove("hidden");
  $("#profil-knopf").setAttribute("aria-expanded", "true");
}
function profilMenueSchliessen() {
  $("#profil-menue").classList.add("hidden");
  $("#profil-knopf").setAttribute("aria-expanded", "false");
}
function baueProfilMenue() {
  const me = aktBenutzer || {};
  const sid = eigeneSpielerId();
  const position = (ichDaten && ichDaten.spieler && ichDaten.spieler.position_angriff) || "";
  $("#pm-kopf").innerHTML =
    `${wappen(eigenePerson(), 40)}
     <span><b>${escape(me.name || "")}</b><small>${aktRolle === "trainer" ? "Trainer" : "Spielerin"}${position ? " · " + escape(position) : ""}</small>${
       (me.aemter || []).length ? `<small class="pm-aemter">${escape(me.aemter.map((a) => a.name).join(" · "))}</small>` : ""}</span>`;
  const eintraege = [];
  if (sid) {
    eintraege.push(["user", "Mein Profil", () => gehe("ich", "ich")]);
    eintraege.push(["checklist", "Meine To-Dos", () => gehe("ich", "todo")]);
    eintraege.push(["chart", "Meine Statistik", () => {
      gehe("ich", "ich");
      setTimeout(() => { const e = $("#ich-statistik"); if (e) e.scrollIntoView({ behavior: "smooth" }); }, 500);
    }]);
  }
  eintraege.push(["users", (me.aemter || []).length ? "Meine Ämter" : "Ämter", () => gehe(amtOber(), "aemter")]);
  eintraege.push(["bell", "Mitteilungen", () => gehe("konto", "mitteilungen")]);
  const liste = $("#pm-liste");
  liste.innerHTML = "";
  for (const [sym, text, aktion] of eintraege) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "pm-zeile pm-knopf";
    b.innerHTML = `<span class="pm-icon">${icon(sym)}</span><span class="pm-label">${escape(text)}</span>` +
      (text === "Mitteilungen" ? '<small class="pm-status"></small>' : "") + `<span class="pm-pfeil">${icon("chevron")}</span>`;
    b.addEventListener("click", () => { profilMenueSchliessen(); aktion(); });
    liste.appendChild(b);
  }
  pushStatus().then((st) => {
    const el = liste.querySelector(".pm-status");
    if (el) el.textContent = st === "aktiv" ? "an" : st === "aus" ? "aus" : "";
  });
  markiereDarstellung();
}
$("#profil-knopf").addEventListener("click", () =>
  $("#profil-menue").classList.contains("hidden") ? profilMenueOeffnen() : profilMenueSchliessen());
$("#profil-menue").addEventListener("click", (e) => { if (e.target.closest("[data-schliessen]")) profilMenueSchliessen(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") profilMenueSchliessen(); });
$("#pm-sync").addEventListener("click", () => { profilMenueSchliessen(); document.getElementById("server-punkt").click(); });
$("#logout-btn").addEventListener("click", profilMenueSchliessen);
// ---- Darstellung: Auto / Hell / Dunkel (theme.js) ----
const _systemDunkel = window.matchMedia ? matchMedia("(prefers-color-scheme: dark)") : { matches: false };
const _speicher = () => { try { return window.localStorage; } catch (_) { return null; } };
let darstellung = Theme.laden(_speicher());
function markiereDarstellung() {
  document.querySelectorAll("#pm-darstellung button").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.darstellung === darstellung)));
}
export function setzeDarstellung(wahl) {
  darstellung = Theme.speichern(_speicher(), wahl);
  Theme.anwenden(document, darstellung, _systemDunkel.matches);
  markiereDarstellung();
}
document.querySelectorAll("#pm-darstellung button").forEach((b) =>
  b.addEventListener("click", () => setzeDarstellung(b.dataset.darstellung)));
// Folgt das Gerät automatisch, soll auch ein Wechsel von Hell auf Dunkel am Abend ankommen.
if (_systemDunkel.addEventListener) {
  _systemDunkel.addEventListener("change", () => Theme.anwenden(document, darstellung, _systemDunkel.matches));
}
const versionEl = document.getElementById("version");
if (versionEl) versionEl.textContent = APP_VERSION;
