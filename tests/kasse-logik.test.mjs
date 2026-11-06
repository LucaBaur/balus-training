// Tests fuer die reinen Hilfen der Mannschaftskasse (static/kasse-logik.js):
// Euro-Anzeige aus Cent, Eingabe "12,50" -> Cent, Wirkung einer Buchung, Beschriftung.
// Kein DOM, kein Netz. Start: node tests/kasse-logik.test.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(dir, "..", "static", "kasse-logik.js"), "utf8");
const sandbox = { window: {}, console, Number, Math, String, Object, Array, isNaN, parseInt };
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: "kasse-logik.js" });
const K = sandbox.window.KasseLogik;

let fails = 0;
function test(name, fn) {
  try { fn(); console.log("ok   " + name); }
  catch (e) { fails++; console.log("FEHLER " + name + "\n     " + e.message); }
}

// Das Leerzeichen vor "€" ist ein geschuetztes (U+00A0), damit der Betrag nicht umbricht.
const NBSP = " ";

test("euro: ganze und krumme Betraege", () => {
  assert.equal(K.euro(0), "0,00" + NBSP + "€");
  assert.equal(K.euro(5), "0,05" + NBSP + "€");
  assert.equal(K.euro(50), "0,50" + NBSP + "€");
  assert.equal(K.euro(1250), "12,50" + NBSP + "€");
  assert.equal(K.euro(30), "0,30" + NBSP + "€");
});
test("euro: Tausenderpunkt", () => {
  assert.equal(K.euro(100000), "1.000,00" + NBSP + "€");
  assert.equal(K.euro(123456789), "1.234.567,89" + NBSP + "€");
});
test("euro: negativ mit echtem Minuszeichen, nie -0", () => {
  assert.equal(K.euro(-1000), "−10,00" + NBSP + "€");
  assert.equal(K.euro(-5), "−0,05" + NBSP + "€");
  assert.equal(K.euro(-0), "0,00" + NBSP + "€");
});
test("euro: Unsinn wird 0,00 statt NaN", () => {
  assert.equal(K.euro(null), "0,00" + NBSP + "€");
  assert.equal(K.euro(undefined), "0,00" + NBSP + "€");
  assert.equal(K.euro("abc"), "0,00" + NBSP + "€");
});

test("parseEuro: gaengige Eingaben", () => {
  assert.equal(K.parseEuro("12,50"), 1250);
  assert.equal(K.parseEuro("12.50"), 1250);
  assert.equal(K.parseEuro("12"), 1200);
  assert.equal(K.parseEuro("0,5"), 50);
  assert.equal(K.parseEuro("5 €"), 500);
  assert.equal(K.parseEuro("  7,25  "), 725);
  assert.equal(K.parseEuro("0,05"), 5);
});
test("parseEuro: Tausendertrennung", () => {
  assert.equal(K.parseEuro("1.234,56"), 123456);
  assert.equal(K.parseEuro("1.000"), 100000);
});
test("parseEuro: kein Gleitkomma-Fehler (0,29 und 1,15 sind exakt)", () => {
  assert.equal(K.parseEuro("0,29"), 29);        // 0.29 * 100 waere 28.999999999999996
  assert.equal(K.parseEuro("1,15"), 115);       // 1.15 * 100 waere 114.99999999999999
  assert.equal(K.parseEuro("4,35"), 435);
});
test("parseEuro: ungueltig oder nicht positiv gibt null", () => {
  for (const s of ["", "   ", "abc", "0", "0,00", "-3", "1,234", "12,505", "1,2,3", "€", ",", "12 Euro 50", null, undefined])
    assert.equal(K.parseEuro(s), null, `"${s}" sollte abgelehnt werden`);
});
test("parseEuro: Obergrenze wie am Server (10.000 €)", () => {
  assert.equal(K.parseEuro("10000"), 1000000);
  assert.equal(K.parseEuro("10000,01"), null);
});

test("ARTEN: vier Arten, nur Forderung/Einzahlung brauchen eine Spielerin", () => {
  assert.deepEqual(K.ARTEN.map((a) => a.key), ["forderung", "einzahlung", "ausgabe", "einnahme"]);
  assert.deepEqual(K.ARTEN.filter((a) => a.spielerin).map((a) => a.key), ["forderung", "einzahlung"]);
  assert.ok(K.ARTEN.every((a) => a.label && a.hinweis));
});

test("wirkung: was eine Buchung fuer die Kasse bedeutet (mit Vorzeichen)", () => {
  assert.equal(K.wirkung({ art: "einzahlung", betrag_cent: 200, storniert: false }), 200);
  assert.equal(K.wirkung({ art: "einnahme", betrag_cent: 4000, storniert: false }), 4000);
  assert.equal(K.wirkung({ art: "ausgabe", betrag_cent: 1000, storniert: false }), -1000);
  assert.equal(K.wirkung({ art: "forderung", betrag_cent: 500, storniert: false }), 0, "Forderung bewegt kein Bargeld");
  assert.equal(K.wirkung({ art: "einnahme", betrag_cent: 4000, storniert: true }), 0, "Storniertes zaehlt nicht");
});

test("kassenstand: rechnet die Liste wie der Server (stornierte nicht)", () => {
  const liste = [
    { art: "einzahlung", betrag_cent: 200, storniert: false },
    { art: "einnahme", betrag_cent: 4000, storniert: false },
    { art: "ausgabe", betrag_cent: 1000, storniert: false },
    { art: "forderung", betrag_cent: 500, storniert: false },
    { art: "einnahme", betrag_cent: 999, storniert: true },
  ];
  assert.equal(K.kassenstand(liste), 3200);
  assert.equal(K.kassenstand([]), 0);
});

test("offenText: schuldet / Guthaben / quitt", () => {
  assert.equal(K.offenText(300), "schuldet 3,00" + NBSP + "€");
  assert.equal(K.offenText(0), "alles bezahlt");
  assert.equal(K.offenText(-1000), "hat 10,00" + NBSP + "€ Guthaben");
});

test("katalogBetrag: fester Betrag, Anzahl, Trainer x2, Kasten", () => {
  const fest = { key: "rot", label: "Rote Karte", cent: 4500, einheit: null };
  const minute = { key: "spaet", label: "Zu spät", cent: 300, einheit: "Min" };
  const kasten = { key: "bier", label: "Bier verschüttet", cent: null, einheit: null };
  assert.equal(K.katalogBetrag(fest, 1, false), 4500);
  assert.equal(K.katalogBetrag(fest, 7, false), 4500, "ohne Einheit zählt die Anzahl nicht");
  assert.equal(K.katalogBetrag(minute, 4, false), 1200);
  assert.equal(K.katalogBetrag(minute, 4, true), 2400, "Trainer: alles mal zwei");
  assert.equal(K.katalogBetrag(minute, 0, false), null, "Anzahl 0 ist ungültig");
  assert.equal(K.katalogBetrag(minute, "x", false), null);
  assert.equal(K.katalogBetrag(kasten, 1, false), null, "Kasten hat keinen Betrag: der wird von Hand eingetragen");
  assert.equal(K.katalogBetrag(null, 1, false), null);
  assert.equal(K.katalogBetrag(minute, 99999, false), null, "über der Obergrenze -> null");
});

test("katalogText: Anzahl und Trainer erscheinen im Buchungstext", () => {
  const minute = { label: "Spieltreffpunkt zu spät", cent: 300, einheit: "Min" };
  const fest = { label: "Rote Karte", cent: 4500, einheit: null };
  assert.equal(K.katalogText(fest, 1, false), "Rote Karte");
  assert.equal(K.katalogText(minute, 4, false), "Spieltreffpunkt zu spät (4 Min)");
  assert.equal(K.katalogText(fest, 1, true), "Rote Karte (Trainer ×2)");
  assert.equal(K.katalogText(minute, 2, true), "Spieltreffpunkt zu spät (2 Min, Trainer ×2)");
  assert.ok(K.katalogText({ label: "x".repeat(200), cent: 1, einheit: null }, 1, false).length <= 120, "Text bleibt unter der Server-Grenze");
});

if (fails) { console.log(`\n${fails} Test(s) fehlgeschlagen`); process.exit(1); }
console.log("\nalles ok");
