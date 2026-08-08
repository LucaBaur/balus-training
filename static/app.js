"use strict";

// -------------------------------------------------------------- Zustand ----
let spielerAlle = [];          // alle aktiven Spielerinnen (vom Server)
const anwesend = new Set();    // ausgewaehlte IDs
let teamListe = [];            // 2-4 Teams, je ein Array von Spieler-Objekten
let teamAnzahl = 2;            // gewuenschte Anzahl (bleibt zwischen Spielen)
let trainingsListe = [];       // Trainings (Team-Einteilung-Auswahl)
let aktTraining = null;        // aktuell geöffnetes Training (Detail/Plan-Editor)
let spielToken = null;         // Idempotenz-Schluessel des aktuellen Spiels
let sendeLaeuft = false;       // verhindert paralleles Doppel-Absenden

const $ = (sel) => document.querySelector(sel);

// Eindeutiger Token je geplantem Spiel. Wird bei neuen/neu gemischten Teams und
// nach jedem erfolgreich gespeicherten Spiel erneuert, damit ein wackeliger
// Handy-Upload dasselbe Spiel nie doppelt zaehlen kann (Server dedupliziert).
function neuerSpielToken() {
  spielToken = (crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : "t-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

async function api(pfad, methode = "GET", body = null) {
  const opt = { method: methode, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const res = await fetch(pfad, opt);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || res.statusText);
  }
  return res.status === 204 ? null : res.json();
}

// ================================================================ Navigation ==
//  Zwei Ebenen: unten die Überpunkte (#tableiste), oben die Unterpunkte des
//  aktiven Überpunkts (#subnav). Eine NAV-Konfiguration treibt beides.
//
//  ROLLEN: 'trainer' sieht alles, 'spieler' nur eine reduzierte Auswahl. Die
//  Rolle filtert hier NUR die Sichtbarkeit — das ist KEINE Sicherheitsgrenze!
//  Echte, server-seitig erzwungene Rollen + Login kommen in Phase 4. Bis dahin
//  ist der Umschalter reine Vorschau.
const NAV = [
  { key: "home", label: "Home", rollen: ["trainer", "spieler"], unter: [
    { key: "home", label: "Übersicht", view: "view-home", init: ladeHome },
  ]},
  { key: "training", label: "Training", rollen: ["trainer", "spieler"], unter: [
    { key: "trainings", label: "Termine", view: "view-trainings", init: ladeTrainingsListe },
    { key: "aufstellung", label: "Aufstellung", view: "view-aufstellung", init: ladeAufstellung },
    { key: "teams", label: "Einteilung", view: "view-anwesenheit", nurTrainer: true,
      init: () => { ladeSpieler().catch(() => {}); ladeTrainings().catch(() => {}); } },
    { key: "uebungen", label: "Übungen", view: "view-wiki", nurTrainer: true,
      init: () => ladeWiki("uebung", "Übungen") },
    { key: "coach", label: "Coach", view: "view-coach", nurTrainer: true, init: starteCoach },
  ]},
  { key: "team", label: "Team", rollen: ["trainer"], unter: [
    { key: "rangliste", label: "Rangliste", view: "view-rangliste", init: ladeRangliste },
    { key: "kader", label: "Kader", view: "view-kader", init: ladeKader },
    { key: "statistik", label: "Statistik", view: "view-wiki",
      init: () => ladeWiki("statistik", "Statistik") },
  ]},
  { key: "taktik", label: "Taktik", rollen: ["trainer", "spieler"], unter: [
    { key: "playbook", label: "Playbook", view: "view-wiki",
      init: () => ladeWiki("playbook", "Playbook") },
    { key: "gegner", label: "Gegner", view: "view-wiki", nurTrainer: true,
      init: () => ladeWiki("gegner", "Gegnercheck") },
  ]},
  { key: "saison", label: "Saison", rollen: ["trainer"], unter: [
    { key: "orga", label: "Orga", view: "view-wiki",
      init: () => ladeWiki(["saison", "orga"], "Saison & Orga") },
    { key: "notizen", label: "Notizen", view: "view-wiki",
      init: () => ladeWiki(["notiz", "besprechung"], "Notizen") },
  ]},
];

let aktRolle = "spieler";  // wird aus /api/me (Server) gesetzt; Default = minimal
let aktBenutzer = null;    // {name, rolle, spieler_id} des angemeldeten Benutzers
let aktOber = "home";
let aktUnter = "home";     // aktiver Unterpunkt (für „zurück" aus Detailansichten)

function sichtbareOber() {
  return NAV.filter((o) => o.rollen.includes(aktRolle));
}
function sichtbareUnter(o) {
  return o.unter.filter((u) => !(u.nurTrainer && aktRolle !== "trainer"));
}

// ---------------------------------------------------------------- Verlauf ---
//  Ohne Verlaufseintraege schliesst die Android-Zurueck-Taste in der TWA die
//  App, statt eine Ebene zurueckzugehen. Jede Navigation legt einen Eintrag an;
//  eine Detailansicht merkt sich, aus welcher Liste sie geoeffnet wurde.
let _ausVerlauf = false;   // true, solange popstate den Zustand wiederherstellt
let _inGehe = false;       // true, solange gehe() die View umschaltet

function verlaufMerken(zustand) {
  if (_ausVerlauf) return;
  try { history.pushState(zustand, ""); } catch (_) {}
}

// View des aktuellen Unterpunkts – dorthin fuehren die "zurueck"-Knoepfe.
function navView() {
  const ober = sichtbareOber().find((o) => o.key === aktOber) || sichtbareOber()[0];
  const unter = sichtbareUnter(ober).find((u) => u.key === aktUnter);
  return unter && unter.view;
}

window.addEventListener("popstate", (e) => {
  const z = e.state;
  _ausVerlauf = true;
  try { gehe(z && z.ober, z && z.unter); } finally { _ausVerlauf = false; }
});

function zeigeView(id) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  const el = $("#" + id);
  if (el) el.classList.remove("hidden");
  window.scrollTo(0, 0);
  // Detail geoeffnet (nicht ueber die Navigation, nicht zurueck zur Liste)
  // -> Verlaufseintrag, damit Zurueck wieder auf der Liste landet.
  if (!_ausVerlauf && !_inGehe && id !== navView()) {
    verlaufMerken({ typ: "detail", ober: aktOber, unter: aktUnter });
  }
}

// Zu einem Überpunkt wechseln; optional direkt zu einem bestimmten Unterpunkt.
function gehe(oberKey, unterKey) {
  const ober = sichtbareOber().find((o) => o.key === oberKey) || sichtbareOber()[0];
  aktOber = ober.key;
  document.querySelectorAll("#tableiste button").forEach((b) =>
    b.classList.toggle("aktiv", b.dataset.ober === aktOber));
  const unterListe = sichtbareUnter(ober);
  const unter = unterListe.find((u) => u.key === unterKey) || unterListe[0];
  aktUnter = unter && unter.key;
  renderSubnav(ober, aktUnter);
  if (unter) {
    _inGehe = true;
    try { zeigeView(unter.view); } finally { _inGehe = false; }
    try { unter.init && unter.init(); } catch (_) {}
  }
  verlaufMerken({ typ: "nav", ober: aktOber, unter: aktUnter });
}

// Unter-Navigation zeichnen; bei nur einem Unterpunkt ausblenden (kein Nutzen).
function renderSubnav(ober, aktUnterKey) {
  const nav = $("#subnav");
  const unterListe = sichtbareUnter(ober);
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

document.querySelectorAll("#tableiste button").forEach((b) =>
  b.addEventListener("click", () => gehe(b.dataset.ober)));

// ---------------------------------------------------------------- Login ----
//  Die Rolle kommt vom SERVER (/api/me). Der lokale `benutzer`-Hint erlaubt
//  Offline-Weiterarbeit nach einmaligem Online-Login; er gewährt KEINE Rechte
//  (der Server erzwingt Rollen bei jeder Anfrage).

function setzeBenutzer(me) {
  aktBenutzer = me;
  aktRolle = me.rolle === "trainer" ? "trainer" : "spieler";
  try { localStorage.setItem("benutzer", JSON.stringify(me)); } catch (_) {}
  const el = document.getElementById("benutzer-name");
  if (el) el.textContent = me.name + (aktRolle === "trainer" ? " · Trainer" : "");
}

function benutzerHint() {
  try { return JSON.parse(localStorage.getItem("benutzer") || "null"); } catch (_) { return null; }
}

async function ladeMe() {
  try {
    const res = await fetch("/api/me", { cache: "no-store" });
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
  // Der Start ist der unterste Verlaufseintrag: von hier schliesst Zurueck
  // die App - so, wie man es von jeder anderen App kennt.
  _ausVerlauf = true;
  try { gehe("home"); } finally { _ausVerlauf = false; }
  try { history.replaceState({ typ: "nav", ober: "home", unter: "home" }, ""); } catch (_) {}
  ladeFertig();
}

async function pruefeAnmeldung() {
  const r = await ladeMe();
  if (r.status === "ok") { setzeBenutzer(r.me); appStarten(); }
  else if (r.status === "offline") {
    const hint = benutzerHint();          // nach früherem Online-Login weiterarbeiten
    if (hint) { setzeBenutzer(hint); appStarten(); }
    else zeigeLogin();
  } else { zeigeLogin(); }                 // anon / Fehler -> anmelden
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
    setzeBenutzer(await res.json());
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
  try { localStorage.removeItem("benutzer"); } catch (_) {}
  location.reload();
}

$("#login-btn").addEventListener("click", login);
$("#login-pin").addEventListener("keydown", (e) => { if (e.key === "Enter") login(); });
$("#logout-btn").addEventListener("click", logout);

// ------------------------------------------------------------- Web-Push ----
function pushMoeglich() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function base64ZuUint8(base64) {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const b64 = (base64 + pad).replace(/-/g, "+").replace(/_/g, "/");
  const roh = atob(b64);
  const arr = new Uint8Array(roh.length);
  for (let i = 0; i < roh.length; i++) arr[i] = roh.charCodeAt(i);
  return arr;
}

async function pushStatus() {
  if (!pushMoeglich()) return "nicht_unterstuetzt";
  if (Notification.permission === "denied") return "blockiert";
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    return sub ? "aktiv" : "aus";
  } catch (_) { return "aus"; }
}

async function pushAktivieren() {
  if (!pushMoeglich()) { toast("Push wird von diesem Gerät nicht unterstützt."); return; }
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { toast("Benachrichtigungen nicht erlaubt."); return renderPushBox(); }
    const { publicKey } = await api("/api/push/vapid");
    if (!publicKey) { toast("Kein Push-Schlüssel am Server."); return; }
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64ZuUint8(publicKey),
    });
    const j = sub.toJSON();
    await api("/api/push/subscribe", "POST", { endpoint: j.endpoint, keys: j.keys });
    toast("Benachrichtigungen aktiviert ✓");
  } catch (e) { toast("Fehler: " + e.message); }
  renderPushBox();
}

async function pushTest() {
  try {
    const r = await api("/api/push/test", "POST");
    toast(r.gesendet ? "Test gesendet – Benachrichtigung kommt gleich."
      : "Kein aktives Abo auf diesem Gerät.");
  } catch (e) { toast("Fehler: " + e.message); }
}

async function pushDeaktivieren() {
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      await api("/api/push/unsubscribe", "POST", { endpoint: sub.endpoint }).catch(() => {});
      await sub.unsubscribe();
    }
    toast("Benachrichtigungen aus.");
  } catch (e) { toast("Fehler: " + e.message); }
  renderPushBox();
}

async function renderPushBox() {
  const el = document.getElementById("push-box");
  if (!el) return;
  const st = await pushStatus();
  if (st === "nicht_unterstuetzt") {
    el.innerHTML = '<span class="push-hint">🔔 Push wird hier nicht unterstützt (am iPhone: App erst „zum Startbildschirm").</span>';
  } else if (st === "blockiert") {
    el.innerHTML = '<span class="push-hint">🔔 Benachrichtigungen im Browser blockiert – in den Einstellungen erlauben.</span>';
  } else if (st === "aktiv") {
    el.innerHTML = '<span class="push-hint">🔔 aktiv</span>' +
      '<button id="push-test">Test</button><button id="push-aus">Aus</button>';
    document.getElementById("push-test").addEventListener("click", pushTest);
    document.getElementById("push-aus").addEventListener("click", pushDeaktivieren);
  } else {
    el.innerHTML = '<button id="push-an" class="primaer">🔔 Benachrichtigungen aktivieren</button>';
    document.getElementById("push-an").addEventListener("click", pushAktivieren);
  }
}

// Trainer: Push-Erinnerung an alle senden, die noch nicht geantwortet haben.
function renderErinnern(d) {
  const el = document.getElementById("td-erinnern");
  if (!el) return;
  if (aktRolle !== "trainer") { el.innerHTML = ""; return; }
  el.innerHTML = '<button id="btn-erinnern">🔔 Erinnerung an Offene senden</button>';
  document.getElementById("btn-erinnern").addEventListener("click", async () => {
    const b = document.getElementById("btn-erinnern");
    b.disabled = true;
    try {
      const r = await api("/api/trainings/" + d.id + "/erinnern", "POST");
      toast(r.offen
        ? `Erinnerung an ${r.offen} Spielerin(nen) – ${r.gesendet} Gerät(e) erreicht.`
        : "Alle haben schon geantwortet.");
    } catch (e) { toast("Fehler: " + e.message); }
    finally { b.disabled = false; }
  });
}

// Bottom-Nav nach Rolle auf-/zubauen (Spieler sieht weniger Überpunkte).
function renderBottomNav() {
  const erlaubt = new Set(sichtbareOber().map((o) => o.key));
  document.querySelectorAll("#tableiste button").forEach((b) =>
    b.classList.toggle("weg", !erlaubt.has(b.dataset.ober)));
}

// ------------------------------------------------------------------ Home ----
async function ladeHome() {
  const el = $("#home-naechstes");
  el.innerHTML = '<p class="hinweis">Lädt…</p>';
  let nt = null;
  try { nt = await Sync.apiOffline("/api/naechstes-training"); } catch (_) {}
  if (nt && nt.id) {
    const an = (nt.teilnahme || []).filter((t) => t.status === "anwesend").length;
    const ab = (nt.teilnahme || []).filter((t) => t.status === "abgesagt").length;
    const label = nt.datum ? datumKurz(nt.datum) : "";
    el.innerHTML =
      `<div class="hk-titel">Nächstes Training</div>
       <div class="hk-name">${escape(nt.titel || label)}</div>
       <div class="hk-datum">${label}${nt.uhrzeit ? " · " + escape(nt.uhrzeit) : ""}</div>
       <div class="hk-zahlen"><span class="zu">${an} zugesagt</span><span class="ab">${ab} abgesagt</span></div>`;
    el.className = "home-karte klickbar";
    el.onclick = () => { gehe("training", "trainings"); setTimeout(() => oeffneTraining(nt.id), 0); };
  } else {
    el.className = "home-karte";
    el.onclick = null;
    el.innerHTML = '<div class="hk-titel">Nächstes Training</div><p class="hinweis">Kein anstehendes Training gefunden.</p>';
  }
  renderHomeSchnell();
  renderPushBox();
}

function renderHomeSchnell() {
  const el = $("#home-schnell");
  const ziele = aktRolle === "spieler"
    ? [["training", "trainings", "📋", "Trainings"], ["taktik", "playbook", "🎯", "Playbook"]]
    : [["training", "trainings", "📋", "Trainings"], ["team", "rangliste", "🏆", "Rangliste"],
       ["training", "coach", "💬", "Coach"], ["taktik", "playbook", "🎯", "Playbook"]];
  el.innerHTML = "";
  for (const [ober, unter, icon, label] of ziele) {
    const b = document.createElement("button");
    b.className = "schnell-kachel";
    b.innerHTML = `<span class="sk-icon">${icon}</span><span>${label}</span>`;
    b.addEventListener("click", () => gehe(ober, unter));
    el.appendChild(b);
  }
  if (aktRolle === "spieler") {
    const hin = document.createElement("p");
    hin.className = "hinweis spieler-hinweis";
    hin.textContent = "Zu- und Absagen machst du unter „Termine“.";
    el.appendChild(hin);
  }
}

// ==================================================== Termine-Uebersicht =====
//  Wer kann wann? Die Liste zeigt die Zusagen schon in der Zeile, damit man
//  eine duenne Einheit sieht, BEVOR man in der Halle steht. Antippen klappt
//  die Namen auf; die Namen kommen aus /api/trainings/{id} und werden gemerkt.

const offeneTermine = new Set();     // aufgeklappte Termine (id)
const terminDetails = new Map();     // id -> Detail mit Namen (einmal geladen)

const WOCHENTAG_KURZ = ["SO", "MO", "DI", "MI", "DO", "FR", "SA"];
const MONAT_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

function datumTeile(iso) {
  const d = new Date((iso || "") + "T12:00:00");
  if (!iso || isNaN(d)) return { wt: "", tag: iso || "" };
  return { wt: WOCHENTAG_KURZ[d.getDay()], tag: d.getDate() + ". " + MONAT_KURZ[d.getMonth()] };
}

// Traegt die Einheit? Absolute Zahlen, weil Handball Koerper braucht: unter
// sechs Zusagen laesst sich kaum sinnvoll trainieren.
function terminStufe(t) {
  const zu = t.anwesend || 0;
  if (zu <= 5) return "kritisch";
  if (zu <= 8) return "knapp";
  return "ok";
}

async function ladeTrainingsListe() {
  $("#trainings-titel").textContent = aktRolle === "spieler" ? "Meine Termine" : "Termine";
  renderTrainingNeu();
  const el = $("#trainings-liste");
  const warn = $("#trainings-warnung");
  if (warn) warn.innerHTML = "";
  el.innerHTML = '<p class="hinweis">Lädt…</p>';
  let liste = [];
  try { liste = await Sync.apiOffline("/api/trainings"); } catch (_) {
    el.innerHTML = '<p class="hinweis">Termine noch nicht verfügbar (einmal online öffnen).</p>';
    return;
  }
  if (!liste.length) { el.innerHTML = '<p class="hinweis">Noch kein Termin eingetragen.</p>'; return; }

  const heute = new Date().toISOString().slice(0, 10);
  const kommend = liste.filter((t) => (t.datum || "") >= heute)
                       .sort((a, b) => (a.datum || "").localeCompare(b.datum || ""));
  const vorbei = liste.filter((t) => (t.datum || "") < heute);   // API liefert absteigend

  el.innerHTML = "";
  if (kommend.length) {
    el.appendChild(gruppenKopf("Kommende Termine"));
    kommend.forEach((t) => el.appendChild(terminKarte(t, false)));
  }
  if (vorbei.length) {
    el.appendChild(gruppenKopf("Vergangen"));
    vorbei.slice(0, 8).forEach((t) => el.appendChild(terminKarte(t, true)));
  }
  renderTerminWarnung(kommend);
}

function gruppenKopf(text) {
  const d = document.createElement("div");
  d.className = "termin-gruppe";
  d.textContent = text;
  return d;
}

// Fruehwarnung: die naechste Einheit, bei der es nicht reicht.
function renderTerminWarnung(kommend) {
  const el = $("#trainings-warnung");
  if (!el) return;
  const duenn = kommend.filter((t) => terminStufe(t) === "kritisch");
  if (!duenn.length) { el.innerHTML = ""; return; }
  const t = duenn[0], d = datumTeile(t.datum);
  const weitere = duenn.length - 1;
  const zusatz = weitere === 0 ? ""
    : weitere === 1 ? ", und eine weitere Einheit ist ähnlich dünn"
    : `, und ${weitere} weitere Einheiten sind ähnlich dünn`;
  el.innerHTML =
    `<div class="termin-warnung"><span class="wz">⚠</span><div>
       <b>${d.wt} ${d.tag}: nur ${t.anwesend || 0} Zusagen</b>
       <p>${escape(t.titel || "Training")} — ${t.abgesagt || 0} abgesagt${zusatz}.
          Früh genug, um zu verschieben, zusammenzulegen oder abzusagen.</p>
     </div></div>`;
}

function terminKarte(t, vergangen) {
  const d = datumTeile(t.datum);
  const stufe = vergangen ? "ok" : terminStufe(t);
  const zu = t.anwesend || 0, ab = t.abgesagt || 0;
  const kader = t.kader || Math.max(zu + ab, 1);
  const auf = offeneTermine.has(t.id);

  const art = document.createElement("article");
  art.className = "termin"
    + (vergangen ? " vergangen" : (stufe === "ok" ? "" : " " + stufe))
    + (auf ? " auf" : "");

  const meinChip = t.meine_status === "anwesend" ? '<span class="t-meine ja">DABEI</span>'
    : t.meine_status === "abgesagt" ? '<span class="t-meine nein">ABGESAGT</span>'
    : t.meine_status === "unsicher" ? '<span class="t-meine un">UNSICHER</span>' : "";

  const kopf = document.createElement("button");
  kopf.className = "t-kopf";
  kopf.setAttribute("aria-expanded", auf ? "true" : "false");
  kopf.innerHTML =
    `<span class="t-datum"><b>${d.wt}</b><span>${escape(d.tag)}</span></span>
     <span class="t-mitte"><b>${escape(t.titel || "Training")}</b>
       <small>${t.uhrzeit ? escape(t.uhrzeit) : "ohne Uhrzeit"}${t.ort ? " · " + escape(t.ort) : ""}` +
      `${t.hat_plan && aktRolle === "trainer"
          ? `<span class="t-planchip">PLAN${t.plan_minuten ? " " + t.plan_minuten + "′" : ""}</span>` : ""}${meinChip}</small>
       <span class="t-bar"><i class="zu" style="width:${(zu / kader) * 100}%"></i>` +
      `<i class="ab" style="width:${(ab / kader) * 100}%"></i></span></span>
     <span class="t-zahl"><b>${zu}</b><small>${stufe === "kritisch" ? "zu wenig" : "Zusagen"}</small></span>`;
  kopf.addEventListener("click", () => {
    if (auf) offeneTermine.delete(t.id); else offeneTermine.add(t.id);
    ladeTrainingsListe();
  });
  art.appendChild(kopf);

  const det = document.createElement("div");
  det.className = "t-detail";
  det.innerHTML = '<p class="t-laedt">Namen werden geladen…</p>';
  art.appendChild(det);
  if (auf) fuelleTerminDetail(det, t);
  return art;
}

async function fuelleTerminDetail(det, t) {
  let d = terminDetails.get(t.id);
  if (!d) {
    try {
      d = await Sync.apiOffline("/api/trainings/" + t.id);
      terminDetails.set(t.id, d);
    } catch (_) {
      det.innerHTML = '<p class="t-laedt">Die Namen gibt es, sobald du einmal online warst.</p>';
      return;
    }
  }
  det.innerHTML = "";
  const teil = d.teilnahme || [];
  const grp = (s) => teil.filter((x) => x.status === s);

  if (aktBenutzer && aktBenutzer.spieler_id) {
    const box = document.createElement("div");
    box.className = "td-rsvp";
    rsvpFuellen(box, d);
    det.appendChild(box);
  }

  anhaengen(det, namensGruppe("Zugesagt", "zu", grp("anwesend")));
  anhaengen(det, namensGruppe("Unsicher", "un", grp("unsicher")));
  anhaengen(det, absagenGruppe(grp("abgesagt")));
  anhaengen(det, namensGruppe("Keine Rückmeldung", "offen",
    teil.filter((x) => x.status === "nominiert" || !x.status)));

  if (aktRolle === "trainer") det.appendChild(terminAktionen(t));
}

function anhaengen(ziel, el) { if (el) ziel.appendChild(el); }

function namensGruppe(titel, kl, arr) {
  if (!arr.length) return null;
  const g = document.createElement("div");
  g.className = "t-gruppe " + kl;
  g.innerHTML = `<div class="gk">${titel} · ${arr.length}</div><div class="t-namen">` +
    arr.map((p) => `<span class="t-name">${escape(p.name)}` +
      `${p.position === "Tor" ? ' <span class="tw">TW</span>' : ""}</span>`).join("") +
    `</div>`;
  return g;
}

// Absagen als Liste statt als Chips - hier gehoert der Grund daneben.
function absagenGruppe(arr) {
  if (!arr.length) return null;
  const g = document.createElement("div");
  g.className = "t-gruppe ab";
  g.innerHTML = `<div class="gk">Abgesagt · ${arr.length}</div><div class="ab-liste">` +
    arr.map((p) =>
      `<div class="ab-zeile"><span class="az-n">${escape(p.name)}</span>` +
      `<span class="az-g${p.grund ? "" : " fehlt"}">${escape(p.grund || "kein Grund angegeben")}</span></div>`
    ).join("") + `</div>`;
  return g;
}

function terminAktionen(t) {
  const akt = document.createElement("div");
  akt.className = "t-aktionen";

  const oeffnen = document.createElement("button");
  oeffnen.textContent = "Öffnen & Plan";
  oeffnen.addEventListener("click", () => oeffneTraining(t.id));
  akt.appendChild(oeffnen);

  const erinnern = document.createElement("button");
  erinnern.textContent = "🔔 Erinnerung senden";
  erinnern.addEventListener("click", async () => {
    erinnern.disabled = true;
    try {
      const r = await api("/api/trainings/" + t.id + "/erinnern", "POST");
      toast(r.offen ? `Erinnerung an ${r.offen} Spielerin(nen) – ${r.gesendet} Gerät(e) erreicht.`
                    : "Alle haben schon geantwortet.");
    } catch (e) { toast("Fehler: " + e.message); }
    finally { erinnern.disabled = false; }
  });
  akt.appendChild(erinnern);

  // Zweistufig statt Rueckfrage-Dialog: erst scharf machen, dann loeschen.
  const weg = document.createElement("button");
  weg.className = "loeschen";
  weg.textContent = "Termin löschen";
  let scharf = false;
  weg.addEventListener("click", () => {
    if (!scharf) {
      scharf = true;
      weg.classList.add("scharf");
      weg.textContent = "Wirklich löschen?";
      setTimeout(() => {
        if (!scharf) return;
        scharf = false; weg.classList.remove("scharf"); weg.textContent = "Termin löschen";
      }, 4000);
      return;
    }
    terminLoeschen(t);
  });
  akt.appendChild(weg);
  return akt;
}

async function terminLoeschen(t) {
  const d = datumTeile(t.datum);
  try {
    await api("/api/trainings/" + t.id + "/loeschen", "POST", {});
    terminDetails.delete(t.id);
    offeneTermine.delete(t.id);
    await Sync.frischHolen("/api/trainings").catch(() => {});
    Sync.frischHolen("/api/naechstes-training").catch(() => {});
    toast(`${d.wt} ${d.tag} gelöscht.`);
    ladeTrainingsListe();
  } catch (e) {
    toast(navigator.onLine ? ("Fehler: " + e.message)
      : "Kein Netz – Löschen braucht eine Verbindung.");
  }
}

// „Neues Training" (nur Trainer/Admin): Datum/Uhrzeit/Ort.
function renderTrainingNeu() {
  const el = document.getElementById("trainings-neu");
  if (!el) return;
  if (aktRolle !== "trainer") { el.innerHTML = ""; return; }
  el.innerHTML =
    `<button id="tn-toggle" class="tn-toggle">＋ Neues Training</button>
     <div id="tn-form" class="tn-form hidden">
       <input id="tn-datum" type="date" />
       <input id="tn-uhrzeit" type="time" />
       <input id="tn-ort" type="text" placeholder="Ort (z. B. Gerhausen)" />
       <button id="tn-speichern" class="primaer">Anlegen</button>
     </div>`;
  document.getElementById("tn-toggle").addEventListener("click", () =>
    document.getElementById("tn-form").classList.toggle("hidden"));
  document.getElementById("tn-speichern").addEventListener("click", trainingAnlegen);
}

async function trainingAnlegen() {
  const datum = document.getElementById("tn-datum").value;
  const uhrzeit = document.getElementById("tn-uhrzeit").value;
  const ort = document.getElementById("tn-ort").value.trim();
  if (!datum) { toast("Bitte ein Datum wählen."); return; }
  try {
    const r = await api("/api/trainings", "POST",
      { datum, uhrzeit, ort, titel: ort ? "Training " + ort : "Training" });
    toast(r.neu ? "Training angelegt ✓" : "Termin am Datum aktualisiert ✓");
    document.getElementById("tn-datum").value = "";
    document.getElementById("tn-uhrzeit").value = "";
    document.getElementById("tn-ort").value = "";
    document.getElementById("tn-form").classList.add("hidden");
    Sync.frischHolen("/api/trainings").catch(() => {});
    ladeTrainingsListe();
  } catch (e) { toast("Fehler: " + e.message); }
}

async function oeffneTraining(id) {
  let d = null;
  try { d = await Sync.apiOffline("/api/trainings/" + id); } catch (_) {}
  if (!d) { toast("Training nicht verfügbar (einmal online öffnen)."); return; }
  aktTraining = d;
  $("#td-titel").textContent = d.titel || (d.datum ? datumKurz(d.datum) : "Training");
  const teile = [];
  if (d.datum) teile.push(datumKurz(d.datum));
  if (d.uhrzeit) teile.push(d.uhrzeit);
  if (d.ort) teile.push(d.ort);
  $("#td-meta").textContent = teile.join(" · ");
  renderRSVP(d);
  renderTeilnahme(d);
  renderErinnern(d);
  renderTrainingPlan();
  zeigeView("view-training-detail");
}

// Zusagen/Unsicher/Abgesagt-Listen. Bei Absagen wird der Grund mit angezeigt
// (für Trainer UND Spielerinnen sichtbar).
function renderTeilnahme(d) {
  const grp = (status) => (d.teilnahme || []).filter((t) => t.status === status);
  const chip = (t, mitGrund) =>
    `<span class="td-chip">${escape(t.name)}${t.position === "Tor" ? ' <span class="tw">TW</span>' : ""}` +
    `${mitGrund && t.grund ? ` <span class="td-grund">– ${escape(t.grund)}</span>` : ""}</span>`;
  const block = (titel, kl, arr, mitGrund) => arr.length
    ? `<div class="td-grp ${kl}"><div class="td-grp-kopf">${titel} (${arr.length})</div>` +
      `<div class="td-chips">${arr.map((t) => chip(t, mitGrund)).join("")}</div></div>`
    : "";
  $("#td-teilnahme").innerHTML =
    block("Zugesagt", "an", grp("anwesend"), false) +
    block("Unsicher", "un", grp("unsicher"), false) +
    block("Abgesagt", "ab", grp("abgesagt"), true);
}

// Haeufige Absagegruende zum Antippen. Freitext bleibt daneben moeglich -
// ein leeres Feld verleitet dazu, die Absage einfach abzuschicken.
const ABSAGE_GRUENDE = ["Arbeit", "Urlaub", "Krank", "Verletzt", "Uni / Schule", "Anderer Termin"];

function renderRSVP(d) {
  const el = $("#td-rsvp");
  if (el) rsvpFuellen(el, d);
}

// Eigene Zu-/Absage. Wird an ZWEI Stellen benutzt (Termin-Detail und
// aufgeklappte Zeile in der Uebersicht), deshalb alles ueber `el` gesucht
// und nicht ueber globale IDs.
function rsvpFuellen(el, d) {
  const sid = aktBenutzer && aktBenutzer.spieler_id;
  if (!sid) { el.innerHTML = ""; return; }          // Trainer / kein Spielerprofil
  const meine = (d.teilnahme || []).find((t) => t.id === sid);
  const status = meine ? meine.status : null;
  const lab = { anwesend: "Zugesagt ✓", abgesagt: "Abgesagt", unsicher: "Unsicher" };
  const grund = (meine && meine.grund) || "";

  el.innerHTML =
    `<div class="rsvp-kopf">Deine Antwort: <b>${status ? lab[status] : "noch offen"}</b>` +
    `${status === "abgesagt" && grund ? ` – ${escape(grund)}` : ""}</div>
     <div class="rsvp-knoepfe">
       <button class="rsvp-ja${status === "anwesend" ? " aktiv" : ""}" data-s="anwesend">Zusagen</button>
       <button class="rsvp-un${status === "unsicher" ? " aktiv" : ""}" data-s="unsicher">Unsicher</button>
       <button class="rsvp-nein${status === "abgesagt" ? " aktiv" : ""}" data-s="abgesagt">Absagen</button>
     </div>
     <div class="rsvp-grund-box hidden">
       <div class="grund-chips">${ABSAGE_GRUENDE.map((g) =>
         `<button class="gchip${g === grund ? " aktiv" : ""}">${g}</button>`).join("")}</div>
       <div class="rsvp-grund-eingabe">
         <input class="rsvp-grund" type="text" maxlength="60"
                placeholder="Grund für die Absage (Pflicht)" value="${escape(grund)}" />
         <button class="rsvp-grund-senden primaer">Absage senden</button>
       </div>
     </div>`;

  const box = el.querySelector(".rsvp-grund-box");
  const feld = el.querySelector(".rsvp-grund");
  const chips = el.querySelectorAll(".gchip");

  chips.forEach((c) => c.addEventListener("click", () => {
    feld.value = c.classList.contains("aktiv") ? "" : c.textContent;
    chips.forEach((x) => x.classList.toggle("aktiv", x === c && feld.value !== ""));
  }));

  el.querySelectorAll(".rsvp-knoepfe button").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.dataset.s === "abgesagt") {              // Grund ist Pflicht -> erst fragen
        box.classList.remove("hidden");
        feld.focus({ preventScroll: true });
        return;
      }
      box.classList.add("hidden");
      rsvpSenden(b.dataset.s, null, d);
    }));

  el.querySelector(".rsvp-grund-senden").addEventListener("click", () => {
    const g = feld.value.trim();
    if (!g) { toast("Bitte einen Grund angeben – den sieht das ganze Team."); feld.focus(); return; }
    rsvpSenden("abgesagt", g, d);
  });
}

async function rsvpSenden(status, grund, d) {
  d = d || aktTraining;
  try {
    // Online-Aktion (Push/Team-Planung brauchen aktuelle Daten): direkt senden.
    await api("/api/trainings/" + d.id + "/teilnahme", "POST", { status, grund });
    const sid = aktBenutzer.spieler_id;
    d.teilnahme = d.teilnahme || [];
    let m = d.teilnahme.find((t) => t.id === sid);
    if (!m) { m = { id: sid, name: aktBenutzer.name, position: "Feld" }; d.teilnahme.push(m); }
    m.status = status; m.grund = grund; m.quelle = "app";
    terminDetails.set(d.id, d);
    toast(status === "abgesagt" ? "Abgesagt – der Grund steht jetzt beim Termin."
                                : "Antwort gespeichert ✓");
    Sync.frischHolen("/api/trainings/" + d.id).catch(() => {});
    Sync.frischHolen("/api/naechstes-training").catch(() => {});
    if (aktTraining && aktTraining.id === d.id) { renderRSVP(aktTraining); renderTeilnahme(aktTraining); }
    // Zahlen in der Uebersicht stimmen erst nach dem Nachladen der Liste.
    if (!$("#view-trainings").classList.contains("hidden")) {
      await Sync.frischHolen("/api/trainings").catch(() => {});
      ladeTrainingsListe();
    } else {
      Sync.frischHolen("/api/trainings").catch(() => {});
    }
  } catch (e) {
    toast(navigator.onLine ? ("Fehler: " + e.message)
      : "Kein Netz – bitte online zu-/absagen.");
  }
}

// Plan anzeigen. Der Plan ist NUR fuer das Trainerteam - Spielerinnen sehen
// hier gar nichts, auch keinen Hinweis darauf, dass es einen gibt.
function renderTrainingPlan() {
  const el = $("#td-plan");
  const d = aktTraining;
  if (aktRolle !== "trainer") { el.innerHTML = ""; return; }

  const bloecke = d.bloecke || [];
  const hatPlan = d.plan_markdown && d.plan_markdown.trim();
  const hatInhalt = d.inhalt && d.inhalt.trim();

  if (bloecke.length) {
    el.innerHTML = `<div class="td-plan-kopf">Trainingsplan <span class="nur-trainer">nur für Trainer</span></div>`;
    el.appendChild(planZeitstrahl(d));
    el.appendChild(planKnopf("✏️ Plan bearbeiten", () => oeffnePlanEditor(d)));
    return;
  }

  // Noch keine Bloecke: alten Text zeigen und das Umwandeln anbieten.
  if (hatPlan) el.innerHTML = `<div class="td-plan-kopf">Trainingsplan <span class="nur-trainer">nur für Trainer</span></div>` + mdLite(d.plan_markdown);
  else if (hatInhalt) el.innerHTML = `<div class="td-plan-kopf">Inhalt</div>` + mdLite(d.inhalt);
  else el.innerHTML = `<p class="hinweis">Für diese Einheit steht noch nichts.</p>`;

  if (hatPlan || hatInhalt) {
    el.appendChild(planKnopf("In Blöcke übernehmen", () => bloeckeAusText(d), "primaer"));
    el.appendChild(planKnopf("Text bearbeiten", startPlanEdit));
  } else {
    el.appendChild(planKnopf("Training aufschreiben", () => oeffnePlanEditor(d), "primaer"));
  }
}

function planKnopf(text, fn, extra) {
  const b = document.createElement("button");
  b.className = "plan-edit-btn" + (extra ? " " + extra : "");
  b.textContent = text;
  b.addEventListener("click", fn);
  return b;
}

// Alten Plantext serverseitig in Bloecke zerlegen (jede Ueberschrift ein Block).
async function bloeckeAusText(d) {
  try {
    const r = await api("/api/trainings/" + d.id + "/blocks/aus-text", "POST");
    d.bloecke = r.bloecke || [];
    await patchBloeckeCache(d.id, d.bloecke);
    renderTrainingPlan();
    toast(`${d.bloecke.length} Blöcke angelegt – jetzt kannst du Zeiten ergänzen.`);
  } catch (e) {
    toast(navigator.onLine ? ("Fehler: " + e.message)
      : "Kein Netz – das Umwandeln braucht eine Verbindung.");
  }
}

function startPlanEdit() {
  const el = $("#td-plan");
  const ta = document.createElement("textarea");
  ta.className = "plan-editor";
  ta.value = aktTraining.plan_markdown || "";
  ta.rows = 14;
  ta.placeholder = "Trainingsplan (Markdown: # Überschrift, - Liste, **fett**) …";
  const leiste = document.createElement("div");
  leiste.className = "plan-edit-leiste";
  const speichern = document.createElement("button");
  speichern.className = "primaer"; speichern.textContent = "Speichern";
  speichern.addEventListener("click", () => savePlan(ta.value));
  const abbrechen = document.createElement("button");
  abbrechen.textContent = "Abbrechen";
  abbrechen.addEventListener("click", renderTrainingPlan);
  leiste.appendChild(speichern); leiste.appendChild(abbrechen);
  el.innerHTML = `<div class="td-plan-kopf">Plan bearbeiten</div>`;
  el.appendChild(ta); el.appendChild(leiste);
  ta.focus();
}

async function savePlan(markdown) {
  const d = aktTraining;
  try {
    // Immer über die Outbox: online sofort, offline gepuffert (Token dedupliziert).
    const r = await Sync.senden("/api/trainings/" + d.id + "/plan", { markdown });
    d.plan_markdown = markdown;                 // optimistisch lokal
    await patchTrainingCache(d.id, markdown);   // GET-Cache konsistent halten
    renderTrainingPlan();
    toast(r.gesendet ? "Plan gespeichert ✓"
      : "Offline gespeichert – wird im WLAN synchronisiert.");
  } catch (e) { toast("Fehler: " + e.message); }
}

// Den gespiegelten GET-Cache mitziehen, damit die Änderung auch offline sofort
// stimmt (Detail-Plan + hat_plan in der Liste).
async function patchTrainingCache(id, markdown) {
  const gesetzt = !!(markdown && markdown.trim());
  try {
    const detail = await LocalDB.get("responses", "/api/trainings/" + id);
    if (detail && detail.daten) {
      detail.daten.plan_markdown = markdown;
      await LocalDB.put("responses", { pfad: "/api/trainings/" + id, daten: detail.daten, ts: Date.now() });
    }
    const liste = await LocalDB.get("responses", "/api/trainings");
    if (liste && Array.isArray(liste.daten)) {
      const t = liste.daten.find((x) => x.id === id);
      if (t) { t.hat_plan = gesetzt ? 1 : 0;
        await LocalDB.put("responses", { pfad: "/api/trainings", daten: liste.daten, ts: Date.now() }); }
    }
  } catch (_) { /* Cache-Patch ist best-effort */ }
}

$("#btn-training-zurueck").addEventListener("click", () => gehe("training", "trainings"));
$("#btn-plan-zurueck").addEventListener("click", planVerlassen);

// ================================================ Trainingsplan in Bloecken ==
//  "Wann mache ich was": Bloecke mit optionaler Dauer. Aus den Dauern rechnet
//  die App die Uhrzeiten - man plant in Minuten, denkt aber in Uhrzeiten.
//  Alles hier ist NUR fuer Trainer; jede Stelle prueft die Rolle selbst.

let planTraining = null;       // Training-Detail, das gerade bearbeitet wird
let planBloecke = [];          // Arbeitskopie der Bloecke
let planTimer = null;          // Entprellung fuer Tipp-Aenderungen
let planUebungen = null;       // Titel aus der Uebungssammlung (einmal geladen)
let planChipsOffen = false;

function zeitZuMinuten(z) {
  const m = /^(\d{1,2}):(\d{2})/.exec(z || "");
  return m ? (+m[1]) * 60 + (+m[2]) : null;
}
function minutenZuZeit(m) {
  return String(Math.floor(m / 60) % 24).padStart(2, "0") + ":" +
         String(Math.round(m) % 60).padStart(2, "0");
}
const planSumme = (b) => (b || []).reduce((s, x) => s + (Number(x.dauer_min) || 0), 0);

// Nur-Lesen-Ansicht: Uhrzeit, was, wie lange.
function planZeitstrahl(d) {
  const box = document.createElement("div");
  box.className = "zeitstrahl";
  let t = zeitZuMinuten(d.uhrzeit);
  for (const b of d.bloecke || []) {
    const dauer = Number(b.dauer_min) || 0;
    const zeile = document.createElement("div");
    zeile.className = "zs-zeile";
    zeile.innerHTML =
      `<span class="zs-uhr">${t != null && dauer ? minutenZuZeit(t) : ""}</span>
       <span class="zs-txt"><b>${escape(b.titel || "Ohne Titel")}</b>` +
      `${b.notiz ? `<small>${escape(b.notiz)}</small>` : ""}</span>
       <span class="zs-dauer">${dauer ? dauer + "′" : ""}</span>`;
    box.appendChild(zeile);
    if (t != null && dauer) t += dauer;
  }
  return box;
}

function oeffnePlanEditor(d) {
  if (aktRolle !== "trainer") return;
  planTraining = d;
  planBloecke = (d.bloecke || []).map((b) =>
    ({ dauer_min: b.dauer_min, titel: b.titel || "", notiz: b.notiz || "" }));
  planChipsOffen = false;
  renderPlanSeite();
  zeigeView("view-plan");
}

function renderPlanSeite() {
  const d = planTraining;
  if (!d) return;
  const dt = datumTeile(d.datum);
  $("#plan-titel").textContent = "Training aufschreiben";
  $("#plan-meta").innerHTML =
    `${dt.wt} ${escape(dt.tag)}${d.uhrzeit ? " · ab " + escape(d.uhrzeit) : ""}` +
    `${d.titel ? " · " + escape(d.titel) : ""} <span class="nur-trainer">nur für Trainer</span>`;

  renderPlanBilanz();
  renderPlanBloecke();
  renderPlanWerkzeug();
}

function renderPlanBilanz() {
  const d = planTraining;
  const summe = planSumme(planBloecke);
  const start = zeitZuMinuten(d.uhrzeit);
  const ohne = planBloecke.filter((b) => !Number(b.dauer_min)).length;
  const el = $("#plan-bilanz");
  el.className = "plan-bilanz";
  el.innerHTML =
    `<div class="pz"><b>${summe}</b><span>Minuten geplant · ${planBloecke.length} ` +
    `${planBloecke.length === 1 ? "Block" : "Blöcke"}</span></div>` +
    `<div class="prest">` +
    (start != null && summe
      ? `Beginn ${escape(d.uhrzeit)} · Ende ${minutenZuZeit(start + summe)}`
      : start != null ? `Beginn ${escape(d.uhrzeit)} – noch keine Dauer eingetragen`
      : `Ohne Uhrzeit am Termin gibt es keine Uhrzeiten im Plan.`) +
    (ohne ? ` · ${ohne} ohne Dauer` : "") +
    `</div><div class="plan-status" id="plan-status"></div>`;
}

function renderPlanBloecke() {
  const el = $("#plan-bloecke");
  el.innerHTML = "";
  if (!planBloecke.length) {
    el.innerHTML = `<div class="plan-leer"><p>Noch kein Block. Fang mit dem Einlaufen an.</p></div>`;
    return;
  }
  let t = zeitZuMinuten(planTraining.uhrzeit);
  planBloecke.forEach((b, i) => {
    const dauer = Number(b.dauer_min) || 0;
    const k = document.createElement("div");
    k.className = "block";

    const oben = document.createElement("div");
    oben.className = "block-oben";
    oben.innerHTML = `<span class="b-uhr">${t != null && dauer ? minutenZuZeit(t) : "—"}</span>`;

    const dau = document.createElement("input");
    dau.className = "b-dauer"; dau.type = "number"; dau.min = "1"; dau.max = "300";
    dau.inputMode = "numeric"; dau.placeholder = "–";
    dau.value = dauer || "";
    dau.setAttribute("aria-label", "Dauer in Minuten");
    dau.addEventListener("input", () => {
      b.dauer_min = dau.value === "" ? null : (parseInt(dau.value, 10) || null);
      renderPlanBilanz();
      planUhrzeitenAuffrischen();
      planSpaeterSpeichern();
    });
    oben.appendChild(dau);
    oben.appendChild(el2("span", "b-min", "Min."));

    const wz = document.createElement("div");
    wz.className = "b-werkzeug";
    wz.appendChild(werkzeug("↑", "Nach oben", i === 0, () => planTauschen(i, i - 1)));
    wz.appendChild(werkzeug("↓", "Nach unten", i === planBloecke.length - 1, () => planTauschen(i, i + 1)));
    wz.appendChild(werkzeug("✕", "Block löschen", false, () => planBlockWeg(i), "weg"));
    oben.appendChild(wz);
    k.appendChild(oben);

    const ti = document.createElement("input");
    ti.className = "b-titel"; ti.type = "text"; ti.maxLength = 120;
    ti.value = b.titel || ""; ti.placeholder = "Was wird gemacht?";
    ti.setAttribute("aria-label", "Titel des Blocks");
    ti.addEventListener("input", () => { b.titel = ti.value; planSpaeterSpeichern(); });
    k.appendChild(ti);

    const no = document.createElement("input");
    no.className = "b-notiz"; no.type = "text"; no.maxLength = 500;
    no.value = b.notiz || ""; no.placeholder = "Notiz – Aufbau, Variante, worauf achten";
    no.setAttribute("aria-label", "Notiz");
    no.addEventListener("input", () => { b.notiz = no.value; planSpaeterSpeichern(); });
    k.appendChild(no);

    el.appendChild(k);
    if (t != null && dauer) t += dauer;
  });
}

function el2(tag, klasse, text) {
  const e = document.createElement(tag);
  e.className = klasse; e.textContent = text;
  return e;
}
function werkzeug(zeichen, titel, aus, fn, extra) {
  const b = document.createElement("button");
  b.textContent = zeichen; b.title = titel; b.disabled = !!aus;
  if (extra) b.className = extra;
  b.addEventListener("click", fn);
  return b;
}

// Uhrzeiten nachziehen, ohne die Eingabefelder neu zu bauen (sonst springt
// der Cursor beim Tippen aus dem Minutenfeld).
function planUhrzeitenAuffrischen() {
  let t = zeitZuMinuten(planTraining.uhrzeit);
  document.querySelectorAll("#plan-bloecke .b-uhr").forEach((e, i) => {
    const dauer = Number((planBloecke[i] || {}).dauer_min) || 0;
    e.textContent = t != null && dauer ? minutenZuZeit(t) : "—";
    if (t != null && dauer) t += dauer;
  });
}

function planTauschen(a, b) {
  if (b < 0 || b >= planBloecke.length) return;
  const x = planBloecke[a]; planBloecke[a] = planBloecke[b]; planBloecke[b] = x;
  renderPlanSeite(); planJetztSpeichern();
}

function planBlockWeg(i) {
  const raus = planBloecke.splice(i, 1)[0];
  renderPlanSeite(); planJetztSpeichern();
  toast(`„${raus.titel || "Block"}" entfernt.`);
}

function planBlockNeu(titel, dauer) {
  planBloecke.push({ dauer_min: dauer || null, titel: titel || "", notiz: "" });
  renderPlanSeite(); planJetztSpeichern();
  const felder = document.querySelectorAll("#plan-bloecke .b-titel");
  if (felder.length && !titel) felder[felder.length - 1].focus();
}

function renderPlanWerkzeug() {
  const el = $("#plan-werkzeug");
  el.innerHTML = "";

  const neu = document.createElement("button");
  neu.className = "knopf-plan primaer";
  neu.textContent = "＋ Block hinzufügen";
  neu.addEventListener("click", () => planBlockNeu());
  el.appendChild(neu);

  const auf = document.createElement("button");
  auf.className = "knopf-plan";
  auf.textContent = (planChipsOffen ? "▾ " : "▸ ") + "Aus der Übungssammlung";
  auf.addEventListener("click", async () => {
    planChipsOffen = !planChipsOffen;
    if (planChipsOffen) await ladePlanUebungen();
    renderPlanWerkzeug();
  });
  el.appendChild(auf);

  if (planChipsOffen) {
    const box = document.createElement("div");
    box.className = "uebung-chips";
    if (planUebungen === null) box.innerHTML = '<p class="hinweis">Lädt…</p>';
    else if (!planUebungen.length) box.innerHTML = '<p class="hinweis">Keine Übungen gefunden.</p>';
    else planUebungen.forEach((name) => {
      const c = document.createElement("button");
      c.className = "uchip"; c.textContent = "＋ " + name;
      c.addEventListener("click", () => { planBlockNeu(name, 20); toast(`„${name}" angehängt.`); });
      box.appendChild(c);
    });
    el.appendChild(box);
  }

  const fertig = document.createElement("button");
  fertig.className = "knopf-plan";
  fertig.textContent = "Fertig";
  fertig.addEventListener("click", planVerlassen);
  el.appendChild(fertig);
}

async function ladePlanUebungen() {
  if (planUebungen !== null) return;
  try {
    const seiten = await Sync.apiOffline("/api/seiten?kategorie=uebung");
    const namen = (seiten || []).map((s) => (s.titel || "").trim()).filter(Boolean);
    planUebungen = [...new Set(namen)].sort((a, b) => a.localeCompare(b, "de"));
  } catch (_) { planUebungen = []; }
}

// -------------------------------------------------------------- Speichern ---
function planStatus(text) {
  const el = document.getElementById("plan-status");
  if (el) el.textContent = text || "";
}

function planSpaeterSpeichern() {
  planStatus("ändert…");
  clearTimeout(planTimer);
  planTimer = setTimeout(planJetztSpeichern, 900);
}

async function planJetztSpeichern() {
  clearTimeout(planTimer);
  const d = planTraining;
  if (!d) return;
  const bloecke = planBloecke.map((b) => ({
    dauer_min: Number(b.dauer_min) || null,
    titel: (b.titel || "").trim(),
    notiz: (b.notiz || "").trim() || null,
  }));
  planStatus("speichert…");
  try {
    // Ueber die Outbox: online sofort, offline gepuffert. Der Endpunkt ersetzt
    // den ganzen Plan, ein wiederholter Versuch verdoppelt also nichts.
    const r = await Sync.senden("/api/trainings/" + d.id + "/blocks", { bloecke });
    d.bloecke = bloecke;
    await patchBloeckeCache(d.id, bloecke);
    planStatus(r.gesendet ? "gespeichert ✓" : "offline gespeichert – wird synchronisiert");
  } catch (e) {
    planStatus("nicht gespeichert: " + e.message);
  }
}

// GET-Cache mitziehen, damit der Plan auch offline sofort stimmt.
async function patchBloeckeCache(id, bloecke) {
  try {
    const detail = await LocalDB.get("responses", "/api/trainings/" + id);
    if (detail && detail.daten) {
      detail.daten.bloecke = bloecke;
      await LocalDB.put("responses",
        { pfad: "/api/trainings/" + id, daten: detail.daten, ts: Date.now() });
    }
    const liste = await LocalDB.get("responses", "/api/trainings");
    if (liste && Array.isArray(liste.daten)) {
      const t = liste.daten.find((x) => x.id === id);
      if (t) {
        t.hat_plan = bloecke.length ? 1 : t.hat_plan;
        t.plan_minuten = planSumme(bloecke);
        await LocalDB.put("responses", { pfad: "/api/trainings", daten: liste.daten, ts: Date.now() });
      }
    }
    terminDetails.delete(id);      // Namen/Plan beim naechsten Aufklappen frisch
  } catch (_) { /* Cache ist Beiwerk */ }
}

async function planVerlassen() {
  await planJetztSpeichern();
  if (aktTraining && planTraining && aktTraining.id === planTraining.id) {
    aktTraining.bloecke = planTraining.bloecke;
    renderTrainingPlan();
    zeigeView("view-training-detail");
  } else {
    gehe("training", "trainings");
  }
}

// -------------------------------------------------------------- Wiki/Seiten --
//  Eine Ansicht für alle Freitext-Bereiche (Playbook/Gegner/Übungen/Statistik/
//  Saison/Notizen). `kat` ist eine Kategorie oder eine Liste von Kategorien.
//
//  BAUM: Seiten mit `parent_id` erscheinen eingerückt unter ihrer Gruppe, in
//  beliebiger Tiefe (Playbook: Spielzüge > Allgemeine Spielzüge > Jugo).
//  Reihenfolge kommt aus `sortierung`, bei Gleichstand alphabetisch.
//  Trainer können Seiten hier anlegen, bearbeiten und löschen.

const WIKI_MAX_TIEFE = 6;          // Reissleine gegen kaputte parent_id-Ketten

let aktWikiKats = [];              // Kategorien der aktuellen Liste
let aktWikiTitel = "";
let aktWikiSeiten = [];            // zuletzt geladene Liste (für das Anlege-Formular)
let aktSeite = null;               // aktuell geöffnete Wiki-Seite

// Zugeklappte Gruppen überleben den Neustart der App (sonst klappt jede
// Sitzung wieder alles auf).
const wikiZugeklappt = new Set((() => {
  try { return JSON.parse(localStorage.getItem("wikiZugeklappt") || "[]"); }
  catch (_) { return []; }
})());

function merkeZugeklappt() {
  try {
    localStorage.setItem("wikiZugeklappt", JSON.stringify([...wikiZugeklappt]));
  } catch (_) { /* privater Modus o. ä. — dann eben nur für diese Sitzung */ }
}

async function ladeWiki(kat, titel) {
  aktWikiKats = Array.isArray(kat) ? kat.slice() : [kat];
  aktWikiTitel = titel || "Wiki";
  $("#wiki-titel").textContent = aktWikiTitel;
  renderWikiNeu();
  const el = $("#wiki-liste");
  el.innerHTML = '<p class="hinweis">Lädt…</p>';
  const teile = await Promise.all(aktWikiKats.map((k) =>
    Sync.apiOffline("/api/seiten?kategorie=" + encodeURIComponent(k)).catch(() => [])));
  aktWikiSeiten = teile.flat();
  renderWikiListe();
}

// Baum aus der flachen Liste: alles mit gültigem parent_id wird Kind, der Rest
// steht oben. Beide Ebenen sind nach `sortierung` sortiert.
function wikiBaum() {
  const vorhanden = new Set(aktWikiSeiten.map((s) => s.id));
  const kinder = new Map();
  const oben = [];
  for (const s of aktWikiSeiten) {
    if (s.parent_id && vorhanden.has(s.parent_id)) {
      if (!kinder.has(s.parent_id)) kinder.set(s.parent_id, []);
      kinder.get(s.parent_id).push(s);
    } else {
      oben.push(s);
    }
  }
  const sortiere = (a, b) => (a.sortierung || 0) - (b.sortierung || 0) ||
    (a.titel || "").localeCompare(b.titel || "", "de");
  oben.sort(sortiere);
  for (const liste of kinder.values()) liste.sort(sortiere);
  return { oben, kinder };
}

function renderWikiListe() {
  const el = $("#wiki-liste");
  if (!aktWikiSeiten.length) {
    el.innerHTML = '<p class="hinweis">Noch keine Einträge.</p>';
    return;
  }
  const { oben, kinder } = wikiBaum();
  el.innerHTML = "";
  for (const s of oben) el.appendChild(wikiKnoten(s, kinder, 0));
}

// Eine Seite samt allem, was unter ihr hängt: ohne Kinder eine Zeile, mit
// Kindern eine aufklappbare Gruppe.
function wikiKnoten(s, kinder, tiefe) {
  const ks = tiefe < WIKI_MAX_TIEFE ? (kinder.get(s.id) || []) : [];
  return ks.length ? wikiGruppe(s, ks, kinder, tiefe)
                   : wikiZeile(s, tiefe ? "kind" : "");
}

// Eine normale Seitenzeile. Leere Seiten sind für Spielerinnen nicht anklickbar,
// für Trainer schon (dort wird der Inhalt ja erst geschrieben).
function wikiZeile(s, extraKlasse) {
  const z = document.createElement("button");
  z.className = "wiki-zeile" + (s.hat_inhalt ? "" : " leer") +
    (extraKlasse ? " " + extraKlasse : "");
  z.innerHTML = `<span class="wz-titel">${escape(s.titel)}</span>` +
    (s.hat_inhalt ? '<span class="wz-pfeil">›</span>' : '<span class="wz-leer">leer</span>');
  if (s.hat_inhalt || aktRolle === "trainer") {
    z.addEventListener("click", () => oeffneSeite(s.id));
  }
  return z;
}

// Gruppenkopf + eingerückte Unterseiten. Der Kopf klappt auf/zu; das „›"
// daneben öffnet die Gruppenseite selbst (Text direkt an der Gruppe).
function wikiGruppe(g, ks, kinder, tiefe) {
  const zu = wikiZugeklappt.has(g.id);
  const box = document.createElement("div");
  box.className = "wiki-gruppe";

  const kinderBox = document.createElement("div");
  kinderBox.className = "wiki-kinder" + (zu ? " hidden" : "");
  for (const k of ks) kinderBox.appendChild(wikiKnoten(k, kinder, tiefe + 1));

  const kopf = document.createElement("div");
  kopf.className = "wiki-zeile gruppe" + (tiefe ? " kind" : "");
  const toggle = document.createElement("button");
  toggle.className = "wz-toggle";
  toggle.setAttribute("aria-expanded", zu ? "false" : "true");
  toggle.innerHTML = `<span class="wz-caret">${zu ? "▸" : "▾"}</span>` +
    `<span class="wz-titel">${escape(g.titel)}</span>` +
    `<span class="wz-anzahl">${ks.length}</span>`;
  toggle.addEventListener("click", () => {
    const jetztZu = !wikiZugeklappt.has(g.id);
    if (jetztZu) wikiZugeklappt.add(g.id); else wikiZugeklappt.delete(g.id);
    merkeZugeklappt();
    kinderBox.classList.toggle("hidden", jetztZu);
    toggle.setAttribute("aria-expanded", jetztZu ? "false" : "true");
    toggle.querySelector(".wz-caret").textContent = jetztZu ? "▸" : "▾";
  });
  kopf.appendChild(toggle);
  if (g.hat_inhalt || aktRolle === "trainer") {
    const auf = document.createElement("button");
    auf.className = "wz-open";
    auf.textContent = "›";
    auf.title = "Gruppenseite öffnen";
    auf.addEventListener("click", () => oeffneSeite(g.id));
    kopf.appendChild(auf);
  }

  box.appendChild(kopf);
  box.appendChild(kinderBox);
  return box;
}

// ------------------------------------------------- Seiten anlegen (Trainer) --
function renderWikiNeu() {
  const el = $("#wiki-neu");
  if (!el) return;
  el.innerHTML = "";
  if (aktRolle !== "trainer") return;
  const btn = document.createElement("button");
  btn.className = "wiki-neu-btn";
  btn.textContent = "＋ Neue Seite";
  btn.addEventListener("click", zeigeWikiNeuForm);
  el.appendChild(btn);
}

function zeigeWikiNeuForm() {
  const el = $("#wiki-neu");
  el.innerHTML = "";
  const form = document.createElement("div");
  form.className = "wiki-neu-form";

  const titel = document.createElement("input");
  titel.type = "text";
  titel.placeholder = "Titel der neuen Seite";

  // Ziel: oberste Ebene je Kategorie oder als Unterseite einer Seite dieser
  // Ebene. Der Wert kodiert beides: "kat:<kategorie>" oder "unter:<id>".
  const ziel = document.createElement("select");
  for (const k of aktWikiKats) {
    const o = document.createElement("option");
    o.value = "kat:" + k;
    o.textContent = aktWikiKats.length > 1 ? `Oberste Ebene (${k})` : "Oberste Ebene";
    ziel.appendChild(o);
  }
  // Jede Seite kann Gruppe werden; die Einrückung zeigt, wo sie im Baum hängt.
  const { oben, kinder } = wikiBaum();
  (function sammle(liste, tiefe) {
    for (const s of liste) {
      const o = document.createElement("option");
      o.value = "unter:" + s.id;
      o.textContent = "Unter " + "· ".repeat(tiefe) + "„" + s.titel + "“";
      ziel.appendChild(o);
      if (tiefe + 1 < WIKI_MAX_TIEFE) sammle(kinder.get(s.id) || [], tiefe + 1);
    }
  })(oben, 0);

  const leiste = document.createElement("div");
  leiste.className = "plan-edit-leiste";
  const anlegen = document.createElement("button");
  anlegen.className = "primaer";
  anlegen.textContent = "Anlegen";
  anlegen.addEventListener("click", () => {
    const [art, wert] = ziel.value.split(":");
    const parent = art === "unter" ? Number(wert) : null;
    const kategorie = art === "unter"
      ? (aktWikiSeiten.find((s) => s.id === parent) || {}).kategorie
      : wert;
    wikiSeiteAnlegen(titel.value, parent, kategorie);
  });
  const abbrechen = document.createElement("button");
  abbrechen.textContent = "Abbrechen";
  abbrechen.addEventListener("click", renderWikiNeu);
  leiste.appendChild(anlegen); leiste.appendChild(abbrechen);

  form.appendChild(titel); form.appendChild(ziel); form.appendChild(leiste);
  el.appendChild(form);
  titel.focus();
}

// Anlegen und Löschen brauchen die vom Server vergebene ID bzw. verändern die
// Struktur -> bewusst NICHT über die Outbox, sondern nur online.
async function wikiSeiteAnlegen(titel, parentId, kategorie) {
  titel = (titel || "").trim();
  if (!titel) { toast("Bitte einen Titel eingeben."); return; }
  if (!Sync.serverOnline) { toast("Neue Seiten gehen nur online."); return; }
  try {
    const r = await api("/api/seiten", "POST",
                        { titel, kategorie, parent_id: parentId });
    await Sync.frischHolen("/api/seiten?kategorie=" + encodeURIComponent(kategorie));
    await ladeWiki(aktWikiKats, aktWikiTitel);
    toast("Seite angelegt ✓");
    if (r && r.id) oeffneSeite(r.id);
  } catch (e) { toast("Fehler: " + e.message); }
}

// ------------------------------------------------------------ Seiten-Detail --
async function oeffneSeite(id) {
  let s = null;
  try { s = await Sync.apiOffline("/api/seiten/" + id); } catch (_) {}
  if (!s) { toast("Seite nicht verfügbar (einmal online öffnen)."); return; }
  aktSeite = s;
  renderSeite();
  zeigeView("view-wiki-detail");
}

function renderSeite() {
  const s = aktSeite;
  $("#wd-titel").textContent = s.titel;
  $("#wd-body").innerHTML = s.markdown ? mdLite(s.markdown)
    : '<p class="hinweis">Diese Seite ist leer.</p>';
  const akt = $("#wd-aktionen");
  akt.innerHTML = "";
  if (aktRolle !== "trainer") return;
  const bearbeiten = document.createElement("button");
  bearbeiten.className = "plan-edit-btn";
  bearbeiten.textContent = s.markdown ? "✏️ Bearbeiten" : "✏️ Inhalt hinzufügen";
  bearbeiten.addEventListener("click", startSeiteEdit);
  const loeschen = document.createElement("button");
  loeschen.className = "plan-edit-btn gefahr";
  loeschen.textContent = "🗑 Löschen";
  loeschen.addEventListener("click", loescheSeite);
  akt.appendChild(bearbeiten); akt.appendChild(loeschen);
}

function startSeiteEdit() {
  const s = aktSeite;
  $("#wd-body").innerHTML = "";
  const box = $("#wd-aktionen");
  box.innerHTML = "";
  const titel = document.createElement("input");
  titel.type = "text";
  titel.className = "wd-titel-editor";
  titel.value = s.titel;
  titel.placeholder = "Titel";
  const ta = document.createElement("textarea");
  ta.className = "plan-editor";
  ta.rows = 16;
  ta.value = s.markdown || "";
  ta.placeholder = "Inhalt (Markdown: ## Überschrift, - Liste, **fett**) …";
  const leiste = document.createElement("div");
  leiste.className = "plan-edit-leiste";
  const speichern = document.createElement("button");
  speichern.className = "primaer";
  speichern.textContent = "Speichern";
  speichern.addEventListener("click", () => speichereSeite(titel.value, ta.value));
  const abbrechen = document.createElement("button");
  abbrechen.textContent = "Abbrechen";
  abbrechen.addEventListener("click", renderSeite);
  leiste.appendChild(speichern); leiste.appendChild(abbrechen);
  box.appendChild(titel); box.appendChild(ta); box.appendChild(leiste);
  ta.focus();
}

async function speichereSeite(titel, markdown) {
  titel = (titel || "").trim();
  if (!titel) { toast("Der Titel darf nicht leer sein."); return; }
  const s = aktSeite;
  try {
    // Wie beim Trainingsplan über die Outbox: online sofort, offline gepuffert.
    const r = await Sync.senden("/api/seiten/" + s.id, { titel, markdown });
    s.titel = titel; s.markdown = markdown;   // optimistisch lokal
    await patchSeiteCache(s);
    renderSeite();
    toast(r.gesendet ? "Seite gespeichert ✓"
      : "Offline gespeichert – wird im WLAN synchronisiert.");
  } catch (e) { toast("Fehler: " + e.message); }
}

// Den gespiegelten GET-Cache mitziehen (Detail + Titel/„leer" in der Liste).
async function patchSeiteCache(s) {
  try {
    await LocalDB.put("responses", { pfad: "/api/seiten/" + s.id, daten: s, ts: Date.now() });
    const pfad = "/api/seiten?kategorie=" + encodeURIComponent(s.kategorie);
    const liste = await LocalDB.get("responses", pfad);
    if (liste && Array.isArray(liste.daten)) {
      const e = liste.daten.find((x) => x.id === s.id);
      if (e) {
        e.titel = s.titel;
        e.hat_inhalt = (s.markdown && s.markdown.trim()) ? 1 : 0;
        await LocalDB.put("responses", { pfad, daten: liste.daten, ts: Date.now() });
      }
    }
  } catch (_) { /* Cache-Patch ist best-effort */ }
}

async function loescheSeite() {
  const s = aktSeite;
  if (!confirm(`„${s.titel}“ wirklich löschen? Unterseiten bleiben erhalten.`)) return;
  if (!Sync.serverOnline) { toast("Löschen geht nur online."); return; }
  try {
    await api("/api/seiten/" + s.id + "/loeschen", "POST", {});
    try { await LocalDB.loesche("responses", "/api/seiten/" + s.id); } catch (_) {}
    await Sync.frischHolen("/api/seiten?kategorie=" + encodeURIComponent(s.kategorie));
    toast("Seite gelöscht ✓");
    gehe(aktOber, aktUnter);
  } catch (e) { toast("Fehler: " + e.message); }
}

$("#btn-wiki-zurueck").addEventListener("click", () => gehe(aktOber, aktUnter));

// Leichtgewichtiges Markdown -> HTML (kein externes Lib, CSP-/offline-sicher).
// Deckt Überschriften, Listen, GFM-Tabellen, fett/kursiv/Code ab. Anytype-
// interne Bild-URLs (127.0.0.1) werden entfernt, weil sie ohne Anytype brechen.
function mdLite(md) {
  if (!md) return "";
  md = md.replace(/!\[[^\]]*\]\((?:https?:\/\/127\.0\.0\.1:\d+|blob:)[^)]*\)/g, "");
  md = md.replace(/<br\s*\/?>/gi, " ");   // Anytype-Artefakt in Tabellenzellen
  const inline = (t) => escape(t)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  // Zellen einer Tabellenzeile: führendes/abschließendes | weg, an | trennen.
  const zellen = (zeile) => zeile.replace(/^\s*\|/, "").replace(/\|\s*$/, "")
    .split("|").map((c) => c.trim());
  const istTrenner = (z) => /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(z) && z.includes("-");

  const zeilen = md.split(/\r?\n/);
  let html = "", liste = null;
  const schliesse = () => { if (liste) { html += "</" + liste + ">"; liste = null; } };
  for (let i = 0; i < zeilen.length; i++) {
    const t = zeilen[i].trim();
    if (!t) { schliesse(); continue; }

    // GFM-Tabelle: Kopfzeile mit | und darunter eine Trennerzeile.
    if (t.startsWith("|") && i + 1 < zeilen.length && istTrenner(zeilen[i + 1])) {
      schliesse();
      const kopf = zellen(t);
      let tab = "<table><thead><tr>" +
        kopf.map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
      i += 2; // Kopf + Trenner überspringen
      while (i < zeilen.length && zeilen[i].trim().startsWith("|")) {
        const zs = zellen(zeilen[i].trim());
        tab += "<tr>" + zs.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
        i++;
      }
      i--; // die for-Schleife erhöht gleich wieder
      html += tab + "</tbody></table>";
      continue;
    }

    let m;
    if ((m = t.match(/^(#{1,4})\s+(.*)$/))) {
      schliesse(); const n = Math.min(m[1].length + 2, 6);
      html += `<h${n}>${inline(m[2])}</h${n}>`;
    } else if ((m = t.match(/^[-*]\s+(.*)$/))) {
      if (liste !== "ul") { schliesse(); html += "<ul>"; liste = "ul"; }
      html += `<li>${inline(m[1])}</li>`;
    } else if ((m = t.match(/^\d+\.\s+(.*)$/))) {
      if (liste !== "ol") { schliesse(); html += "<ol>"; liste = "ol"; }
      html += `<li>${inline(m[1])}</li>`;
    } else {
      schliesse(); html += `<p>${inline(t)}</p>`;
    }
  }
  schliesse();
  return html;
}

// ----------------------------------------------------------- Anwesenheit ----
async function ladeSpieler() {
  // erst gecachten Stand zeigen (auch offline sofort), dann online aktualisieren
  const cached = await Sync.spiegelRoh("/api/spieler");
  if (cached) { spielerAlle = cached; renderAnwesenheit(); }
  const frisch = await Sync.frischHolen("/api/spieler");
  if (frisch) { spielerAlle = frisch; renderAnwesenheit(); }
}

function renderAnwesenheit() {
  const el = $("#anwesenheit-liste");
  el.innerHTML = "";
  if (spielerAlle.length === 0) {
    el.innerHTML = '<p class="hinweis">Noch keine Spielerinnen. Lege sie im Tab „Kader" an.</p>';
    return;
  }
  for (const s of spielerAlle) {
    const zeile = document.createElement("label");
    zeile.className = "spieler-zeile" + (anwesend.has(s.id) ? " gewaehlt" : "");
    zeile.innerHTML = `
      <input type="checkbox" ${anwesend.has(s.id) ? "checked" : ""}>
      <span class="name">${escape(s.name)}</span>
      <span class="meta">${s.position === "Tor" ? "Tor · " : ""}ELO ${s.elo}</span>`;
    zeile.querySelector("input").addEventListener("change", (e) => {
      if (e.target.checked) anwesend.add(s.id); else anwesend.delete(s.id);
      zeile.classList.toggle("gewaehlt", e.target.checked);
    });
    el.appendChild(zeile);
  }
}

$("#btn-generieren").addEventListener("click", () => {
  // Team-Einteilung laeuft LOKAL (teams-local.js) -> funktioniert offline.
  const anwesendeSpieler = spielerAlle.filter((p) => anwesend.has(p.id));
  if (anwesendeSpieler.length < 2) { toast("Mindestens zwei Spielerinnen auswählen."); return; }
  teamsNeuBilden(anwesendeSpieler);
  renderTeams();
  zeigeView("view-teams");
});

async function ladeTrainings() {
  const sel = $("#training-auswahl");
  sel.innerHTML = '<option value="">— manuell auswählen —</option>';
  try {
    trainingsListe = await Sync.apiOffline("/api/anytype/trainings");
  } catch (e) {
    trainingsListe = [];          // Anytype nicht erreichbar -> nur manuell
    return;
  }
  for (const t of trainingsListe) {
    const o = document.createElement("option");
    o.value = t.id;
    o.textContent = `${t.label} · ${t.spieler_ids.length} zugesagt`;
    sel.appendChild(o);
  }
}

$("#training-auswahl").addEventListener("change", (e) => {
  const t = trainingsListe.find((x) => x.id === e.target.value);
  if (!t) return;
  anwesend.clear();
  t.spieler_ids.forEach((id) => anwesend.add(id));
  renderAnwesenheit();
  const fehlend = t.anwesend_gesamt - t.spieler_ids.length;
  toast(fehlend > 0
    ? `${t.spieler_ids.length} übernommen · ${fehlend} nicht im Kader`
    : `${t.spieler_ids.length} Spielerinnen übernommen`);
});

// ------------------------------------------------------------------ Teams ----
//  Erwaermungsspiele laufen mal mit zwei, mal mit vier Teams. Die Teams heissen
//  nach ihren Leibchen - so ruft man sie in der Halle auch auf.

const TEAM_FARBEN = [
  { k: "A", name: "Blau",  farbe: "var(--court)",   text: "#03212F" },
  { k: "B", name: "Ocker", farbe: "var(--ocker)",   text: "#231204" },
  { k: "C", name: "Weiß",  farbe: "#E7ECF2",        text: "#0E1C33" },
  { k: "D", name: "Grün",  farbe: "#7FC5A8",        text: "#08281C" },
];

function teamAnzahlSetzen(n) {
  teamAnzahl = Math.max(2, Math.min(Number(n) || 2, 4));
  try { localStorage.setItem("team-anzahl", String(teamAnzahl)); } catch (_) {}
}
function teamAnzahlLaden() {
  try { teamAnzahlSetzen(localStorage.getItem("team-anzahl")); } catch (_) {}
}

function teamsNeuBilden(spieler) {
  teamListe = TeamsLokal.generiereN(spieler, teamAnzahl);
  neuerSpielToken();
}

function renderTeams() {
  const wrap = $("#teams-wrap");
  wrap.innerHTML = "";
  wrap.className = "teams" + (teamListe.length > 2 ? " viele" : "");
  teamListe.forEach((team, i) => {
    const f = TEAM_FARBEN[i];
    const sp = document.createElement("div");
    sp.className = "team";
    sp.innerHTML =
      `<h2 style="color:${f.farbe === "#E7ECF2" ? "var(--grau)" : f.farbe}">Team ${f.k}
         <span class="team-leibchen">${f.name}</span>
         <span class="schnitt">${schnitt(team)}</span></h2>`;
    const chips = document.createElement("div");
    chips.className = "chips";
    team.forEach((p) => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.style.borderLeft = "5px solid " + f.farbe;
      chip.innerHTML = `${escape(p.name)}` +
        `${p.position === "Tor" ? '<span class="tor">TW</span>' : ""}` +
        `<span class="elo">${p.elo}</span>`;
      // Antippen schiebt ins naechste Team (bei zweien: auf die andere Seite).
      chip.addEventListener("click", () => {
        const ziel = (i + 1) % teamListe.length;
        teamListe[i].splice(teamListe[i].indexOf(p), 1);
        teamListe[ziel].push(p);
        renderTeams();
        if (teamListe.length > 2) toast(p.name.split(" ")[0] + " → Team " + TEAM_FARBEN[ziel].k);
      });
      chips.appendChild(chip);
    });
    if (!team.length) chips.innerHTML = '<p class="hinweis">noch leer</p>';
    sp.appendChild(chips);
    wrap.appendChild(sp);
  });
  renderTeamAnzahl();
  renderSiegchance();
  renderErgebnisKnoepfe();
}

function renderTeamAnzahl() {
  const el = $("#team-anzahl");
  if (!el) return;
  const anwesende = teamListe.flat().length;
  el.innerHTML = '<span class="ta-lab">Teams</span>';
  const gr = document.createElement("div");
  gr.className = "ta-gruppe";
  [2, 3, 4].forEach((n) => {
    const b = document.createElement("button");
    b.textContent = n;
    b.setAttribute("aria-pressed", teamListe.length === n ? "true" : "false");
    b.disabled = anwesende < n * 2;
    b.addEventListener("click", () => {
      teamAnzahlSetzen(n);
      teamsNeuBilden(teamListe.flat());
      renderTeams();
    });
    gr.appendChild(b);
  });
  el.appendChild(gr);
}

function schnitt(team) {
  if (!team.length) return "";
  return "Ø " + Math.round(team.reduce((a, p) => a + p.elo, 0) / team.length);
}
function mittel(team) {
  return team.length ? team.reduce((a, p) => a + p.elo, 0) / team.length : 0;
}

// Bei zwei Teams die Siegchance, sonst ein Staerkevergleich (eine Chance
// zwischen vier Teams waere Zahlenspielerei).
function renderSiegchance() {
  const el = $("#siegchance");
  if (teamListe.length !== 2) {
    if (teamListe.some((t) => !t.length)) { el.innerHTML = ""; return; }
    const schnitte = teamListe.map(mittel);
    const mx = Math.max(...schnitte), mn = Math.min(...schnitte);
    el.innerHTML = '<div class="staerke">' + teamListe.map((t, i) => {
      const breite = 45 + (mx === mn ? 55 : ((mittel(t) - mn) / (mx - mn)) * 55);
      return `<div class="st-zeile"><span class="st-k" style="color:${TEAM_FARBEN[i].farbe}">Team ${TEAM_FARBEN[i].k}</span>` +
             `<span class="st-bar"><i style="width:${breite}%;background:${TEAM_FARBEN[i].farbe}"></i></span>` +
             `<span class="st-w">Ø ${Math.round(mittel(t))}</span></div>`;
    }).join("") + "</div>";
    return;
  }
  const [a, b] = teamListe;
  if (!a.length || !b.length) { el.innerHTML = ""; return; }
  const pA = 1 / (1 + Math.pow(10, (mittel(b) - mittel(a)) / 400));
  const p = Math.round(pA * 100);
  el.innerHTML =
    `<span class="ch-a">Team A ${p}%</span>` +
    `<span class="ch-bar"><span style="width:${p}%"></span></span>` +
    `<span class="ch-b">${100 - p}% Team B</span>`;
}

// Ergebnis-Knoepfe: je Team einer, mit den Namen darunter - beim Eintragen
// zwischen zwei Spielen will man sehen, wen man da gerade wertet.
function renderErgebnisKnoepfe() {
  const el = $("#ergebnis-knoepfe");
  el.innerHTML = "";
  teamListe.forEach((team, i) => {
    const f = TEAM_FARBEN[i];
    const b = document.createElement("button");
    b.className = "erg";
    b.style.background = f.farbe;
    b.style.color = f.text;
    b.innerHTML =
      `<span class="erg-txt"><span class="erg-titel">Team ${f.k} gewinnt` +
      `<span class="erg-oe">${schnitt(team)} · ${team.length}</span></span>` +
      `<span class="erg-namen">${escape(team.map((p) => p.name.split(" ")[0]).join(" · "))}</span></span>` +
      `<span class="erg-pfeil">›</span>`;
    b.addEventListener("click", () => eintragen(f.k));
    el.appendChild(b);
  });
  const u = document.createElement("button");
  u.className = "erg unent";
  u.innerHTML =
    `<span class="erg-txt"><span class="erg-titel">Unentschieden</span>` +
    `<span class="erg-namen">Alle bekommen die Hälfte</span></span><span class="erg-pfeil">›</span>`;
  u.addEventListener("click", () => eintragen("U"));
  el.appendChild(u);
}

function ergebnisKnoepfeSperren(sperren) {
  document.querySelectorAll("#ergebnis-knoepfe button").forEach((b) => {
    b.disabled = sperren;
  });
}

async function eintragen(ergebnis) {
  if (teamListe.length < 2 || teamListe.some((t) => !t.length)) {
    toast("Jedes Team braucht Spielerinnen."); return;
  }
  if (sendeLaeuft) return;              // schon ein Absenden unterwegs
  if (!spielToken) neuerSpielToken();   // Sicherheitsnetz, falls kein Token gesetzt
  sendeLaeuft = true;
  ergebnisKnoepfeSperren(true);
  try {
    // Geht immer erst in die Outbox; online sofort gesendet, offline gepuffert.
    // Der Token verhindert Doppelzaehlung, egal wann der Sync passiert.
    const r = await Sync.senden("/api/spiel", {
      teams: teamListe.map((t) => t.map((p) => p.id)),
      ergebnis,
      token: spielToken,
    });
    if (r.gesendet) {
      // Online: Teams mit frischen ELOs aus der Rangliste auffrischen.
      const rl = await Sync.frischHolen("/api/rangliste");
      if (Array.isArray(rl)) {
        const nachId = Object.fromEntries(rl.map((p) => [p.id, p]));
        teamListe = teamListe.map((t) => t.map((p) => nachId[p.id] || p));
      }
      toast((ergebnis === "U" ? "Unentschieden gespeichert"
        : "Sieg Team " + ergebnis + " gespeichert") + " — nächstes Spiel?");
    } else {
      toast("Offline gespeichert – wird im WLAN automatisch synchronisiert.");
    }
    neuerSpielToken(); // Outbox haelt den alten Token; naechstes Spiel neu
    renderTeams();
  } catch (e) {
    toast("Fehler: " + e.message);
  } finally {
    sendeLaeuft = false;
    ergebnisKnoepfeSperren(false);
  }
}

$("#btn-neu-mischen").addEventListener("click", () => {
  teamsNeuBilden(teamListe.flat());
  renderTeams();
});

$("#btn-zurueck").addEventListener("click", () => {
  ladeSpieler().then(() => zeigeView("view-anwesenheit"));
});

// -------------------------------------------------------------- Rangliste ----
async function ladeRangliste() {
  // Offline-first: erst den letzten bekannten Stand sofort zeigen, dann (online)
  // frisch nachladen. Siehe sync.js / local-db.js.
  const el = $("#rangliste-liste");
  const zeige = (liste) => {
    el.innerHTML = "";
    liste.forEach((p, i) => {
      const zeile = document.createElement("button");
      zeile.className = "rang-zeile";
      zeile.innerHTML = `
        <span class="platz">${i + 1}</span>
        <span class="name">${escape(p.name)}${p.position === "Tor" ? ' <span class="tor">TW</span>' : ""}</span>
        <span class="elo">${p.elo}</span>
        <span class="sp">${p.spiele_gesamt} Sp.</span>`;
      zeile.addEventListener("click", () => oeffneSpielerDetail(p));
      el.appendChild(zeile);
    });
  };
  const cached = await Sync.spiegelRoh("/api/rangliste");
  if (cached) zeige(cached);
  const frisch = await Sync.frischHolen("/api/rangliste");
  if (frisch) zeige(frisch);
}

// -------------------------------------------------- Spieler-/Spiel-Detail ----
let detailSpieler = null;      // {id, name, elo, position_angriff, ...}
let detailSpiele = [];         // geladene Spiele der gewaehlten Spielerin
let detailStats = null;        // Kennzahlen der gewaehlten Spielerin
let detailTraining = null;     // Trainings-Anwesenheit der gewaehlten Spielerin
let detailLC = null;           // Laufchallenge-Ergebnis der gewaehlten Spielerin
let aktuellesSpiel = null;     // im Spiel-Detail geoeffnetes Spiel
// Wohin „zurück" aus dem Spieler-Detail führt (Rangliste oder Kader).
let detailZurueck = () => { ladeRangliste(); zeigeView("view-rangliste"); };

function datumKurz(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

async function oeffneSpielerDetail(p, herkunft) {
  try {
    // offline-faehig: einmal online geoeffnet -> danach aus dem GET-Cache
    const d = await Sync.apiOffline("/api/spieler/" + p.id + "/spiele");
    detailSpieler = d.spieler;
    detailSpiele = d.spiele;
    detailStats = d.stats;
    detailTraining = d.training || null;
    detailLC = d.laufchallenge || null;
    // Zurück-Ziel je nach Herkunft (Rangliste bzw. Kader).
    if (herkunft === "kader") {
      $("#btn-detail-zurueck").textContent = "← Kader";
      detailZurueck = () => { ladeKader(); zeigeView("view-kader"); };
    } else {
      $("#btn-detail-zurueck").textContent = "← Rangliste";
      detailZurueck = () => { ladeRangliste(); zeigeView("view-rangliste"); };
    }
    renderSpielerDetail();
    zeigeView("view-spieler-detail");
  } catch (e) {
    toast(navigator.onLine ? ("Fehler: " + e.message)
      : "Offline – diese Details wurden noch nicht geladen. Einmal online öffnen.");
  }
}

// ELO-Verlauf als kleine Inline-SVG-Sparkline (offline-/CSP-sicher, kein Lib).
// Rekonstruiert die ELO nach jedem Spiel aus aktueller ELO + Deltas (neueste
// zuerst), dann von alt nach neu gezeichnet.
function eloSparkline() {
  const deltas = detailSpiele.map((s) => s.delta);   // neueste zuerst
  if (deltas.length < 2) return "";
  let cur = detailSpieler.elo;
  const nach = [cur];                                // elo nach neuestem Spiel
  for (const d of deltas) { cur = cur - d; nach.push(cur); }
  const werte = nach.reverse();                      // alt -> neu (inkl. Startwert)
  const w = 280, h = 56, pad = 5;
  const min = Math.min(...werte), max = Math.max(...werte), span = (max - min) || 1;
  const px = (i) => pad + i * (w - 2 * pad) / (werte.length - 1);
  const py = (v) => pad + (h - 2 * pad) * (1 - (v - min) / span);
  const pts = werte.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");
  const farbe = werte[werte.length - 1] >= werte[0] ? "var(--gruen)" : "var(--b)";
  return `<svg class="elo-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="ELO-Verlauf">` +
    `<polyline fill="none" stroke="${farbe}" stroke-width="2" points="${pts}"/>` +
    `<circle cx="${px(werte.length - 1).toFixed(1)}" cy="${py(werte[werte.length - 1]).toFixed(1)}" r="3.5" fill="${farbe}"/>` +
    `</svg>`;
}

// Profilkopf: Position, Trainings-Anwesenheit, ELO-Sparkline.
function renderProfil() {
  const el = $("#detail-profil");
  if (!el) return;
  const sp = detailSpieler;
  const badges = [];
  if (sp.position === "Tor") badges.push("Torhüterin");
  if (sp.position_angriff) badges.push("Angriff: " + escape(sp.position_angriff));
  if (sp.position_abwehr) badges.push("Abwehr: " + escape(sp.position_abwehr));
  const badgeHtml = badges.length
    ? `<div class="profil-badges">${badges.map((b) => `<span class="pb">${b}</span>`).join("")}</div>` : "";
  let training = "";
  const tr = detailTraining;
  if (tr && tr.erfasst) {
    const q = tr.quote != null ? tr.quote + "%" : "–";
    training = `<div class="profil-training">
      <span class="pt-wert">${tr.anwesend}<small>/${tr.anwesend + tr.abgesagt}</small></span>
      <span class="pt-label">Trainings da (${q})</span></div>`;
  }
  let lauf = "";
  const lc = detailLC;
  if (lc) {
    const platz = lc.rang ? `Platz ${lc.rang}${lc.teilnehmer ? " / " + lc.teilnehmer : ""}` : "";
    const andere = lc.andere ? ` · ${lc.andere} andere` : "";
    lauf = `<div class="profil-lauf">
      <div class="pl-kopf">🏃 ${escape(lc.challenge || "Laufchallenge")}</div>
      <div class="pl-zahlen">
        <span class="pl-km">${lc.km}<small>km</small></span>
        <span class="pl-meta">${lc.laeufe} Läufe${andere}</span>
        ${platz ? `<span class="pl-rang">${platz}</span>` : ""}
      </div></div>`;
  }
  const spark = eloSparkline();
  const sparkBlock = spark
    ? `<div class="profil-elo"><div class="pe-kopf">ELO-Verlauf</div>${spark}</div>` : "";
  el.innerHTML = badgeHtml + training + lauf + sparkBlock;
}

function renderStats() {
  const el = $("#detail-stats");
  const s = detailStats;
  if (!s || (s.siege + s.unent + s.niederlagen) === 0) { el.innerHTML = ""; return; }
  const serieText = s.serie_typ
    ? (s.serie_anzahl + "× " + ({ S: "Sieg", N: "Niederlage", U: "Unent." }[s.serie_typ])
        + (s.serie_anzahl > 1 && s.serie_typ !== "U" ? "e" : ""))
    : "–";
  const kacheln = [
    ["Bilanz", `${s.siege}·${s.unent}·${s.niederlagen}`, "S·U·N"],
    ["Serie", serieText, ""],
    ["Bester", (s.bester > 0 ? "+" : "") + s.bester, "ein Spiel"],
    ["Höchststand", s.peak, "ELO"],
  ];
  el.innerHTML = kacheln.map(([t, w, u]) =>
    `<div class="stat"><span class="s-wert">${w}</span>` +
    `<span class="s-titel">${t}</span>${u ? `<span class="s-unter">${u}</span>` : ""}</div>`
  ).join("");
}

function renderSpielerDetail() {
  $("#detail-name").textContent = `${detailSpieler.name} · ELO ${detailSpieler.elo}`;
  renderProfil();
  renderStats();
  const el = $("#detail-spiele");
  el.innerHTML = "";
  if (!detailSpiele.length) {
    el.innerHTML = '<p class="hinweis">Noch keine Spiele gespielt.</p>';
    return;
  }
  detailSpiele.forEach((s, idx) => {
    const zeile = document.createElement("button");
    zeile.className = "detail-zeile";
    const kl = s.delta > 0 ? "plus" : (s.delta < 0 ? "minus" : "null");
    const vz = s.delta > 0 ? "+" : "";
    const erg = s.ergebnis === "U" ? "Unentschieden"
      : (s.ergebnis === s.mein_team ? "Sieg" : "Niederlage");
    zeile.innerHTML = `
      <span class="d-datum">${datumKurz(s.datum)}</span>
      <span class="d-erg">${erg}</span>
      <span class="d-delta ${kl}">${vz}${s.delta}</span>`;
    zeile.addEventListener("click", () => oeffneSpielDetail(idx));
    el.appendChild(zeile);
  });
}

function oeffneSpielDetail(idx) {
  const s = detailSpiele[idx];
  aktuellesSpiel = s;
  const unent = s.ergebnis === "U";
  // Aeltere Spiele kennen nur team_a/team_b, neuere die ganze Liste.
  const gruppen = s.teams && s.teams.length ? s.teams : [s.team_a, s.team_b];
  $("#spiel-titel").textContent = datumKurz(s.datum) + " · " +
    (unent ? "Unentschieden" : "Sieg Team " + s.ergebnis) +
    (gruppen.length > 2 ? ` · ${gruppen.length} Teams` : "");

  const wrap = $("#spiel-teams");
  wrap.innerHTML = "";
  gruppen.forEach((team, i) => {
    const k = TEAM_FARBEN[i].k;
    const block = document.createElement("div");
    block.id = "spiel-team-" + k;
    wrap.appendChild(block);
    renderTeamBlock("#spiel-team-" + k, "Team " + k, team,
      unent ? "unent" : (s.ergebnis === k ? "sieger" : "verlierer"));
  });

  // Korrektur-Knoepfe passend zur Teamzahl dieses Spiels
  const kk = $("#korrektur-knoepfe");
  kk.innerHTML = "";
  gruppen.forEach((_, i) => {
    const k = TEAM_FARBEN[i].k;
    const b = document.createElement("button");
    b.textContent = "Team " + k;
    b.classList.toggle("aktiv", s.ergebnis === k);
    b.addEventListener("click", () => spielKorrigieren(k));
    kk.appendChild(b);
  });
  const u = document.createElement("button");
  u.textContent = "Unent.";
  u.classList.toggle("aktiv", s.ergebnis === "U");
  u.addEventListener("click", () => spielKorrigieren("U"));
  kk.appendChild(u);

  zeigeView("view-spiel-detail");
}

async function spielKorrigieren(ergebnis) {
  if (!aktuellesSpiel) return;
  if (ergebnis === aktuellesSpiel.ergebnis) { toast("Ergebnis ist schon so eingetragen."); return; }
  try {
    await api("/api/spiel/" + aktuellesSpiel.spiel_id + "/aendern", "POST", { ergebnis });
    toast("Ergebnis geändert — ELOs neu berechnet.");
    await detailNeuLaden(aktuellesSpiel.spiel_id);
  } catch (e) { toast("Fehler: " + e.message); }
}

async function spielLoeschen() {
  if (!aktuellesSpiel) return;
  if (!confirm("Dieses Spiel wirklich löschen? Die ELOs werden neu berechnet.")) return;
  try {
    await api("/api/spiel/" + aktuellesSpiel.spiel_id + "/loeschen", "POST");
    toast("Spiel gelöscht — ELOs neu berechnet.");
    await detailNeuLaden(null);   // zurueck zur Spieler-Uebersicht
  } catch (e) { toast("Fehler: " + e.message); }
}

// Spieler-Detail nach einer Aenderung neu laden; wenn das Spiel noch existiert,
// erneut oeffnen, sonst zurueck zur Uebersicht.
async function detailNeuLaden(spielId) {
  const d = await api("/api/spieler/" + detailSpieler.id + "/spiele");
  detailSpieler = d.spieler;
  detailSpiele = d.spiele;
  detailStats = d.stats;
  detailTraining = d.training || null;
  detailLC = d.laufchallenge || null;
  renderSpielerDetail();
  const idx = spielId == null ? -1 : detailSpiele.findIndex((s) => s.spiel_id === spielId);
  if (idx >= 0) oeffneSpielDetail(idx);
  else zeigeView("view-spieler-detail");
}

$("#btn-spiel-loeschen").addEventListener("click", spielLoeschen);

function renderTeamBlock(sel, titel, spieler, klasse) {
  const el = $(sel);
  el.className = "spiel-team " + klasse;
  const label = klasse === "sieger" ? "Sieger"
    : (klasse === "verlierer" ? "Verlierer" : "Unentschieden");
  const items = spieler.map((p) => {
    const hervor = p.id === detailSpieler.id ? " hervor" : "";
    const tw = p.position === "Tor" ? ' <span class="tw">TW</span>' : "";
    return `<li class="${hervor.trim()}">${escape(p.name)}${tw}</li>`;
  }).join("");
  el.innerHTML = `<div class="team-kopf">${titel} · ${label}</div><ul>${items}</ul>`;
}

$("#btn-detail-zurueck").addEventListener("click", () => detailZurueck());
$("#btn-spiel-zurueck").addEventListener("click", () => zeigeView("view-spieler-detail"));

// ==================================================== Aufstellung / Feld =====
//  Wer steht wo? Zwei Ansichten auf demselben Halbfeld:
//    Training - ALLE Zusagen stehen auf ihrer Position (alle Halblinken bei
//               Halblinks). Zeigt sofort, wo es duenn wird.
//    Spiel    - eine Spielerin je Position plus Wechselbank.
//  Die Spiel-Aufstellung ist eine Tafel, kein Dokument: sie liegt lokal auf
//  dem Geraet (localStorage), nicht auf dem Server.

const POSITIONEN = [
  { k: "TW", lang: "Tor",         x: 50,   y: 88.5, gx: 50, gy: 88 },
  { k: "LA", lang: "Linksaußen",  x: 10.5, y: 79.5, gx: 15, gy: 78 },
  { k: "HL", lang: "Halblinks",   x: 24,   y: 39.5, gx: 20, gy: 36 },
  { k: "RM", lang: "Mitte",       x: 50,   y: 36.5, gx: 50, gy: 29 },
  { k: "HR", lang: "Halbrechts",  x: 76,   y: 39.5, gx: 80, gy: 36 },
  { k: "RA", lang: "Rechtsaußen", x: 89.5, y: 79.5, gx: 85, gy: 78 },
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

function positionenVon(sp) {
  const treffer = new Set();
  (sp.position_angriff || "").toLowerCase().split(/[\/,;+&]|\bund\b/).forEach((t) => {
    const s = t.trim();
    if (POS_ALIAS[s]) POS_ALIAS[s].forEach((k) => treffer.add(k));
  });
  if (!treffer.size && sp.position === "Tor") treffer.add("TW");   // grobe Angabe rettet
  return [...treffer];
}
const initialen = (name) =>
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

// Portrait im Wappen: Initialen jetzt, Fotos spaeter in derselben Form.
function wappen(sp, groesse) {
  const t = [["#3467C9", "#16376F"], ["#2F62BD", "#122F5E"], ["#4A7BD4", "#1B3F7E"]][sp.id % 3];
  return `<span class="wappen" style="--w:${groesse}px;--c1:${t[0]};--c2:${t[1]}">` +
         `<span class="ini">${escape(initialen(sp.name))}</span></span>`;
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

async function ladeAufstellung() {
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

// ------------------------------------------------------------------ Kader ----
function stufeVonElo(elo) {
  if (elo >= 1150) return "stark";
  if (elo <= 850) return "schwach";
  return "mittel";
}

async function ladeKader() {
  spielerAlle = await api("/api/spieler");
  const el = $("#kader-liste");
  el.innerHTML = "";
  for (const s of spielerAlle) {
    const zeile = document.createElement("div");
    zeile.className = "kader-zeile";
    const gespielt = s.spiele_gesamt > 0;
    zeile.innerHTML = `
      <div class="kopf klickbar" role="button" tabindex="0">
        <span class="name">${escape(s.name)}</span>
        <span class="meta">ELO ${s.elo} · ${s.spiele_gesamt} Sp. <span class="kopf-pfeil">›</span></span>
      </div>
      <div class="steuer">
        <label>Stufe
          <select class="f-stufe" ${gespielt ? "disabled title='nach Spielen gesperrt'" : ""}>
            <option value="stark" ${stufeVonElo(s.elo) === "stark" ? "selected" : ""}>stark</option>
            <option value="mittel" ${stufeVonElo(s.elo) === "mittel" ? "selected" : ""}>mittel</option>
            <option value="schwach" ${stufeVonElo(s.elo) === "schwach" ? "selected" : ""}>schwach</option>
          </select>
        </label>
        <label class="aktiv-label">aktiv
          <input type="checkbox" class="f-aktiv" ${s.aktiv ? "checked" : ""}>
        </label>
      </div>
      <div class="pos-wahl">
        <div class="pos-kopf">Position auf dem Feld <span>mehrere möglich</span></div>
        <div class="pos-chips"></div>
      </div>`;
    zeile.querySelector(".kopf").addEventListener("click", () => oeffneSpielerDetail(s, "kader"));
    const speichern = (feld) =>
      api("/api/spieler/" + s.id, "POST", feld).then(() => ladeKader());
    zeile.querySelector(".f-stufe").addEventListener("change", (e) =>
      speichern({ stufe: e.target.value }));
    zeile.querySelector(".f-aktiv").addEventListener("change", (e) =>
      speichern({ aktiv: e.target.checked }));

    // Angriffsposition als Mehrfachauswahl. Sie steuert die Feld-Ansicht und
    // (ueber "Tor") auch, wen die Team-Aufteilung als Torhueterin behandelt.
    const wahl = new Set(positionenVon(s));
    const chips = zeile.querySelector(".pos-chips");
    POSITIONEN.forEach((pos) => {
      const c = document.createElement("button");
      c.className = "pchip" + (wahl.has(pos.k) ? " aktiv" : "");
      c.innerHTML = `<b>${pos.k}</b><span>${pos.lang}</span>`;
      c.title = pos.lang;
      c.setAttribute("aria-pressed", wahl.has(pos.k) ? "true" : "false");
      c.addEventListener("click", () => {
        if (wahl.has(pos.k)) wahl.delete(pos.k); else wahl.add(pos.k);
        c.classList.toggle("aktiv", wahl.has(pos.k));
        c.setAttribute("aria-pressed", wahl.has(pos.k) ? "true" : "false");
        const text = POSITIONEN.filter((x) => wahl.has(x.k)).map((x) => x.lang).join("/");
        s.position_angriff = text;
        s.position = wahl.has("TW") ? "Tor" : "Feld";
        api("/api/spieler/" + s.id, "POST", { position_angriff: text })
          .then(() => toast(s.name.split(" ")[0] + ": " + (text || "Position offen")))
          .catch((e) => toast("Nicht gespeichert: " + e.message));
      });
      chips.appendChild(c);
    });
    el.appendChild(zeile);
  }
}

function anytypeStatus(text, ok) {
  const el = $("#anytype-status");
  if (!el) return;
  const zeit = new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  el.textContent = `${zeit} — ${text}`;
  el.classList.toggle("ok", ok === true);
  el.classList.toggle("fehler", ok === false);
  try { localStorage.setItem("anytypeStatus", JSON.stringify({ zeit, text, ok })); } catch (_) {}
}

function restoreAnytypeStatus() {
  try {
    const raw = localStorage.getItem("anytypeStatus");
    if (!raw) return;
    const { zeit, text, ok } = JSON.parse(raw);
    const el = $("#anytype-status");
    el.textContent = `zuletzt ${zeit} — ${text}`;
    el.classList.toggle("ok", ok === true);
    el.classList.toggle("fehler", ok === false);
  } catch (_) {}
}

$("#btn-import").addEventListener("click", async () => {
  const btn = $("#btn-import");
  btn.disabled = true; anytypeStatus("Import läuft…", null);
  try {
    const r = await api("/api/anytype/import", "POST");
    anytypeStatus(`Import ok: ${r.neu} neu, ${r.aktualisiert} aktualisiert`, true);
    ladeKader();
  } catch (e) { anytypeStatus("Import fehlgeschlagen: " + e.message, false); }
  finally { btn.disabled = false; }
});

$("#btn-sync").addEventListener("click", async () => {
  const btn = $("#btn-sync");
  btn.disabled = true; anytypeStatus("Sync läuft…", null);
  try {
    const r = await api("/api/anytype/sync", "POST");
    anytypeStatus(`Sync ok: ${r.geschrieben} ELOs nach Anytype geschrieben`, true);
  } catch (e) { anytypeStatus("Sync fehlgeschlagen: " + e.message, false); }
  finally { btn.disabled = false; }
});

$("#form-spieler").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("#neu-name").value.trim();
  if (!name) return;
  try {
    await api("/api/spieler", "POST", {
      name,
      stufe: $("#neu-stufe").value,
      position: $("#neu-position").value,
    });
    $("#neu-name").value = "";
    ladeKader();
    toast(name + " hinzugefügt");
  } catch (err) { toast("Fehler: " + err.message); }
});

// -------------------------------------------------------------- Hilfsmittel ----
let toastTimer = null;
function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2600);
}

function escape(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).catch(() => {});
  let neuladen = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (neuladen) return;
    neuladen = true;
    location.reload();          // bei neuem Service Worker automatisch frisch laden
  });
}

// ---------------------------------------------------------------- Coach ----
let llmVerlauf = [];          // {role, content} fuer das Modell
let coachGestartet = false;
let chatDatumCursor = null;   // lokales Datum des zuletzt gerenderten Bubbles
let mediaRecorder = null;
let audioChunks = [];

const GRUSS = "Hi! Beschreib dein Training (tippen oder 🎤) – zum Beispiel: 90 Minuten, 14 Spielerinnen, Schwerpunkt Tempospiel. Ich frage nach, wenn etwas fehlt, und hänge den Plan auf Wunsch direkt ans Training.";

async function starteCoach() {
  if (coachGestartet) return;
  coachGestartet = true;
  chatEl().innerHTML = "";
  chatDatumCursor = null;
  llmVerlauf = [];
  let hist = [];
  try { hist = await api("/api/chat"); } catch (e) {}
  if (!hist.length) { botBubble(GRUSS); return; }
  for (const m of hist) {
    if (m.rolle === "plan") zeigePlan(m.titel, m.text, m.ts);
    else bubble(m.rolle, m.text, { ts: m.ts, zeit: m.rolle !== "info" });
    if (m.rolle === "user") llmVerlauf.push({ role: "user", content: m.text });
    if (m.roh) llmVerlauf.push({ role: "assistant", content: m.roh });
  }
}

function chatEl() { return $("#chat-verlauf"); }

// Nachricht best-effort serverseitig speichern (blockiert den Chat nie).
function persist(rolle, text, extra) {
  api("/api/chat", "POST", Object.assign({ rolle, text }, extra || {})).catch(() => {});
}

function lokalesDatum(ts) {
  const d = ts ? new Date(ts) : new Date();
  return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
}

function datumsLabel(ts) {
  const d = new Date(ts), heute = new Date();
  const gestern = new Date(); gestern.setDate(heute.getDate() - 1);
  const gleich = (a, b) => a.toDateString() === b.toDateString();
  if (gleich(d, heute)) return "Heute";
  if (gleich(d, gestern)) return "Gestern";
  if ((heute - d) / 86400000 < 7) return d.toLocaleDateString("de-DE", { weekday: "long" });
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// Bei Datumswechsel einen WhatsApp-artigen Trenner einfuegen.
function ensureDivider(ts) {
  const tag = lokalesDatum(ts);
  if (tag === chatDatumCursor) return;
  chatDatumCursor = tag;
  const div = document.createElement("div");
  div.className = "chat-tag";
  div.innerHTML = `<span>${escape(datumsLabel(ts))}</span>`;
  chatEl().appendChild(div);
}

function bubble(rolle, text, opt) {
  opt = opt || {};
  const ts = opt.ts || new Date().toISOString();
  ensureDivider(ts);
  const div = document.createElement("div");
  div.className = "bubble " + rolle;
  if (text) {
    const t = document.createElement("span");
    t.className = "b-text";
    t.textContent = text;
    div.appendChild(t);
  }
  if (opt.zeit !== false) {
    const z = document.createElement("span");
    z.className = "b-zeit";
    z.textContent = new Date(ts).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    div.appendChild(z);
  }
  chatEl().appendChild(div);
  chatEl().scrollTop = chatEl().scrollHeight;
  return div;
}
function userBubble(t, opt) { return bubble("user", t, opt); }
function botBubble(t, opt) { return bubble("bot", t, opt); }
function infoBubble(t) { return bubble("info", t, { zeit: false }); }

async function coachSenden(text) {
  text = (text || "").trim();
  if (!text) return;
  userBubble(text);
  persist("user", text);
  llmVerlauf.push({ role: "user", content: text });
  $("#chat-text").value = "";
  const tip = botBubble("…", { zeit: false });
  try {
    const r = await api("/api/trainer/chat", "POST", { verlauf: llmVerlauf });
    tip.remove();
    if (r.roh) llmVerlauf.push({ role: "assistant", content: r.roh });
    if (r.typ === "rueckfrage") {
      const t = "Dazu brauche ich noch:\n" + (r.fragen || []).map((f) => "• " + f).join("\n");
      botBubble(t);
      persist("bot", t, { roh: r.roh });
    } else if (r.typ === "plan") {
      if (r.warnung) { infoBubble(r.warnung); persist("info", r.warnung); }
      zeigePlan(r.titel, r.markdown);
      persist("plan", r.markdown, { titel: r.titel, roh: r.roh });
    } else {
      const t = r.text || "(keine Antwort)";
      botBubble(t);
      persist("bot", t, { roh: r.roh });
    }
  } catch (e) {
    tip.remove();
    infoBubble("Fehler: " + e.message);
  }
}

function zeigePlan(titel, markdown, ts) {
  const div = bubble("bot", "", { ts, zeit: false });
  const pre = document.createElement("div");
  pre.className = "plan";
  pre.textContent = markdown;
  div.appendChild(pre);
  const btn = document.createElement("button");
  btn.className = "primaer plan-btn";
  btn.textContent = "✅ Passt – ans Training";
  btn.addEventListener("click", () => zeigeAnlageOptionen(div, btn, titel, markdown));
  div.appendChild(btn);
  const z = document.createElement("span");
  z.className = "b-zeit";
  z.textContent = new Date(ts || Date.now()).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  div.appendChild(z);
  chatEl().scrollTop = chatEl().scrollHeight;
}

async function zeigeAnlageOptionen(div, btn, titel, markdown) {
  btn.disabled = true;
  btn.textContent = "…";
  let trainings = [];
  try { trainings = await api("/api/trainings"); } catch (e) {}
  const heute = new Date().toISOString().slice(0, 10);
  const kommend = (trainings || [])
    .filter((t) => t.datum && t.datum >= heute)
    .sort((a, b) => a.datum.localeCompare(b.datum));
  btn.remove();
  const box = document.createElement("div");
  box.className = "anlage-optionen";
  const frage = document.createElement("div");
  frage.className = "anlage-frage";
  frage.textContent = kommend.length
    ? "An welches Training anhängen?"
    : "Kein anstehendes Training – neu anlegen?";
  box.appendChild(frage);
  kommend.forEach((t) => {
    const b = document.createElement("button");
    b.className = "opt-btn";
    const zusatz = t.hat_plan ? " · ersetzt Plan" : "";
    b.textContent = "→ " + (t.label || t.datum) + " (" + (t.anwesend || 0) + " Zusagen)" + zusatz;
    b.addEventListener("click", () =>
      planSpeichern({ markdown, training_id: t.id }, box,
        "an " + (t.label || t.datum) + " angehängt"));
    box.appendChild(b);
  });
  const neu = document.createElement("button");
  neu.className = "opt-btn";
  neu.textContent = "→ Neues Training (Datum)";
  neu.addEventListener("click", () => {
    const datum = prompt("Datum des neuen Trainings (JJJJ-MM-TT)", heute);
    if (datum) planSpeichern({ markdown, titel, datum }, box,
      "als neues Training (" + datum + ") angelegt");
  });
  box.appendChild(neu);
  div.appendChild(box);
  chatEl().scrollTop = chatEl().scrollHeight;
}

// Plan nativ ans Training hängen: bestehendes -> /plan, sonst Training anlegen.
async function planSpeichern(payload, box, erfolg) {
  box.querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    if (payload.training_id != null) {
      await api("/api/trainings/" + payload.training_id + "/plan", "POST",
        { markdown: payload.markdown });
    } else {
      await api("/api/trainings", "POST",
        { datum: payload.datum, titel: payload.titel || "", markdown: payload.markdown });
    }
    infoBubble("✅ Plan " + erfolg + ".");
    box.remove();
    Sync.prefetchAlles(true).catch(() => {});   // Trainings-Cache auffrischen
  } catch (e) {
    box.querySelectorAll("button").forEach((b) => (b.disabled = false));
    infoBubble("Speichern fehlgeschlagen: " + e.message);
  }
}

$("#btn-senden").addEventListener("click", () => coachSenden($("#chat-text").value));
$("#chat-text").addEventListener("keydown", (e) => {
  if (e.key === "Enter") coachSenden($("#chat-text").value);
});

$("#btn-chat-loeschen").addEventListener("click", async () => {
  if (!confirm("Gesamten Chat-Verlauf löschen?")) return;
  try {
    await api("/api/chat/loeschen", "POST");
    coachGestartet = false;
    starteCoach();
    toast("Verlauf gelöscht");
  } catch (e) { toast("Fehler: " + e.message); }
});

$("#btn-mic").addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    infoBubble("Mikrofon nicht verfügbar (nur über HTTPS).");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => { if (e.data.size) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      $("#btn-mic").classList.remove("aufnahme");
      const typ = mediaRecorder.mimeType || "audio/webm";
      const ext = typ.includes("mp4") ? "mp4" : typ.includes("ogg") ? "ogg" : "webm";
      const blob = new Blob(audioChunks, { type: typ });
      const fd = new FormData();
      fd.append("datei", blob, "audio." + ext);
      const tip = botBubble("🎧 transkribiere…");
      try {
        const res = await fetch("/api/trainer/audio", { method: "POST", body: fd });
        tip.remove();
        if (!res.ok) throw new Error(await res.text());
        const { text } = await res.json();
        $("#chat-text").value = text;
        $("#chat-text").focus();
      } catch (e) {
        tip.remove();
        infoBubble("Transkription fehlgeschlagen: " + e.message);
      }
    };
    mediaRecorder.start();
    $("#btn-mic").classList.add("aufnahme");
    infoBubble("🎤 Aufnahme läuft – zum Stoppen nochmal 🎤 tippen.");
  } catch (e) {
    infoBubble("Mikrofon-Zugriff verweigert: " + e.message);
  }
});

// Start
// Sichtbare Versionsnummer im Kopf — was drin ist, steht in CHANGELOG.md.
// Bei jeder Aenderung: hier hochzaehlen, Eintrag im CHANGELOG, sw.js CACHE
// bumpen und die ?v= der geaenderten Dateien in index.html.
const APP_VERSION = "v0.40.0";
const versionEl = document.getElementById("version");
if (versionEl) versionEl.textContent = APP_VERSION;

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
}
document.addEventListener("server:status", (e) => { _serverOnline = e.detail.online; malePunkt(); });
document.addEventListener("outbox:offen", (e) => { _offen = e.detail.offen; malePunkt(); });
const _punkt = document.getElementById("server-punkt");
if (_punkt) _punkt.addEventListener("click", async () => {
  toast("Synchronisiere…");
  const ok = await Sync.jetztSynchronisieren();
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
function ladeStatus(text, prozent) {
  const t = document.getElementById("ladebalken-text");
  if (t && text != null) t.textContent = text;
  const b = document.getElementById("ladebalken-bar");
  if (b && prozent != null) b.style.width = prozent + "%";
}
function ladeFertig() {
  const l = document.getElementById("ladebalken");
  if (l) l.remove();
}

ladeStatus("App startet…", 60);
restoreAnytypeStatus();
ladeStatus("Anmeldung prüfen…", 85);
// Rolle kommt vom Server: /api/me -> appStarten() (angemeldet) bzw. zeigeLogin().
pruefeAnmeldung();
