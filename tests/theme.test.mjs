// Tests fuer die Darstellung hell/dunkel (static/theme.js).
// Start: node tests/theme.test.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(dir, "..", "static", "theme.js"), "utf8");

function lade() {
  const sandbox = { window: {}, console };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "theme.js" });
  return sandbox.window.Theme;
}
const Theme = lade();

function fakeDoc(mitMeta = true) {
  const meta = { content: "" };
  return {
    meta,
    documentElement: { dataset: {}, style: {} },
    querySelector: (sel) => (mitMeta && sel.includes("theme-color") ? meta : null),
  };
}
const speicher = (start = {}) => {
  const d = { ...start };
  return { getItem: (k) => (k in d ? d[k] : null), setItem: (k, v) => { d[k] = String(v); }, d };
};

let fails = 0;
function test(name, fn) {
  try { fn(); console.log("ok   " + name); }
  catch (e) { fails++; console.log("FEHLER " + name + "\n     " + e.message); }
}

test("normiere kennt nur auto, hell, dunkel", () => {
  assert.equal(Theme.normiere("hell"), "hell");
  assert.equal(Theme.normiere("dunkel"), "dunkel");
  assert.equal(Theme.normiere("auto"), "auto");
  assert.equal(Theme.normiere("rosa"), "auto");
  assert.equal(Theme.normiere(null), "auto");
  assert.equal(Theme.normiere(undefined), "auto");
});

test("effektiv: Auto folgt dem System, sonst gilt die Wahl", () => {
  assert.equal(Theme.effektiv("auto", true), "dunkel");
  assert.equal(Theme.effektiv("auto", false), "hell");
  assert.equal(Theme.effektiv("hell", true), "hell");
  assert.equal(Theme.effektiv("dunkel", false), "dunkel");
  assert.equal(Theme.effektiv("quatsch", true), "dunkel");     // ungueltig = auto
});

test("laden/speichern: Rundlauf ueber den Speicher", () => {
  const s = speicher();
  assert.equal(Theme.laden(s), "auto");
  assert.equal(Theme.speichern(s, "dunkel"), "dunkel");
  assert.equal(s.d.darstellung, "dunkel");
  assert.equal(Theme.laden(s), "dunkel");
  assert.equal(Theme.speichern(s, "murks"), "auto");
  assert.equal(Theme.laden(speicher({ darstellung: "murks" })), "auto");
});

test("kaputter Speicher wirft nie (privates Fenster, gesperrte Daten)", () => {
  const kaputt = { getItem() { throw new Error("gesperrt"); }, setItem() { throw new Error("gesperrt"); } };
  assert.equal(Theme.laden(kaputt), "auto");
  assert.equal(Theme.speichern(kaputt, "hell"), "hell");
  assert.equal(Theme.laden(null), "auto");
  assert.equal(Theme.speichern(null, "hell"), "hell");
});

test("anwenden setzt data-theme und die Farbe der Systemleiste", () => {
  const d = fakeDoc();
  assert.equal(Theme.anwenden(d, "dunkel", false), "dunkel");
  assert.equal(d.documentElement.dataset.theme, "dunkel");
  assert.equal(d.meta.content, Theme.FARBEN.dunkel);
  assert.equal(Theme.anwenden(d, "auto", false), "hell");
  assert.equal(d.documentElement.dataset.theme, "hell");
  assert.equal(d.meta.content, Theme.FARBEN.hell);
  assert.notEqual(Theme.FARBEN.hell, Theme.FARBEN.dunkel);
});

test("anwenden kommt ohne theme-color-Tag klar", () => {
  const d = fakeDoc(false);
  assert.equal(Theme.anwenden(d, "auto", true), "dunkel");
  assert.equal(d.documentElement.dataset.theme, "dunkel");
});

if (fails) { console.log(`\n${fails} Test(s) fehlgeschlagen`); process.exit(1); }
console.log("\nAlle Tests bestanden");
