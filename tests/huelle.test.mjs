// Prueft, dass das Frontend aus ES-Modulen zusammenpasst. Start: node tests/huelle.test.mjs
//   1. Jedes Modul (static/main.js, core/, features/) steht in der Huelle des Service Workers (sw.js);
//      sonst fehlt es offline - und HUELLE enthaelt keine Datei, die es nicht gibt.
//   2. Jeder Import zeigt auf eine vorhandene Datei, und der importierte Name wird dort exportiert.
//   3. index.html und sw.js verweisen mit derselben ?v= auf main.js.
//   4. Klassische Skripte (index.html) und HUELLE haben dieselben ?v=.
import fs from "node:fs";
import path from "node:path";

const STATIC = new URL("../static/", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
let fehler = 0;
function check(name, ok, detail = "") {
  console.log((ok ? "ok   " : "FEHLER ") + name + (ok ? "" : "  -> " + detail));
  if (!ok) fehler++;
}

// ---- Module einsammeln ------------------------------------------------------
const module_ = ["main.js"];
for (const ordner of ["core", "features"])
  for (const f of fs.readdirSync(path.join(STATIC, ordner)).sort()) if (f.endsWith(".js")) module_.push(`${ordner}/${f}`);

// ---- 1. Huelle ---------------------------------------------------------------
const sw = fs.readFileSync(path.join(STATIC, "sw.js"), "utf8");
const huelle = [...sw.match(/const HUELLE = \[([\s\S]*?)\];/)[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
const huelleOhneQuery = huelle.map((h) => h.split("?")[0]);

const fehlendInHuelle = module_.filter((m) => !huelleOhneQuery.includes("/" + m));
check(`Alle ${module_.length} Module stehen in der Huelle`, fehlendInHuelle.length === 0, fehlendInHuelle.join(", "));

const unbekannt = huelleOhneQuery.filter((h) => h !== "/" && !h.startsWith("/portraits/") && !fs.existsSync(path.join(STATIC, h)));
check("Jeder Eintrag der Huelle ist eine vorhandene Datei", unbekannt.length === 0, unbekannt.join(", "));

// ---- 2. Importe und Exporte --------------------------------------------------
const exporte = new Map();
const importe = [];
for (const m of module_) {
  const src = fs.readFileSync(path.join(STATIC, m), "utf8");
  const namen = new Set([...src.matchAll(/^export\s+(?:async\s+)?(?:function\*?|const|let|class)\s+([A-Za-z_$][\w$]*)/gm)].map((x) => x[1]));
  exporte.set(m, namen);
  for (const x of src.matchAll(/^import\s*\{([^}]*)\}\s*from\s*"([^"]+)";/gm))
    importe.push({ von: m, ziel: path.posix.normalize(path.posix.join(path.posix.dirname(m), x[2])), namen: x[1].split(",").map((s) => s.trim()).filter(Boolean) });
}
const kaputt = [];
for (const i of importe) {
  const e = exporte.get(i.ziel);
  if (!e) { kaputt.push(`${i.von}: Datei ${i.ziel} fehlt`); continue; }
  for (const n of i.namen) if (!e.has(n)) kaputt.push(`${i.von}: ${n} wird von ${i.ziel} nicht exportiert`);
}
check(`${importe.length} Importe zeigen auf vorhandene Exporte`, kaputt.length === 0, kaputt.join("; "));

// ---- 2b. Erreichbarkeit: jedes Modul muss von main.js aus (ueber Importe) geladen werden -------------
// Module ohne Exporte (nur Seiteneffekte wie Klick-Handler) fallen sonst unbemerkt weg.
const graph = new Map(module_.map((m) => {
  const src = fs.readFileSync(path.join(STATIC, m), "utf8");
  const ziele = [...src.matchAll(/^import\s*(?:\{[^}]*\}\s*from\s*)?"([^"]+)";/gm)]
    .map((x) => path.posix.normalize(path.posix.join(path.posix.dirname(m), x[1])));
  return [m, ziele];
}));
const erreicht = new Set(["main.js"]);
for (const stapel = ["main.js"]; stapel.length;)
  for (const z of graph.get(stapel.pop()) || []) if (!erreicht.has(z)) { erreicht.add(z); stapel.push(z); }
const verwaist = module_.filter((m) => !erreicht.has(m));
check("Jedes Modul wird von main.js aus geladen", verwaist.length === 0, verwaist.join(", "));

// ---- 3./4. ?v= in index.html und Huelle -----------------------------------------
const html = fs.readFileSync(path.join(STATIC, "index.html"), "utf8");
const mainHtml = html.match(/<script type="module" src="\/main\.js\?v=(\d+)"/);
const mainSw = huelle.find((h) => h.startsWith("/main.js?v="));
check("index.html laedt main.js als Modul", !!mainHtml);
check("main.js: gleiche ?v= in index.html und Huelle", !!mainHtml && mainSw === "/main.js?v=" + mainHtml[1], `${mainHtml?.[1]} vs ${mainSw}`);

const klassisch = [...html.matchAll(/<(?:script|link)[^>]+(?:src|href)="(\/[^"]+\.(?:js|css)\?v=\d+)"/g)].map((m) => m[1]).filter((u) => !u.startsWith("/main.js"));
const nichtInHuelle = klassisch.filter((u) => !huelle.includes(u));
check("Klassische Skripte/Styles: gleiche ?v= in index.html und Huelle", nichtInHuelle.length === 0, nichtInHuelle.join(", "));

if (fehler) { console.error(`\n${fehler} Fehler`); process.exit(1); }
console.log("\nalles ok");
