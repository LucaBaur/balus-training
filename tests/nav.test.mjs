// Tests fuer die Navigation nach Rolle (static/nav.js).
// Spielerin: fuenf Reiter (Home, Termine, Videos, Playbook, Mannschaft), Profil hinter dem Kreis oben rechts.
// Trainer: die bekannten fuenf Reiter. Start: node tests/nav.test.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(dir, "..", "static", "nav.js"), "utf8");

function lade() {
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "nav.js" });
  return sandbox.window.NavKonfig;
}
const Nav = lade();

let fails = 0;
function test(name, fn) {
  try { fn(); console.log("ok   " + name); }
  catch (e) { fails++; console.log("FEHLER " + name + "\n     " + e.message); }
}
const labels = (liste) => liste.map((o) => o.label);
const keys = (liste) => liste.map((o) => o.key);

test("Spielerin mit Profil: fuenf Reiter", () => {
  const t = Nav.tabs("spieler", true);
  assert.deepEqual(labels(t), ["Home", "Termine", "Videos", "Playbook", "Mannschaft"]);
  assert.deepEqual(keys(t), ["home", "training", "videos", "taktik", "mannschaft"]);
});

test("Spielerin ohne Profil: keine Videos und keine Mannschaft (es gibt nichts Eigenes zu zeigen)", () => {
  assert.deepEqual(labels(Nav.tabs("spieler", false)), ["Home", "Termine", "Playbook"]);
});

test("Trainer: Home, Training, Team, Taktik, Saison - mit und ohne Profil", () => {
  for (const profil of [true, false]) {
    assert.deepEqual(labels(Nav.tabs("trainer", profil)), ["Home", "Training", "Team", "Taktik", "Saison"]);
  }
});

test("Aemter: Spielerin im Reiter Mannschaft, Trainer unter Saison - dieselben Seiten", () => {
  const s = Nav.finde("spieler", true, "mannschaft", "listen");
  assert.equal(s.unter.view, "view-listen");
  assert.deepEqual(labels(Nav.subnav(s.ober)), ["Ämter", "Listen"]);
  const t = Nav.finde("trainer", true, "saison", "aemter");
  assert.equal(t.unter.view, "view-aemter");
  assert.ok(labels(Nav.subnav(t.ober)).includes("Listen"));
  assert.equal(Nav.finde("trainer", true, "mannschaft", "aemter"), null);   // sechs Reiter waeren zu viel
  assert.equal(Nav.finde("spieler", true, "saison", "aemter"), null);       // Saison bleibt Trainer-Sache
});

test("jeder Reiter hat ein Symbol", () => {
  for (const rolle of ["spieler", "trainer"]) {
    for (const o of Nav.tabs(rolle, true)) assert.ok(o.icon && typeof o.icon === "string", `${rolle}/${o.key}`);
  }
});

test("'Ich' ist kein Reiter, aber erreichbar (Profil-Menue)", () => {
  assert.ok(!keys(Nav.tabs("spieler", true)).includes("ich"));
  const ziel = Nav.finde("spieler", true, "ich", "todo");
  assert.ok(ziel && ziel.unter.key === "todo" && ziel.unter.view === "view-todo");
  assert.equal(Nav.finde("spieler", false, "ich", "ich"), null);     // ohne Profil gibt es nichts
  assert.ok(Nav.finde("trainer", true, "ich", "ich"));               // Trainerin, die mitspielt
});

test("Home der Spielerin hat keine Unterleiste, Liga bleibt erreichbar", () => {
  const home = Nav.finde("spieler", true, "home", "home").ober;
  assert.deepEqual(labels(Nav.subnav(home, "spieler")), ["Übersicht"]);
  const liga = Nav.finde("spieler", true, "home", "liga");
  assert.ok(liga && liga.unter.view === "view-liga");
});

test("Home des Trainers zeigt Übersicht und Liga", () => {
  const home = Nav.finde("trainer", true, "home", "home").ober;
  assert.deepEqual(labels(Nav.subnav(home, "trainer")), ["Übersicht", "Liga"]);
});

test("Termine der Spielerin: Termine und Aufstellung, ohne Trainer-Seiten", () => {
  const o = Nav.finde("spieler", true, "training", "trainings").ober;
  assert.equal(o.label, "Termine");
  assert.deepEqual(labels(Nav.subnav(o, "spieler")), ["Termine", "Aufstellung"]);
  assert.equal(Nav.finde("spieler", true, "training", "coach").unter.key, "trainings");   // Fallback auf den ersten
});

test("Training des Trainers hat fuenf Unterpunkte", () => {
  const o = Nav.finde("trainer", true, "training", "trainings").ober;
  assert.deepEqual(labels(Nav.subnav(o, "trainer")), ["Termine", "Aufstellung", "Einteilung", "Übungen", "Coach"]);
});

test("Playbook der Spielerin ohne Gegnercheck, Trainer mit", () => {
  const s = Nav.finde("spieler", true, "taktik", "playbook").ober;
  assert.equal(s.label, "Playbook");
  assert.deepEqual(labels(Nav.subnav(s, "spieler")), ["Playbook"]);
  const t = Nav.finde("trainer", true, "taktik", "playbook").ober;
  assert.deepEqual(labels(Nav.subnav(t, "trainer")), ["Playbook", "Gegner"]);
});

test("Spielerin kommt nicht an Team und Saison", () => {
  assert.equal(Nav.finde("spieler", true, "team", "rangliste"), null);
  assert.equal(Nav.finde("spieler", true, "saison", "orga"), null);
});

test("Videos der Spielerin: ein Unterpunkt, eigene View", () => {
  const f = Nav.finde("spieler", true, "videos", "videos");
  assert.equal(f.unter.view, "view-videos");
  assert.equal(Nav.finde("trainer", false, "videos", "videos"), null);   // Trainer nutzt Team -> Videos
  assert.ok(Nav.finde("trainer", false, "team", "videos"));
});

test("alle Views heissen view-* und Schluessel sind je Ebene eindeutig", () => {
  for (const o of Nav.NAV) {
    const ks = o.unter.map((u) => u.key);
    assert.equal(new Set(ks).size, ks.length, `doppelter Unterpunkt in ${o.key}`);
    for (const u of o.unter) assert.match(u.view, /^view-/);
  }
});

if (fails) { console.log(`\n${fails} Test(s) fehlgeschlagen`); process.exit(1); }
console.log("\nAlle Tests bestanden");
