import { renderHomeOffen } from "../features/home.js";
import { ladePortraitIndex, ladePortraitInfo, portraitInfo, wappen } from "./portraits.js";
import { _ausVerlauf, gehe, renderBottomNav, setzeAusVerlauf } from "./router.js";
import { ladeFertig } from "./statuspunkt.js";
import { besuchMelden, nutzungSenden } from "./tracking.js";
import { $, escape, toast } from "./ui.js";

export let aktRolle = "spieler";  // wird aus /api/me (Server) gesetzt; Default = minimal
export let aktBenutzer = null;    // {name, rolle, spieler_id} des angemeldeten Benutzers
export const eigeneSpielerId = () => (aktBenutzer && aktBenutzer.spieler_id) || null;
// ---------------------------------------------------------------- Login ----
//  Die Rolle kommt vom SERVER (/api/me). Der lokale `benutzer`-Hint erlaubt
//  Offline-Weiterarbeit nach einmaligem Online-Login; er gewährt KEINE Rechte
//  (der Server erzwingt Rollen bei jeder Anfrage).

export function setzeBenutzer(me) {
  aktBenutzer = me;
  aktRolle = me.rolle === "trainer" ? "trainer" : "spieler";
  try { localStorage.setItem("benutzer", JSON.stringify(me)); } catch (_) {}
  const el = document.getElementById("benutzer-name");
  if (el) el.textContent = me.name + (aktRolle === "trainer" ? " · Trainer" : "");
  renderAnsicht(me);
  kopfPortraitZeichnen();
}
// Der Kreis oben rechts zeigt dasselbe Wappen wie die Aufstellung: das eigene
// Foto oder, wenn so gewaehlt, den Anfangsbuchstaben.
export function eigenePerson() {
  const me = aktBenutzer || {};
  const i = portraitInfo[me.spieler_id] || {};
  return { id: me.spieler_id || 0, name: i.name || me.name || "?" };
}
export function kopfPortraitZeichnen() {
  const el = document.getElementById("profil-initial");
  if (el) el.innerHTML = `<span class="kopf-rahmen">${wappen(eigenePerson(), 30)}</span>`;
}
// ---------------------------------------------------------- Ansicht als ----
//  Ein Trainer kann die App aus Sicht einer Spielerin ansehen. Der Server
//  loest die Session dann auf die Spielerin auf (nur lesend). Hier nur die
//  Bedienung: Umschalter in der Benutzer-Leiste + Banner im Ansicht-Modus.
let ansichtKonten = null;
function renderAnsicht(me) {
  const banner = document.getElementById("ansicht-banner");
  if (banner) {
    if (me.ansicht_als) {
      banner.classList.remove("hidden");
      banner.innerHTML = "";
      const t = document.createElement("span");
      t.innerHTML = "👁 Ansicht als <b>" + escape(me.name) + "</b>";
      const b = document.createElement("button");
      b.textContent = "zurück zu " + (me.echter_name || "meinem Konto");
      b.addEventListener("click", ansichtStop);
      banner.append(t, b);
    } else {
      banner.classList.add("hidden");
      banner.innerHTML = "";
    }
  }
  const sel = document.getElementById("ansicht-select");
  if (!sel) return;
  const trainerSicht = me.rolle === "trainer" || me.ansicht_als;
  if (!trainerSicht) { sel.classList.add("hidden"); return; }
  fuelleAnsichtSelect(me);
}
async function fuelleAnsichtSelect(me) {
  const sel = document.getElementById("ansicht-select");
  if (!ansichtKonten) {
    try {
      const r = await fetch("/api/ansicht/konten", { cache: "no-store" });
      if (r.ok) ansichtKonten = await r.json();
    } catch (_) { /* offline: Umschalter bleibt verborgen */ }
  }
  if (!ansichtKonten) return;             // erst zeigen, wenn befüllbar
  sel.classList.remove("hidden");
  sel.innerHTML = "";
  const eigen = document.createElement("option");
  eigen.value = ""; eigen.textContent = "Mein Konto (Trainer)";
  sel.appendChild(eigen);
  for (const k of ansichtKonten) {
    const o = document.createElement("option");
    o.value = String(k.benutzer_id);
    o.textContent = "Ansehen als: " + k.name;
    sel.appendChild(o);
  }
  sel.value = me.als_benutzer_id ? String(me.als_benutzer_id) : "";
}
async function ansichtWechseln(wert) {
  try {
    const pfad = wert ? "/api/ansicht/" + wert : "/api/ansicht/stop";
    const r = await fetch(pfad, { method: "POST" });
    if (!r.ok) throw new Error();
    await cachesLeeren();                 // die Spielerinnen-Sicht soll keine Trainer-Antworten aus dem Cache zeigen
    location.reload();
  } catch (_) { toast("Ansicht-Wechsel fehlgeschlagen – Verbindung prüfen."); }
}
async function ansichtStop() {
  try {
    const r = await fetch("/api/ansicht/stop", { method: "POST" });
    if (!r.ok) throw new Error();
    await cachesLeeren();
    location.reload();
  } catch (_) { toast("Kein Netz – gleich noch mal versuchen."); }
}
function benutzerHint() {
  try { return JSON.parse(localStorage.getItem("benutzer") || "null"); } catch (_) { return null; }
}
async function ladeMe() {
  try {
    // Mit Zeitlimit: ohne das kann ein haengender Fetch (z. B. eine tote
    // WLAN-Route am PC) die App fuer immer im Ladebalken stehen lassen.
    const res = await Promise.race([
      fetch("/api/me", { cache: "no-store" }),
      new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 6000)),
    ]);
    if (res.status === 401) return { status: "anon" };
    if (!res.ok) return { status: "fehler" };
    return { status: "ok", me: await res.json() };
  } catch (_) {
    return { status: "offline" };
  }
}
function zeigeLogin() {
  const ls = document.getElementById("login-screen");
  if (ls) ls.classList.remove("hidden");
  ladeFertig();                 // Ladebalken weg, Login zeigen
}
function appStarten() {
  const ls = document.getElementById("login-screen");
  if (ls) ls.classList.add("hidden");
  renderBottomNav();
  besuchMelden();
  // Der Start ist der unterste Verlaufseintrag: von hier schliesst Zurueck
  // die App - so, wie man es von jeder anderen App kennt.
  setzeAusVerlauf(true);
  try { gehe("home"); } finally { setzeAusVerlauf(false); }
  try { history.replaceState({ typ: "nav", ober: "home", unter: "home" }, ""); } catch (_) {}
  ladeFertig();
  setTimeout(pruefeStand, 3000);          // kurz nach dem Start gegenpruefen
}
// ------------------------------------------------------------ Stand-Check ----
//  Im Hintergrund pruefen, ob dieses Geraet alles Aktuelle hat: Zugang (Rolle,
//  Spielerprofil -> "Ich"-Reiter) vom Server und die App-Version (ein neuer
//  Service Worker laedt die App von selbst neu, siehe controllerchange unten).
//  Laeuft nach dem Start, beim Zurueckkehren in die App, alle 5 Minuten und
//  beim Antippen des Sync-Punkts.
let _standLaeuft = false;
export async function pruefeStand(sichtbar) {
  if (_standLaeuft || !aktBenutzer) return;
  _standLaeuft = true;
  try {
    const r = await ladeMe();
    if (r.status === "anon") { toast("Bitte neu anmelden."); zeigeLogin(); return; }
    if (r.status === "ok") {
      const alt = aktBenutzer, me = r.me;
      const geaendert = (alt.spieler_id || null) !== (me.spieler_id || null)
                     || alt.rolle !== me.rolle;
      // Hat jemand sein Portrait geaendert, soll das ohne Neuladen ankommen.
      await ladePortraitInfo();
      setzeBenutzer(me);
      if (geaendert) {
        renderBottomNav();
        renderHomeOffen();
        toast("Dein Zugang wurde aktualisiert ✓");
      } else if (sichtbar) toast("Alles aktuell ✓");
    }
    nutzungSenden();
    const reg = "serviceWorker" in navigator && await navigator.serviceWorker.getRegistration();
    if (reg) reg.update().catch(() => {});
  } finally { _standLaeuft = false; }
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) pruefeStand(); });
setInterval(pruefeStand, 5 * 60 * 1000);
export async function pruefeAnmeldung() {
  await ladePortraitIndex();          // vor dem ersten Rendern: Fotos sind da
  await ladePortraitInfo();
  const r = await ladeMe();
  if (r.status === "ok") { setzeBenutzer(r.me); appStarten(); }
  else if (r.status === "offline" || r.status === "fehler") {
    // Kein Netz ODER der Server hat gestolpert (500): beides ist KEIN
    // "abgemeldet". Wer sich einmal angemeldet hat, arbeitet weiter — sonst
    // landet man bei jedem Server-Schluckauf grundlos wieder auf dem Login.
    const hint = benutzerHint();
    if (hint) { setzeBenutzer(hint); appStarten(); }
    else zeigeLogin();
  } else { zeigeLogin(); }                 // anon (401) -> wirklich anmelden
}
async function login() {
  const name = $("#login-name").value.trim();
  const pin = $("#login-pin").value;
  const fehler = $("#login-fehler");
  fehler.textContent = "";
  if (!name || !pin) { fehler.textContent = "Name und PIN eingeben."; return; }
  $("#login-btn").disabled = true;
  try {
    const res = await fetch("/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, pin }),
    });
    if (!res.ok) {
      let msg = "Name oder PIN falsch.";
      try { const j = await res.json(); if (j && j.detail) msg = j.detail; } catch (_) {}
      fehler.textContent = msg;
      return;
    }
    const me = await res.json();
    const vorher = benutzerHint();
    if (vorher && vorher.name !== me.name) await cachesLeeren();   // anderes Konto: nichts von vorher zeigen
    await ladePortraitInfo();               // erst jetzt angemeldet: Portrait-Wahl holen
    setzeBenutzer(me);
    $("#login-pin").value = "";
    appStarten();
    Sync.pingServer().catch(() => {});     // Daten sofort laden
  } catch (_) {
    fehler.textContent = "Verbindung fehlgeschlagen.";
  } finally {
    $("#login-btn").disabled = false;
  }
}
async function logout() {
  try { await fetch("/api/logout", { method: "POST" }); } catch (_) {}
  try { localStorage.removeItem("benutzer"); localStorage.removeItem("nutzung_q"); } catch (_) {}
  await cachesLeeren();
  location.reload();
}
// Gespiegelte Server-Daten (IndexedDB) verwerfen, damit ein anderes Konto auf demselben
// Geraet nie kurz den Zwischenspeicher des vorherigen sieht (siehe LocalDB.leereCaches).
async function cachesLeeren() {
  try { await LocalDB.leereCaches(); } catch (_) {}
}
$("#login-btn").addEventListener("click", login);
$("#login-pin").addEventListener("keydown", (e) => { if (e.key === "Enter") login(); });
$("#logout-btn").addEventListener("click", logout);
$("#ansicht-select").addEventListener("change", (e) => ansichtWechseln(e.target.value));
