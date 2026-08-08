// Tests fuer die lokale Team-Generierung (static/teams-local.js).
// Prueft: gleiche Groessen, faire Aufteilung, Torhueter-Verteilung, grosse Gruppe.
// Start: node tests/teams.test.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(dir, "..", "static", "teams-local.js"), "utf8");

function ladeTeams() {
  const sandbox = { window: {}, Array, Math, Set, Number, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "teams-local.js" });
  return sandbox.window.TeamsLokal;
}

const schnitt = (t) => t.reduce((s, p) => s + p.elo, 0) / t.length;
const feld = (id, elo) => ({ id, elo, position: "Feld" });
const tor = (id, elo) => ({ id, elo, position: "Tor" });

let fails = 0;
async function test(name, fn) {
  try { await fn(); console.log("  ok   " + name); }
  catch (e) { fails++; console.log("  FAIL " + name + "\n         " + e.message); }
}

async function main() {
  console.log("Team-Generierungs-Tests");
  const T = ladeTeams();

  await test("gleiche ELOs -> ausgeglichen, Groessen n/2", async () => {
    const sp = [feld(1, 1000), feld(2, 1000), feld(3, 1000), feld(4, 1000)];
    const [a, b] = T.generiere(sp);
    assert.strictEqual(a.length, 2);
    assert.strictEqual(b.length, 2);
    assert.strictEqual(schnitt(a), schnitt(b));
  });

  await test("alle Spielerinnen bleiben erhalten (ungerade Zahl)", async () => {
    const sp = [feld(1, 1200), feld(2, 900), feld(3, 1000), feld(4, 1100), feld(5, 950)];
    const [a, b] = T.generiere(sp);
    assert.strictEqual(a.length + b.length, 5);
    assert.ok(Math.abs(a.length - b.length) <= 1, "Groessen duerfen sich max. um 1 unterscheiden");
    const ids = [...a, ...b].map((p) => p.id).sort();
    assert.deepStrictEqual(ids, [1, 2, 3, 4, 5]);
  });

  await test("bei >= 2 Torhueterinnen bekommt jedes Team eine", async () => {
    const sp = [tor(1, 1000), tor(2, 1000), feld(3, 1100), feld(4, 900), feld(5, 1050), feld(6, 950)];
    const [a, b] = T.generiere(sp);
    assert.ok(a.some((p) => p.position === "Tor"), "Team A braucht eine TW");
    assert.ok(b.some((p) => p.position === "Tor"), "Team B braucht eine TW");
  });

  await test("faire Aufteilung minimiert die Differenz", async () => {
    // 1600,1000,1000,400 -> optimal {1600,400} vs {1000,1000}, Differenz 0
    const sp = [feld(1, 1600), feld(2, 1000), feld(3, 1000), feld(4, 400)];
    const [a, b] = T.generiere(sp);
    assert.strictEqual(Math.abs(schnitt(a) - schnitt(b)), 0);
  });

  await test("grosse Gruppe (n=24) liefert gueltige Aufteilung ohne Absturz", async () => {
    const sp = Array.from({ length: 24 }, (_, i) => feld(i + 1, 800 + i * 15));
    const [a, b] = T.generiere(sp);
    assert.strictEqual(a.length + b.length, 24);
    assert.ok(Math.abs(a.length - b.length) <= 1);
  });

  await test("drei Teams: alle bleiben drin, Groessen fast gleich", async () => {
    const sp = Array.from({ length: 15 }, (_, i) => feld(i + 1, 850 + i * 20));
    const t = T.generiereN(sp, 3);
    assert.strictEqual(t.length, 3);
    assert.strictEqual(t.flat().length, 15);
    assert.strictEqual(new Set(t.flat().map((p) => p.id)).size, 15);
    const gr = t.map((x) => x.length);
    assert.ok(Math.max(...gr) - Math.min(...gr) <= 1, "Groessen: " + gr);
  });

  await test("vier Teams: Staerke-Spanne bleibt klein", async () => {
    const sp = Array.from({ length: 16 }, (_, i) => feld(i + 1, 800 + i * 25));
    const t = T.generiereN(sp, 4);
    assert.strictEqual(t.length, 4);
    assert.strictEqual(t.flat().length, 16);
    const s = t.map(schnitt);
    assert.ok(Math.max(...s) - Math.min(...s) < 40, "Spanne zu gross: " + s.join(", "));
  });

  await test("Torhueterinnen werden auf die Teams verteilt", async () => {
    const sp = [tor(1, 1000), tor(2, 990), tor(3, 980),
                ...Array.from({ length: 9 }, (_, i) => feld(i + 4, 900 + i * 20))];
    const t = T.generiereN(sp, 3);
    assert.strictEqual(t.filter((x) => x.some((p) => p.position === "Tor")).length, 3);
  });

  await test("generiereN(…, 2) verhaelt sich wie generiere", async () => {
    const sp = [feld(1, 1600), feld(2, 1000), feld(3, 1000), feld(4, 400)];
    const t = T.generiereN(sp, 2);
    assert.strictEqual(t.length, 2);
    assert.strictEqual(Math.abs(schnitt(t[0]) - schnitt(t[1])), 0);
  });

  console.log(fails ? `\n${fails} Test(s) FEHLGESCHLAGEN\n` : "\nAlle Tests bestanden\n");
  process.exit(fails ? 1 : 0);
}
main();
