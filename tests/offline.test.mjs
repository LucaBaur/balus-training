// Offline-Tests fuer die Sync-Schicht (static/sync.js).
// Laedt sync.js in einem vm-Kontext mit gefaelschten Browser-Globals und prueft
// vor allem TIMING (gecachter GET muss sofort antworten, auch wenn das Netz
// haengt) und das Outbox-Verhalten (offline puffern, online senden, idempotent).
// Start: node tests/offline.test.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(dir, "..", "static", "sync.js"), "utf8");

function makeLocalDB() {
  const stores = { responses: new Map(), outbox: new Map() };
  const kp = (s) => (s === "responses" ? "pfad" : s === "outbox" ? "token" : "id");
  return {
    async get(store, key) { return stores[store].get(key) || null; },
    async put(store, val) { stores[store].set(val[kp(store)], val); return val; },
    async getAlle(store) { return [...(stores[store] || new Map()).values()]; },
    async ersetzeAlle(store, list) { stores[store] = new Map((list || []).map((x) => [x.id, x])); },
    async outboxAlle() { return [...stores.outbox.values()]; },
    async outboxHinzu(e) { stores.outbox.set(e.token, e); },
    async outboxEntfernen(t) { stores.outbox.delete(t); },
    _stores: stores,
  };
}

function ladeSync({ navigatorOnline = true, fetchImpl, localdb }) {
  const win = { addEventListener() {} };
  const sandbox = {
    window: win,
    navigator: { onLine: navigatorOnline },
    fetch: fetchImpl,
    crypto: { randomUUID: () => "tok-" + Math.random().toString(16).slice(2) },
    document: { dispatchEvent() {}, addEventListener() {}, hidden: false },
    LocalDB: localdb,
    setTimeout, clearTimeout, setInterval, clearInterval, console,
    CustomEvent: class { constructor(t, o) { this.type = t; this.detail = o && o.detail; } },
    Promise, Error, Date, Math, JSON,
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "sync.js" });
  return { Sync: win.Sync, sandbox };
}

const hang = () => new Promise(() => {});
// echtes fetch liefert IMMER ein Promise -> Fake ebenso (sonst bricht .then()).
const okResp = () => Promise.resolve({ ok: true, status: 200, json: async () => ({}), text: async () => "" });
const delay = (ms) => new Promise((r) => setTimeout(r, ms));

let fails = 0;
async function test(name, fn) {
  try { await fn(); console.log("  ok   " + name); }
  catch (e) { fails++; console.log("  FAIL " + name + "\n         " + e.message); }
}

async function main() {
  console.log("Offline-Sync-Tests");

  // 1) Regressionstest: Cache da -> sofort, auch wenn Netz haengt.
  await test("cached GET liefert < 500ms trotz haengendem Netz", async () => {
    const db = makeLocalDB();
    const pfad = "/api/spieler/5/spiele";
    await db.put("responses", { pfad, daten: { marker: 42 }, ts: 0 });
    const { Sync } = ladeSync({ fetchImpl: hang, localdb: db });
    const t0 = Date.now();
    const res = await Sync.apiOffline(pfad);
    const dt = Date.now() - t0;
    assert.strictEqual(res.marker, 42);
    assert.ok(dt < 500, `zu langsam: ${dt}ms`);
  });

  // 2) offline + kein Cache -> schnelle Ablehnung
  await test("offline ohne Cache lehnt < 500ms ab", async () => {
    const db = makeLocalDB();
    const { Sync } = ladeSync({ navigatorOnline: false, fetchImpl: hang, localdb: db });
    const t0 = Date.now();
    let threw = false;
    try { await Sync.apiOffline("/api/unbekannt"); } catch { threw = true; }
    const dt = Date.now() - t0;
    assert.ok(threw && dt < 500, `threw=${threw} dt=${dt}ms`);
  });

  // 3) spiegelRoh liefert Cache OHNE fetch
  await test("spiegelRoh liefert Cache ohne fetch", async () => {
    const db = makeLocalDB();
    await db.put("responses", { pfad: "/api/rangliste", daten: [{ id: 9 }], ts: 0 });
    let calls = 0;
    const { Sync } = ladeSync({ fetchImpl: () => { calls++; return hang(); }, localdb: db });
    calls = 0; // Start-Ping ignorieren
    const res = await Sync.spiegelRoh("/api/rangliste");
    assert.strictEqual(res[0].id, 9);
    assert.strictEqual(calls, 0, "spiegelRoh darf keinen fetch ausloesen");
  });

  // 4) senden OFFLINE -> puffert in Outbox (gesendet=false), Token im Body
  await test("senden offline puffert in Outbox", async () => {
    const db = makeLocalDB();
    const { Sync } = ladeSync({ navigatorOnline: false, fetchImpl: hang, localdb: db });
    const r = await Sync.senden("/api/spiel", { ergebnis: "A", token: "tok1" });
    assert.strictEqual(r.gesendet, false, "darf offline nicht als gesendet gelten");
    const eintrag = await db.get("outbox", "tok1");
    assert.ok(eintrag && eintrag.body.token === "tok1", "muss mit Token in der Outbox liegen");
  });

  // 5) senden mit erreichbarem Server -> gesendet, Outbox leer
  await test("senden online sendet und leert die Outbox", async () => {
    const db = makeLocalDB();
    let posts = 0;
    const fetchImpl = (url, opt) => { if (opt && opt.method === "POST") posts++; return okResp(); };
    const { Sync } = ladeSync({ fetchImpl, localdb: db });
    await Sync.pingServer();
    await delay(20);
    const r = await Sync.senden("/api/spiel", { ergebnis: "A", token: "tok2" });
    assert.strictEqual(r.gesendet, true);
    assert.strictEqual((await db.outboxAlle()).length, 0, "Outbox muss leer sein");
    assert.ok(posts >= 1, "mindestens ein POST");
  });

  // 6) fehlgeschlagener Send bleibt in Outbox (idempotent nachholbar)
  await test("fehlgeschlagener Send bleibt in Outbox", async () => {
    const db = makeLocalDB();
    const fetchImpl = (url, opt) => (opt && opt.method === "POST")
      ? Promise.reject(new Error("netz weg")) : okResp();
    const { Sync } = ladeSync({ fetchImpl, localdb: db });
    await Sync.pingServer();          // Server "erreichbar" (Ping ok)
    await delay(20);
    const r = await Sync.senden("/api/spiel", { ergebnis: "A", token: "tok3" });
    assert.strictEqual(r.gesendet, false);
    const eintrag = await db.get("outbox", "tok3");
    assert.ok(eintrag && eintrag.body.token === "tok3", "muss fuer spaeteren Sync liegen bleiben");
  });

  // 7) Kompletter Ablauf: offline eintragen -> online -> automatisch gesendet.
  await test("offline eingereiht, dann online -> jetztSynchronisieren sendet", async () => {
    const db = makeLocalDB();
    let posts = 0;
    let netzAn = false;
    const fetchImpl = (url, opt) => {
      if (!netzAn) return Promise.reject(new Error("offline"));
      if (opt && opt.method === "POST") posts++;
      return okResp();
    };
    const { Sync } = ladeSync({ navigatorOnline: false, fetchImpl, localdb: db });
    const r1 = await Sync.senden("/api/spiel", { ergebnis: "A", token: "tokZ" });
    assert.strictEqual(r1.gesendet, false, "offline muss puffern");
    assert.ok(await db.get("outbox", "tokZ"), "muss in der Outbox liegen");
    netzAn = true; // Flugmodus aus
    const ok = await Sync.jetztSynchronisieren();
    assert.strictEqual(ok, true, "Server jetzt erreichbar");
    assert.strictEqual((await db.outboxAlle()).length, 0, "Outbox muss geleert sein");
    assert.ok(posts >= 1, "Spiel muss gesendet worden sein");
  });

  // 8) Server antwortet mit Fehler -> bleibt ERREICHBAR (nicht offline), Eintrag
  //    bleibt liegen, Fehlertext wird erfasst.
  await test("Server-Fehlerantwort: online bleiben, Fehler erfasst", async () => {
    const db = makeLocalDB();
    const fetchImpl = (url, opt) => (opt && opt.method === "POST")
      ? Promise.resolve({ ok: false, status: 400, text: async () => "boese daten", json: async () => ({}) })
      : okResp();
    const { Sync } = ladeSync({ fetchImpl, localdb: db });
    await Sync.pingServer();
    await delay(20);
    const r = await Sync.senden("/api/spiel", { ergebnis: "A", token: "tokE" });
    assert.strictEqual(r.gesendet, false, "darf nicht als gesendet gelten");
    assert.strictEqual(Sync.serverOnline, true, "Server ist erreichbar -> nicht offline");
    assert.strictEqual(Sync.letzterFehler, "boese daten", "Fehlertext muss erfasst sein");
    assert.ok(await db.get("outbox", "tokE"), "Eintrag muss liegen bleiben");
  });

  console.log(fails ? `\n${fails} Test(s) FEHLGESCHLAGEN\n` : "\nAlle Tests bestanden\n");
  process.exit(fails ? 1 : 0);
}
main();
