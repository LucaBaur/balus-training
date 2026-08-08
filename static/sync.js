"use strict";

// ============================================================================
//  sync.js — Offline-Schicht: Server-Status, GET-Cache, Vorab-Laden, Outbox.
// ----------------------------------------------------------------------------
//  - GET (apiOffline/spiegelRoh/frischHolen): cache-first, IndexedDB-Spiegel.
//  - Schreiben (senden): geht IMMER erst in die Outbox (persistente Absicht) und
//    wird gesendet, sobald der Server erreichbar ist -> arbeiten im Funkloch,
//    automatischer Rueck-Sync im WLAN.
//  - Serverstatus: echter Ping auf /api/ping (navigator.onLine luegt im Flugmodus).
//  Voraussetzung: local-db.js ist VOR dieser Datei geladen (window.LocalDB).
// ============================================================================

function neuerToken() {
  return crypto?.randomUUID
    ? crypto.randomUUID()
    : "t-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

// Promise nach ms abbrechen, damit ein haengender Fetch nichts blockiert.
function mitTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms)),
  ]);
}

async function netzAufruf(pfad, methode, body) {
  const opt = { method: methode, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const res = await fetch(pfad, opt);
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    const err = new Error(txt || res.statusText || ("HTTP " + res.status));
    err.http = res.status; // Server HAT geantwortet -> kein Netzfehler
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

// -------------------------------------------------------- Server-Status ----
let serverErreichbar = false;
let letzterFehler = null; // letzte Fehlermeldung beim Senden (fuer Diagnose)

function statusSetzen(ok) {
  const geaendert = ok !== serverErreichbar;
  serverErreichbar = ok;
  if (geaendert) {
    document.dispatchEvent(new CustomEvent("server:status", { detail: { online: ok } }));
  }
  if (ok) {
    // Server wieder da -> offene Schreibvorgaenge senden und Daten auffrischen.
    flushOutbox().then(() => prefetchAlles(false)).catch(() => {});
  }
}

// Echte Erreichbarkeit pruefen (kurzer Ping, umgeht den Service Worker via /api).
async function pingServer() {
  try {
    await mitTimeout(
      fetch("/api/ping", { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error("nok"); }),
      2500
    );
    statusSetzen(true);
    return true;
  } catch (_) {
    statusSetzen(false);
    return false;
  }
}

// -------------------------------------------------------------- GET-Cache ----
async function spiegelRoh(pfad) {
  const c = await LocalDB.get("responses", pfad);
  return c ? c.daten : null;
}

async function frischHolen(pfad) {
  if (!serverErreichbar) return null; // kein sinnloser Netzversuch
  try {
    const daten = await mitTimeout(netzAufruf(pfad, "GET", null), 4000);
    LocalDB.put("responses", { pfad, daten, ts: Date.now() }).catch(() => {});
    return daten;
  } catch (_) {
    statusSetzen(false);
    return null;
  }
}

async function apiOffline(pfad, methode = "GET", body = null) {
  if (methode.toUpperCase() !== "GET") return senden(pfad, body); // Schreiben -> Outbox

  // Cache-first: im Cache -> sofort liefern, ggf. im Hintergrund auffrischen.
  const cached = await LocalDB.get("responses", pfad);
  if (cached) {
    if (serverErreichbar) frischHolen(pfad).catch(() => {});
    return cached.daten;
  }
  // Kein Cache: definitiv offline -> schnell abbrechen; sonst Netz versuchen.
  if (!serverErreichbar && navigator.onLine === false) {
    throw new Error("Offline und kein zwischengespeicherter Stand.");
  }
  const daten = await mitTimeout(netzAufruf(pfad, "GET", null), 4000);
  LocalDB.put("responses", { pfad, daten, ts: Date.now() }).catch(() => {});
  return daten;
}

// --------------------------------------------------------- Vorab-Laden ----
//  Alle offline benoetigten Daten holen, damit NICHTS erst angeklickt werden muss.
let _letzterPrefetch = 0;
let _prefetchLaeuft = false;
async function prefetchAlles(force) {
  if (!serverErreichbar || _prefetchLaeuft) return;
  const jetzt = Date.now();
  if (!force && jetzt - _letzterPrefetch < 60000) return; // hoechstens 1x/Minute
  _prefetchLaeuft = true;
  _letzterPrefetch = jetzt;
  try {
    const rang = await frischHolen("/api/rangliste");
    await frischHolen("/api/spieler");
    await frischHolen("/api/anytype/trainings");
    // Phase-3-Inhalte (native): Home, Trainings-Liste + -Details, Wiki-Kategorien
    // inkl. der Seiten-Details (damit offline nichts erst angeklickt werden muss).
    await frischHolen("/api/naechstes-training");
    const trainings = await frischHolen("/api/trainings");
    if (Array.isArray(trainings)) {
      for (const t of trainings) await frischHolen("/api/trainings/" + t.id);
    }
    for (const kat of ["playbook", "gegner", "uebung", "statistik",
                       "saison", "orga", "notiz", "besprechung"]) {
      const seiten = await frischHolen("/api/seiten?kategorie=" + kat);
      if (Array.isArray(seiten)) {
        for (const s of seiten) {
          if (s.hat_inhalt) await frischHolen("/api/seiten/" + s.id);
        }
      }
    }
    if (Array.isArray(rang)) {
      for (const p of rang) {
        await frischHolen("/api/spieler/" + p.id + "/spiele");
      }
    }
    document.dispatchEvent(new CustomEvent("prefetch:fertig"));
  } catch (_) {
    /* Teil-Prefetch ist ok; naechster Lauf holt den Rest */
  } finally {
    _prefetchLaeuft = false;
  }
}

// -------------------------------------------------------------- Schreiben ----
//  Immer erst persistent in die Outbox, dann (wenn Server da) sofort senden.
async function senden(pfad, body) {
  const token = (body && body.token) || neuerToken();
  const eintrag = { token, pfad, methode: "POST", body: { ...(body || {}), token }, ts: Date.now() };
  await LocalDB.outboxHinzu(eintrag);
  meldeOffen();
  if (serverErreichbar) await flushOutbox();
  const nochOffen = await LocalDB.get("outbox", token);
  return { gesendet: !nochOffen, token };
}

// Flushes werden SERIALISIERT (Promise-Kette), nicht per Guard abgebrochen —
// sonst kann ein gerade laufender Flush einen frisch eingereihten Eintrag
// "verschlucken" und senden() meldet faelschlich "nicht gesendet".
let _flushKette = Promise.resolve();
function flushOutbox() {
  _flushKette = _flushKette.then(_flushEinmal, _flushEinmal);
  return _flushKette;
}
async function _flushEinmal() {
  if (!serverErreichbar) return;
  const offen = (await LocalDB.outboxAlle()).sort((a, b) => a.ts - b.ts);
  for (const e of offen) {
    try {
      await mitTimeout(netzAufruf(e.pfad, e.methode, e.body), 6000);
      await LocalDB.outboxEntfernen(e.token); // erst nach Erfolg -> nie doppelt
      letzterFehler = null;
    } catch (err) {
      letzterFehler = (err && err.message) ? err.message : String(err);
      document.dispatchEvent(new CustomEvent("sync:fehler", { detail: { fehler: letzterFehler } }));
      // Nur ein echter Netzfehler = offline. Eine Server-Fehlerantwort
      // (err.http gesetzt) heisst: Server erreichbar, aber dieser Eintrag klemmt.
      if (!err || err.http === undefined) statusSetzen(false);
      break; // Reihenfolge bewahren -> Rest beim naechsten Versuch
    }
  }
  await meldeOffen();
  document.dispatchEvent(new CustomEvent("sync:fertig"));
}

async function anzahlOffen() {
  return (await LocalDB.outboxAlle()).length;
}
async function meldeOffen() {
  const n = await anzahlOffen();
  document.dispatchEvent(new CustomEvent("outbox:offen", { detail: { offen: n } }));
}

// Manuell anstossen (Tipp auf den Status-Punkt): pruefen + offene senden.
async function jetztSynchronisieren() {
  const ok = await pingServer();
  if (ok) await flushOutbox();
  return ok;
}

// ------------------------------------------------------------------ Start ----
window.addEventListener("online", () => pingServer());
window.addEventListener("offline", () => statusSetzen(false));
// OHNE Neuladen aktualisieren: sobald die App wieder sichtbar wird oder Fokus
// bekommt, sofort neu pruefen (das passiert beim Zurueckkehren zur App nach dem
// Ausschalten des Flugmodus) -> Status wird dynamisch grün und Sync laeuft an.
document.addEventListener("visibilitychange", () => { if (!document.hidden) pingServer(); });
window.addEventListener("focus", () => pingServer());
setInterval(pingServer, 10000);
pingServer();          // sofort einmal pruefen
meldeOffen();          // Badge initialisieren

window.Sync = {
  apiOffline, spiegelRoh, frischHolen, senden, flushOutbox, jetztSynchronisieren,
  pingServer, prefetchAlles, anzahlOffen,
  get serverOnline() { return serverErreichbar; },
  get letzterFehler() { return letzterFehler; },
};
