// Tests fuer die Spielzug-Logik (static/spielzug-logik.js): Entscheidungsbaum durchlaufen,
// Aufstellungen aufbauen, Videostatus. Reine Funktionen, kein DOM.
// Start: node tests/spielzug.test.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(dir, "..", "static", "spielzug-logik.js"), "utf8");
const sandbox = { window: {}, console };
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: "spielzug-logik.js" });
const L = sandbox.window.SpielzugLogik;

// Objekte aus dem vm-Sandbox haben andere Prototypen als die des Tests: ueber JSON vergleichen.
const eq = (ist, soll) => assert.deepStrictEqual(JSON.parse(JSON.stringify(ist)), JSON.parse(JSON.stringify(soll)));

let fails = 0;
function test(name, fn) {
  try { fn(); console.log("ok   " + name); }
  catch (e) { fails++; console.log("FEHLER " + name + "\n     " + e.message); }
}

const k = (id, kinder = [], extra = {}) => ({ id, text: "T" + id, reaktion: null, stellung: {}, video_clip_id: null, kinder, ...extra });
// A -> B -> C(Verzweigung: C1 | C2 -> D(Verzweigung: D1 | D2))
const baum = k("A", [k("B", [k("C", [
  k("C1", [], { reaktion: "Innen raus", video_clip_id: 7 }),
  k("C2", [k("D", [k("D1", [], { reaktion: "Aussen" }), k("D2", [], { reaktion: "Mitte zu", video_clip_id: 8 })]) ], { reaktion: "Abwehr haelt" }),
])])]);

test("Grundaufstellung ist 6:0 mit sechs Angreiferinnen", () => {
  eq(Object.keys(L.ANGRIFF_GRUND).sort(), ["HL", "HR", "KR", "LA", "RA", "RM"]);
  eq(Object.keys(L.ABWEHR_GRUND).sort(), ["D1", "D2", "D3", "D4", "D5", "D6"]);
});

test("lauf: ohne Wahl stoppt der Weg an der Verzweigung", () => {
  const l = L.lauf(baum, []);
  eq(l.knoten.map((n) => n.id), ["A", "B", "C"]);
  assert.strictEqual(l.offen.id, "C");
});

test("lauf: mit Wahl geht es in die gewaehlte Loesung", () => {
  eq(L.lauf(baum, [0]).knoten.map((n) => n.id), ["A", "B", "C", "C1"]);
  assert.strictEqual(L.lauf(baum, [0]).offen, null);
});

test("lauf: zweite Verzweigung braucht die zweite Wahl", () => {
  eq(L.lauf(baum, [1]).knoten.map((n) => n.id), ["A", "B", "C", "C2", "D"]);
  eq(L.lauf(baum, [1, 1]).knoten.map((n) => n.id), ["A", "B", "C", "C2", "D", "D2"]);
});

test("lauf: ungueltige Wahl wird wie keine Wahl behandelt", () => {
  assert.strictEqual(L.lauf(baum, [9]).offen.id, "C");
});

test("Navigation: weiter laeuft bis zur Verzweigung und bleibt dort stehen", () => {
  let s = L.start();
  s = L.weiter(baum, s); s = L.weiter(baum, s);
  assert.strictEqual(L.aktuell(baum, s).id, "C");
  assert.strictEqual(L.weiter(baum, s).i, 2, "an der Verzweigung gibt es kein Weiter ohne Wahl");
});

test("Navigation: zurueck stoppt am Anfang", () => {
  assert.strictEqual(L.zurueck(baum, L.start()).i, 0);
});

test("optionen: nur an einer Verzweigung, mit Beschriftung und Videohinweis", () => {
  let s = { wahl: [], i: 0 };
  eq(L.optionen(baum, s), []);
  s = { wahl: [], i: 2 };
  const o = L.optionen(baum, s);
  eq(o.map((x) => x.reaktion), ["Innen raus", "Abwehr haelt"]);
  eq(o.map((x) => x.hatVideo), [true, true], "auch ein Video weiter unten im Ast zaehlt");
});

test("waehle: setzt die Wahl und springt in die Loesung", () => {
  const s = L.waehle(baum, { wahl: [], i: 2 }, 1);
  eq(s.wahl, [1]);
  assert.strictEqual(L.aktuell(baum, s).id, "C2");
});

test("waehle: zweite Verzweigung ergaenzt die Wahl", () => {
  let s = L.waehle(baum, { wahl: [], i: 2 }, 1);
  s = L.weiter(baum, s);
  assert.strictEqual(L.aktuell(baum, s).id, "D");
  s = L.waehle(baum, s, 0);
  eq(s.wahl, [1, 0]);
  assert.strictEqual(L.aktuell(baum, s).id, "D1");
});

test("waehle: andere Loesung an frueherer Verzweigung verwirft spaetere Wahlen", () => {
  let s = { wahl: [1, 0], i: 5 };
  s = L.zurueck(baum, s); s = L.zurueck(baum, s); s = L.zurueck(baum, s);
  assert.strictEqual(L.aktuell(baum, s).id, "C");
  s = L.waehle(baum, s, 0);
  eq(s.wahl, [0]);
  assert.strictEqual(L.aktuell(baum, s).id, "C1");
});

test("stellungen: Teilangaben bleiben in den folgenden Schritten bestehen", () => {
  const knoten = [
    { stellung: { angriff: { KR: [170, 125] }, ball: "HL" } },
    { stellung: { abwehr: { D3: [160, 148] } } },
    { stellung: {} },
  ];
  const s = L.stellungen(knoten);
  eq(s[0].angriff.KR, [170, 125]);
  eq(s[0].angriff.LA, L.ANGRIFF_GRUND.LA, "Rest bleibt Grundaufstellung");
  eq(s[1].angriff.KR, [170, 125], "KR bleibt, wo sie war");
  eq(s[2].abwehr.D3, [160, 148], "D3 bleibt, wo sie war");
  assert.strictEqual(s[2].ball, "HL");
});

test("stellungen: aendert die Grundaufstellung nicht (keine geteilten Referenzen)", () => {
  const vorher = JSON.stringify(L.ANGRIFF_GRUND);
  const s = L.stellungen([{ stellung: { angriff: { LA: [1, 1] } } }]);
  s[0].angriff.HL[0] = 999;
  assert.strictEqual(JSON.stringify(L.ANGRIFF_GRUND), vorher);
});

test("videoUebersicht: listet jede Loesung mit Pfad und Videostatus", () => {
  const u = L.videoUebersicht(baum);
  eq(u.map((x) => x.pfad.join(" > ")),
    ["Innen raus", "Abwehr haelt > Aussen", "Abwehr haelt > Mitte zu"]);
  eq(u.map((x) => x.hatVideo), [true, false, true]);
});

test("videoUebersicht: Spielzug ohne Verzweigung ist eine einzige Loesung", () => {
  assert.strictEqual(L.videoUebersicht(k("X", [k("Y")])).length, 1);
});

// ---- Feldgeometrie: echtes Handballfeld (1 m = 20 Einheiten, Tor 3 m = 60 breit, Mitte x = 200) ----
// Torraum (6 m) und Freiwurflinie (9 m) sind KEINE Halbkreise: Sie halten den Abstand 6 bzw. 9 m zur
// Torlinie zwischen den Pfosten (Viertelkreise um die Pfosten, dazwischen 3 m gerade).
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const nah = (a, b, tol = 0.01) => Math.abs(a - b) <= tol;

test("abstandZumTor: Abstand zur Torlinie zwischen den Pfosten", () => {
  assert.ok(nah(L.abstandZumTor(200, 120), 120), "6 m vor der Mitte");
  assert.ok(nah(L.abstandZumTor(170, 0), 0), "am Pfosten");
  assert.ok(nah(L.abstandZumTor(100, 0), 70), "neben dem Pfosten auf der Torlinie");
  assert.ok(nah(L.abstandZumTor(110, 80), Math.hypot(60, 80)), "schraeg: Abstand zum naechsten Pfosten");
});

test("6-m-Linie: jeder Punkt genau 6 m vom Tor, mit 3 m Geraden in der Mitte", () => {
  const p = L.linienPunkte(120);
  assert.ok(p.every((q) => nah(L.abstandZumTor(q[0], q[1]), 120)), "alle Punkte 6 m vom Tor");
  assert.ok(nah(p[0][0], 50) && nah(p[0][1], 0), "beginnt auf der Torlinie, 6 m links vom Pfosten");
  assert.ok(nah(p[p.length - 1][0], 350) && nah(p[p.length - 1][1], 0), "endet auf der Torlinie rechts");
  assert.ok(p.some((q) => nah(q[0], 170) && nah(q[1], 120)) && p.some((q) => nah(q[0], 230) && nah(q[1], 120)),
    "die Gerade geht von Pfosten zu Pfosten (170 bis 230)");
  assert.ok(!p.some((q) => q[0] > 171 && q[0] < 229 && !nah(q[1], 120)), "dazwischen verlaeuft sie gerade");
});

test("9-m-Linie: gleiche Form, am Seitenaus abgeschnitten", () => {
  const p = L.linienPunkte(180);
  assert.ok(p.every((q) => nah(L.abstandZumTor(q[0], q[1]), 180)), "alle Punkte 9 m vom Tor");
  assert.ok(p.every((q) => q[0] >= -0.01 && q[0] <= 400.01), "bleibt im Feld (0 bis 20 m Breite)");
  assert.ok(nah(p[0][0], 0) && nah(p[p.length - 1][0], 400), "reicht bis zum Seitenaus");
  assert.ok(p.some((q) => nah(q[0], 170) && nah(q[1], 180)) && p.some((q) => nah(q[0], 230) && nah(q[1], 180)),
    "auch hier 3 m gerade in der Mitte");
});

test("Siebenmetermarke: 1 m breit, 7 m vor dem Tor, mittig", () => {
  const m = L.SIEBEN_METER;
  assert.ok(nah(m.y, 140) && nah(m.x2 - m.x1, 20) && nah((m.x1 + m.x2) / 2, 200));
});

test("Grundaufstellung: niemand steht im Torraum, Abwehr direkt vor der 6-m-Linie", () => {
  const alle = [...Object.values(L.ANGRIFF_GRUND), ...Object.values(L.ABWEHR_GRUND)];
  assert.ok(alle.every((q) => L.abstandZumTor(q[0], q[1]) > 120), "kein Spieler im Torraum");
  for (const [n, q] of Object.entries(L.ABWEHR_GRUND)) {
    const d = L.abstandZumTor(q[0], q[1]);
    assert.ok(d > 120 && d <= 150, n + " steht " + (d / 20).toFixed(1) + " m vom Tor (erwartet 6 bis 7,5 m)");
  }
});

test("Grundaufstellung: Rueckraum ausserhalb der 9-m-Linie, niemand ueberdeckt jemanden", () => {
  for (const n of ["HL", "RM", "HR"]) {
    const q = L.ANGRIFF_GRUND[n];
    assert.ok(L.abstandZumTor(q[0], q[1]) >= 180, n + " steht innerhalb der 9-m-Linie");
  }
  const namen = [...Object.entries(L.ANGRIFF_GRUND), ...Object.entries(L.ABWEHR_GRUND)];
  for (let i = 0; i < namen.length; i++) for (let j = i + 1; j < namen.length; j++)
    assert.ok(dist(namen[i][1], namen[j][1]) >= 26, namen[i][0] + " und " + namen[j][0] + " ueberdecken sich");
});

// ---- Editor: den Baum bearbeiten (alles unveraenderlich: jede Funktion gibt einen NEUEN Baum zurueck) ----
test("neuerBaum: ein Startschritt, der die Grundaufstellung erbt", () => {
  const b = L.neuerBaum();
  assert.strictEqual(b.kinder.length, 0);
  assert.ok(b.text.length > 0 && typeof b.id === "number" && b.id < 0, "vorlaeufige (negative) ID bis zum Speichern");
  eq(b.stellung, {});
});

test("finde: Knoten per ID", () => {
  assert.strictEqual(L.finde(baum, "D2").id, "D2");
  assert.strictEqual(L.finde(baum, "gibtsnicht"), null);
});

test("fuegeKindEin: haengt einen Schritt an, ohne den alten Baum zu veraendern", () => {
  const vorher = JSON.stringify(baum);
  const r = L.fuegeKindEin(baum, "D1");
  assert.strictEqual(JSON.stringify(baum), vorher, "Original bleibt unveraendert");
  const d1 = L.finde(r.baum, "D1");
  assert.strictEqual(d1.kinder.length, 1);
  assert.strictEqual(d1.kinder[0].id, r.neueId);
  assert.ok(r.neueId < 0);
});

test("fuegeKindEin: ab dem zweiten Ast tragen ALLE Aeste eine Beschriftung", () => {
  let r = L.fuegeKindEin(L.neuerBaum(), L.neuerBaum().id);
  const wurzel = r.baum.id;
  r = L.fuegeKindEin(r.baum, wurzel);
  const kinder = L.finde(r.baum, wurzel).kinder;
  assert.strictEqual(kinder.length, 2);
  assert.ok(kinder.every((x) => x.reaktion && x.reaktion.trim()), "beide beschriftet");
  assert.notStrictEqual(kinder[0].reaktion, kinder[1].reaktion, "unterschiedlich beschriftet");
});

test("fuegeKindEin: vorhandene Beschriftungen bleiben", () => {
  const r = L.fuegeKindEin(baum, "C");
  const kinder = L.finde(r.baum, "C").kinder;
  assert.strictEqual(kinder[0].reaktion, "Innen raus");
  assert.strictEqual(kinder.length, 3);
});

test("fuegeKindEin: neue IDs sind eindeutig", () => {
  let r = L.fuegeKindEin(L.neuerBaum(), -1);
  const a = r.neueId;
  r = L.fuegeKindEin(r.baum, -1);
  assert.notStrictEqual(r.neueId, a);
});

test("fuegeKindEin: Grenzen wie auf dem Server (6 Aeste, 12 Schritte)", () => {
  let b = L.neuerBaum();
  for (let i = 0; i < 6; i++) b = L.fuegeKindEin(b, -1).baum;
  const voll = L.fuegeKindEin(b, -1);
  assert.strictEqual(voll.neueId, null, "siebter Ast wird abgelehnt");
  assert.strictEqual(L.finde(voll.baum, -1).kinder.length, 6);
  let kette = L.neuerBaum(), id = -1;
  for (let i = 1; i < 12; i++) { const r = L.fuegeKindEin(kette, id); kette = r.baum; id = r.neueId; }
  assert.strictEqual(L.fuegeKindEin(kette, id).neueId, null, "dreizehnter Schritt wird abgelehnt");
});

test("loescheKnoten: entfernt den Knoten samt allem darunter", () => {
  const b = L.loescheKnoten(baum, "C2");
  assert.strictEqual(L.finde(b, "C2"), null);
  assert.strictEqual(L.finde(b, "D"), null);
  assert.strictEqual(L.finde(b, "C1").id, "C1");
  assert.ok(L.finde(baum, "C2"), "Original bleibt");
});

test("loescheKnoten: die Wurzel loeschen leert den ganzen Baum", () => {
  assert.strictEqual(L.loescheKnoten(baum, "A"), null);
});

test("setze: aendert nur erlaubte Felder", () => {
  const b = L.setze(baum, "B", { text: "Neu", reaktion: "x", video_clip_id: 5, kinder: [], id: 99 });
  const n = L.finde(b, "B");
  assert.strictEqual(n.text, "Neu"); assert.strictEqual(n.video_clip_id, 5);
  assert.strictEqual(n.kinder.length, 1, "kinder bleiben");
  assert.strictEqual(n.id, "B", "id bleibt");
});

test("begrenze: bleibt im Feld", () => {
  eq(L.begrenze([-20, 500]), [0, 300]);
  eq(L.begrenze([450, -5]).map((v, i) => (i === 0 ? v : 0)), [400, 0]);
});

test("begrenze: wer im Torraum landet, wird an die 6-m-Linie geschoben", () => {
  const p = L.begrenze([200, 60]);
  assert.ok(L.abstandZumTor(p[0], p[1]) >= 119.5, "nicht mehr im Torraum");
  assert.ok(L.abstandZumTor(p[0], p[1]) <= 121, "aber so nah wie moeglich dran");
  const q = L.begrenze([120, 40]);
  assert.ok(L.abstandZumTor(q[0], q[1]) >= 119.5);
  eq(L.begrenze([200, 200]), [200, 200]);
});

test("setzePosition: schreibt die Position in den Knoten", () => {
  const b = L.setzePosition(baum, "B", "angriff", "KR", [210, 150]);
  eq(L.finde(b, "B").stellung.angriff.KR, [210, 150]);
  assert.ok(!L.finde(baum, "B").stellung.angriff, "Original bleibt");
});

test("setzePosition: unbekannte Spielerin oder Seite wird ignoriert", () => {
  eq(L.setzePosition(baum, "B", "angriff", "XX", [1, 1]), baum);
  eq(L.setzePosition(baum, "B", "mitte", "KR", [1, 1]), baum);
});

test("setzeBall: nur bei einer Angreiferin", () => {
  assert.strictEqual(L.finde(L.setzeBall(baum, "B", "HL"), "B").stellung.ball, "HL");
  eq(L.setzeBall(baum, "B", "D1"), baum);
});

test("stellungFuer: Aufstellung an einem Knoten inklusive geerbter Positionen", () => {
  let b = L.setzePosition(baum, "B", "angriff", "KR", [210, 150]);
  const st = L.stellungFuer(b, "C");
  eq(st.angriff.KR, [210, 150]);
  eq(st.angriff.LA, L.ANGRIFF_GRUND.LA);
  assert.strictEqual(L.stellungFuer(b, "gibtsnicht"), null);
});

test("zustandFuer: Zustand, der genau auf einen Knoten zeigt", () => {
  eq(L.zustandFuer(baum, "B"), { wahl: [], i: 1 });
  eq(L.zustandFuer(baum, "C2"), { wahl: [1], i: 3 });
  eq(L.zustandFuer(baum, "D2"), { wahl: [1, 1], i: 5 });
  assert.strictEqual(L.zustandFuer(baum, "gibtsnicht"), null);
  assert.strictEqual(L.aktuell(baum, L.zustandFuer(baum, "D2")).id, "D2");
});

test("setzeZurueck: ein Schritt erbt wieder alles vom Schritt davor", () => {
  let b = L.setzePosition(baum, "C", "angriff", "HL", [150, 165]);
  b = L.setzeBall(b, "C", "HL");
  b = L.setzeZurueck(b, "C");
  eq(L.finde(b, "C").stellung, {});
  eq(L.stellungFuer(b, "C"), L.stellungFuer(b, "B"));
  eq(L.finde(b, "C").kinder.length, 2);
  assert.strictEqual(L.finde(b, "C").text, "TC", "Text bleibt");
});

// ---- Beschreibung ueber der Grafik: Vorlage fuer neue Playbook-Texte ----
test("Vorlage: fragt nach Inhalt und Ziel des Spielzugs, ohne etwas vorzugeben", () => {
  const v = L.BESCHREIBUNG_VORLAGE;
  assert.ok(/^## Worum geht es\?/m.test(v), "erste Ueberschrift");
  assert.ok(/^## Was wollen wir erreichen\?/m.test(v), "zweite Ueberschrift");
  assert.ok(v.indexOf("Worum") < v.indexOf("erreichen"), "Reihenfolge: erst Inhalt, dann Ziel");
  assert.strictEqual(v.replace(/^## .*$/gm, "").trim(), "", "nur Ueberschriften, kein vorgegebener Inhalt");
});

if (fails) { console.log(`\n${fails} Test(s) fehlgeschlagen.`); process.exit(1); }
console.log("\nAlle Tests gruen.");
