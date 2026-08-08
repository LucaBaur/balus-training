"use strict";

// ============================================================================
//  local-db.js — Lokaler Spiegel der Server-Daten (IndexedDB)
// ----------------------------------------------------------------------------
//  Das Handy hält eine Kopie der wichtigsten Daten, damit Lesen offline sofort
//  funktioniert. Die WAHRHEIT bleibt die SQLite am Server; hier steht nur ein
//  Spiegel + eine "Outbox" mit noch nicht gesendeten Schreibvorgaengen.
//
//  Bewusst ohne Fremdbibliothek (reines IndexedDB), damit die PWA klein bleibt
//  und ohne Netz ladbar ist. Gerüst — Stores stehen, Feinschliff folgt Phase 1.
// ============================================================================

const DB_NAME = "balu";
const DB_VERSION = 2;

// Object-Stores: gespiegelte Server-Daten + Meta + Outbox.
//   keyPath: Primaerschluessel je Datensatz.
const STORES = {
  spieler: { keyPath: "id" },
  spiele: { keyPath: "id" },
  rangliste: { keyPath: "id" },
  trainings: { keyPath: "id" }, // Anytype-Trainings (mit Zusagen)
  meta: { keyPath: "schluessel" }, // z.B. letzter Sync-Zeitpunkt
  outbox: { keyPath: "token", autoIncrement: false }, // offene Schreibvorgaenge
  responses: { keyPath: "pfad" }, // roher GET-Cache pro Pfad -> offline lesbar
};

let _db = null;

// IndexedDB oeffnen / migrieren. Idempotent — mehrfacher Aufruf teilt sich eine
// Verbindung.
function oeffneDB() {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      for (const [name, opt] of Object.entries(STORES)) {
        if (!db.objectStoreNames.contains(name)) {
          db.createObjectStore(name, opt);
        }
      }
    };
    req.onsuccess = () => {
      _db = req.result;
      resolve(_db);
    };
    req.onerror = () => reject(req.error);
  });
}

function _tx(store, modus) {
  return oeffneDB().then((db) => db.transaction(store, modus).objectStore(store));
}

// -------------------------------------------------------------- Lesen/Schreiben
async function put(store, wert) {
  const os = await _tx(store, "readwrite");
  return new Promise((resolve, reject) => {
    const r = os.put(wert);
    r.onsuccess = () => resolve(wert);
    r.onerror = () => reject(r.error);
  });
}

// Ganze Liste ersetzen (z.B. nach einem erfolgreichen GET vom Server).
async function ersetzeAlle(store, liste) {
  const os = await _tx(store, "readwrite");
  return new Promise((resolve, reject) => {
    os.clear().onsuccess = () => {
      for (const w of liste || []) os.put(w);
    };
    os.transaction.oncomplete = () => resolve(liste);
    os.transaction.onerror = () => reject(os.transaction.error);
  });
}

async function getAlle(store) {
  const os = await _tx(store, "readonly");
  return new Promise((resolve, reject) => {
    const r = os.getAll();
    r.onsuccess = () => resolve(r.result || []);
    r.onerror = () => reject(r.error);
  });
}

async function get(store, key) {
  const os = await _tx(store, "readonly");
  return new Promise((resolve, reject) => {
    const r = os.get(key);
    r.onsuccess = () => resolve(r.result || null);
    r.onerror = () => reject(r.error);
  });
}

async function loesche(store, key) {
  const os = await _tx(store, "readwrite");
  return new Promise((resolve, reject) => {
    const r = os.delete(key);
    r.onsuccess = () => resolve();
    r.onerror = () => reject(r.error);
  });
}

// ------------------------------------------------------------------- Outbox ----
//  Ein offener Schreibvorgang: { token, pfad, methode, body, ts }.
//  token = Idempotenz-Schluessel (bei Spielen bereits vorhanden) → der Server
//  darf denselben Eintrag mehrfach empfangen, ohne doppelt zu zaehlen.
async function outboxHinzu(eintrag) {
  return put("outbox", eintrag);
}
async function outboxAlle() {
  return getAlle("outbox");
}
async function outboxEntfernen(token) {
  return loesche("outbox", token);
}

// Als globales Objekt bereitstellen (kein Bundler im Projekt).
window.LocalDB = {
  oeffneDB,
  put,
  get,
  getAlle,
  ersetzeAlle,
  loesche,
  outboxHinzu,
  outboxAlle,
  outboxEntfernen,
  STORES,
};
