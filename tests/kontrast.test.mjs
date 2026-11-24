// Prueft die Lesbarkeit der Farben in Hell UND Dunkel (WCAG 2.x). Start: node tests/kontrast.test.mjs
// Die Werte kommen aus den echten Quellen: Tokens aus static/style.css, Wappenfarben aus
// core/portraits.js, Teamfarben aus features/einteilung.js - der Test kann also nicht von der App abweichen.
//   Text 4,5:1 | Grafik (Linien, Punkte, Balken, Ringe) 3:1
// Bereiche: --tvg-text (Text auf Karten), Ampel, Aufstellungsfeld, Spielzug-Feld, Balken/Diagramme.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const STATIC = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "static");
const lies = (p) => fs.readFileSync(path.join(STATIC, p), "utf8");
const css = lies("style.css");

let fehler = 0;
function check(name, ok, detail = "") {
  console.log((ok ? "ok   " : "FEHLER ") + name + (ok ? "" : "  -> " + detail));
  if (!ok) fehler++;
}

// ---- Tokens einlesen --------------------------------------------------------------
const ohneKommentar = css.replace(/\/\*[\s\S]*?\*\//g, "");
function deklarationen(block) {
  const m = {};
  for (const d of block.split(";")) {
    const i = d.indexOf(":");
    if (i < 0) continue;
    const k = d.slice(0, i).trim();
    if (k.startsWith("--")) m[k] = d.slice(i + 1).trim();
  }
  return m;
}
const blockNach = (kopf) => {
  const i = ohneKommentar.indexOf(kopf);
  if (i < 0) throw new Error("Block nicht gefunden: " + kopf);
  return ohneKommentar.slice(ohneKommentar.indexOf("{", i) + 1, ohneKommentar.indexOf("}", i));
};
const HELL = deklarationen(blockNach(":root {"));
const DUNKEL = { ...HELL, ...deklarationen(blockNach(':root[data-theme="dark"]')) };
const MODI = { hell: HELL, dunkel: DUNKEL };

// ---- Farben ---------------------------------------------------------------------------
function farbe(wert, tokens, tiefe = 0) {
  wert = wert.trim();
  const v = wert.match(/^var\((--[\w-]+)\)$/);
  if (v) {
    if (!(v[1] in tokens) || tiefe > 8) throw new Error("Token fehlt: " + v[1]);
    return farbe(tokens[v[1]], tokens, tiefe + 1);
  }
  let h = wert.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (h) {
    let x = h[1];
    if (x.length === 3) x = [...x].map((c) => c + c).join("");
    return [0, 2, 4].map((i) => parseInt(x.slice(i, i + 2), 16)).concat(1);
  }
  const r = wert.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$/);
  if (r) return [+r[1], +r[2], +r[3], r[4] === undefined ? 1 : +r[4]];
  if (wert === "transparent") return [0, 0, 0, 0];
  throw new Error("Farbe nicht lesbar: " + wert);
}
const ueber = (oben, unten) => {                       // oben (mit Alpha) auf unten legen
  const a = oben[3];
  return [0, 1, 2].map((i) => Math.round(oben[i] * a + unten[i] * (1 - a))).concat(1);
};
const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
const kontrast = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

// Prueft ein Paar in beiden Modi. fg/bg: Token ("--karte"), Farbe ("#fff") oder Funktion (tokens) => Farbe.
function paar(name, fg, bg, ziel, modi = ["hell", "dunkel"]) {
  for (const m of modi) {
    const t = MODI[m];
    const f = (x) => (typeof x === "function" ? x(t) : farbe(x.startsWith("--") ? `var(${x})` : x, t));
    try {
      const v = kontrast(f(fg), ueber(f(bg), [255, 255, 255, 1]));
      check(`${m.padEnd(6)} ${v.toFixed(2).padStart(5)}:1 (>= ${ziel})  ${name}`, v >= ziel, `nur ${v.toFixed(2)}:1`);
    } catch (e) { check(`${m} ${name}`, false, e.message); }
  }
}

// ---- 1. Text in --tvg-text (frueher --tvg-900: im Dunkelmodus unsichtbar) -----------------
paar("--tvg-text auf Karte (Kasse, Aemter, Listen, To-Dos)", "--tvg-text", "--karte", 4.5);
paar("--tvg-text auf Chip-Flaeche (--tint)", "--tvg-text", "--tint", 4.5);
const falscherText = [...ohneKommentar.matchAll(/(?:^|[;{\s])(?:color|fill):\s*var\(--tvg-900\)/g)].length;
check("--tvg-900 wird nirgends als Textfarbe benutzt (nur --tvg-text)", falscherText === 0, falscherText + " Stellen");

paar("Abmelden-Knoepfe im Profil-Menue (--warn-text) auf Karte", "--warn-text", "--karte", 4.5);

// ---- 2. Ampel ------------------------------------------------------------------------------
for (const a of ["gruen", "orange", "rot"]) {
  paar(`Zahl im Ampel-Chip (--ampel-schrift auf --ampel-${a})`, "--ampel-schrift", `--ampel-${a}`, 4.5);
  paar(`Ampelpunkt ${a} auf Szenen-Zeile (--flaeche)`, `--ampel-${a}`, "--flaeche", 3);
  paar(`Ampel-Randstreifen ${a} auf Karte`, `--ampel-${a}`, "--karte", 3);
}
paar("Statustext 'an' in Ampel-Gruen auf Karte", "--ampel-gruen", "--karte", 4.5);
check("Ampelfarben nur ueber Tokens (kein fest codiertes #1f9d55 / #d9890b)",
  !/#1f9d55|#d9890b/i.test(ohneKommentar), "feste Ampelfarben im CSS");
const regel = (sel) => (ohneKommentar.match(new RegExp(sel.replace(/[.\\]/g, "\\$&") + "\\s*\\{([^}]*)\\}")) || [, ""])[1];
check("Ampelpunkte unterscheiden sich auch ohne Farbe (Form per clip-path)",
  /clip-path/.test(regel(".an-punkt.orange")) && /clip-path/.test(regel(".an-punkt.rot")) && !/clip-path/.test(regel(".an-punkt.gruen")),
  "orange/rot brauchen clip-path, gruen bleibt rund");
check("Ampel-Chips tragen ein Zeichen (Haekchen/Ausrufezeichen/Kreuz)",
  ["gruen", "orange", "rot"].every((a) => /content:/.test(regel(`.an-p.${a}::before`))), "::before mit content fehlt");

// ---- 3. Aufstellungsfeld ---------------------------------------------------------------------
paar("Weisse Feldlinie auf Hallenboden (--feld-court)", "#fff", "--feld-court", 3);
paar("Weisse Feldlinie auf Torraum (--feld-ocker)", "#fff", "--feld-ocker", 3);
paar("Feldrand (--feld-court) hebt sich vom Seitengrund ab", "--feld-court", "--bg", 3);
paar("Rollenkuerzel (weiss) im Chip auf Hallenboden", "#fff", (t) => ueber(farbe("var(--feld-chip)", t), farbe("var(--feld-court)", t)), 4.5);
paar("Rollenkuerzel (weiss) im Chip auf Torraum", "#fff", (t) => ueber(farbe("var(--feld-chip)", t), farbe("var(--feld-ocker)", t)), 4.5);
paar("Auswahlring um die Spielerin (--ocker-text) auf Seitengrund", "--ocker-text", "--bg", 3);
const wappen = [...lies("core/portraits.js").matchAll(/\["(#[0-9A-Fa-f]{6})",\s*"(#[0-9A-Fa-f]{6})"\]/g)];
check("Wappenfarben aus portraits.js gefunden", wappen.length >= 3, wappen.length + " Paare");
wappen.forEach((w, i) => paar(`Initialen (weiss) auf Wappen-Farbe ${i + 1} (${w[1]})`, "#fff", w[1], 4.5, ["hell"]));

// ---- 4. Spielzug-Feld (Playbook) ----------------------------------------------------------
paar("Spielerbeschriftung Angriff (--tvg-text) auf Kreis (--tint)", "--tvg-text", "--tint", 4.5);
paar("Spielerbeschriftung Abwehr (--warn-text) auf Kreis (--warn-bg)", "--warn-text", "--warn-bg", 4.5);
paar("Kreisrand Angriff (--tvg) auf Spielzug-Feld", "--tvg", "--court-bg", 3);

// ---- 5. Diagramme und Balken ----------------------------------------------------------------
paar("ELO-Linie steigend (--gruen) auf Karte", "--gruen", "--karte", 3);
paar("ELO-Linie fallend (--b) auf Karte", "--b", "--karte", 3);
for (const [n, tok] of [["zugesagt (--tvg)", "--tvg"], ["knapp (--ocker-kraeftig)", "--ocker-kraeftig"], ["kritisch (--warn)", "--warn"]])
  paar(`Teilnahme-Balken ${n} auf Spur (--bar-spur)`, tok, "--bar-spur", 3);
// Team-Balken: sichtbar ist die Kante - entweder die Fuellung selbst oder ihr Rand (--bar-rand).
const teamFarben = [...lies("features/einteilung.js").matchAll(/farbe:\s*"([^"]+)"/g)].map((m) => m[1]);
check("Teamfarben aus einteilung.js gefunden", teamFarben.length === 4, teamFarben.length + " Farben");
for (const f of teamFarben)
  paar(`Team-Balken ${f} gegen die Spur (--linie), inkl. Rand`,
    (t) => { const fl = farbe(f, t); return ueber(farbe("var(--bar-rand)", t), fl); }, "--linie", 3);
check("Team-Balken haben den Rand aus --bar-rand", /\.st-bar i\s*\{[^}]*var\(--bar-rand\)/.test(ohneKommentar), ".st-bar i ohne --bar-rand");

if (fehler) { console.error(`\n${fehler} Fehler`); process.exit(1); }
console.log("\nalles ok");
