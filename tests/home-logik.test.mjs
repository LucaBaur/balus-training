// Tests fuer die Auswahl auf den Startseiten (static/home-logik.js):
// naechstes Training, Spiele, Tabellenauszug, "Neu fuer dich", Aufgabenliste des Trainers.
// Reine Funktionen ohne Oberflaeche. Start: node tests/home-logik.test.mjs
import { readFileSync } from "node:fs";
import vm from "node:vm";
import assert from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(dir, "..", "static", "home-logik.js"), "utf8");

function lade() {
  const sandbox = { window: {}, console, Date, Math, Number, Array, Object, Set };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "home-logik.js" });
  return sandbox.window.HomeLogik;
}
const H = lade();

let fails = 0;
function test(name, fn) {
  try { fn(); console.log("ok   " + name); }
  catch (e) { fails++; console.log("FEHLER " + name + "\n     " + e.message); }
}

const HEUTE = "2026-11-03";                         // ein Dienstag
const tr = (id, datum, o = {}) => ({ id, datum, art: "training", titel: "Training", anwesend: 8, abgesagt: 0,
                                     unsicher: 0, kader: 16, meine_status: null, ...o });
const sp = (id, datum, o = {}) => tr(id, datum, { art: "ligaspiel", gegner: "SG X", ...o });

test("Wochentag in voller Laenge", () => {
  assert.equal(H.wochentag("2026-11-05"), "Donnerstag");
  assert.equal(H.wochentag("2026-11-09"), "Montag");
  assert.equal(H.wochentag(""), "");
});

test("naechstes Training: frueheste Einheit ab heute, Spiele zaehlen nicht", () => {
  const l = [tr(3, "2026-11-10"), sp(2, "2026-11-04"), tr(1, "2026-11-05"), tr(9, "2026-10-30")];
  assert.equal(H.naechstesTraining(l, HEUTE).id, 1);
  assert.equal(H.naechstesTraining([tr(9, "2026-10-30")], HEUTE), null);
  assert.equal(H.naechstesTraining([], HEUTE), null);
});

test("heute zaehlt noch als kommend", () => {
  assert.equal(H.naechstesTraining([tr(1, HEUTE)], HEUTE).id, 1);
});

test("naechste Spiele: nur Spiele, aufsteigend, hoechstens n", () => {
  const l = [tr(1, "2026-11-04"), sp(2, "2026-11-20"), sp(3, "2026-11-06"), sp(4, "2026-11-13"),
             sp(5, "2026-11-27"), sp(6, "2026-10-01")];
  assert.deepEqual(H.naechsteSpiele(l, HEUTE, 3).map((t) => t.id), [3, 4, 2]);
});

test("offene Antworten: ohne eigene Antwort, ohne das Hero-Training", () => {
  const l = [tr(1, "2026-11-05"), tr(2, "2026-11-09", { meine_status: "anwesend" }), tr(3, "2026-11-12"),
             sp(4, "2026-11-06"), tr(5, "2026-10-01")];
  assert.deepEqual(H.offeneAntworten(l, HEUTE).map((t) => t.id), [1, 4, 3]);
  assert.deepEqual(H.offeneAntworten(l, HEUTE, 1).map((t) => t.id), [4, 3]);
});

const tabelle = [
  { platz: 1, team: "A", punkte_plus: 6, punkte_minus: 0 },
  { platz: 2, team: "B", punkte_plus: 5, punkte_minus: 1 },
  { platz: 3, team: "TV Gerhausen 1900", punkte_plus: 5, punkte_minus: 3, eigen: true },
  { platz: 4, team: "D", punkte_plus: 4, punkte_minus: 0 },
  { platz: 5, team: "E", punkte_plus: 2, punkte_minus: 2 },
];

test("Tabellenauszug: eigene Zeile mit Vor- und Nachbar", () => {
  const a = H.tabellenAuszug(tabelle);
  assert.equal(a.platz, 3);
  assert.equal(a.punkte, "5:3");
  assert.deepEqual(a.zeilen.map((z) => z.platz), [2, 3, 4]);
  assert.deepEqual(a.zeilen.map((z) => !!z.eigen), [false, true, false]);
});

test("Tabellenauszug am Rand und ohne eigenes Team", () => {
  const erster = tabelle.map((z, i) => ({ ...z, eigen: i === 0 }));
  assert.deepEqual(H.tabellenAuszug(erster).zeilen.map((z) => z.platz), [1, 2]);
  const letzter = tabelle.map((z, i) => ({ ...z, eigen: i === 4 }));
  assert.deepEqual(H.tabellenAuszug(letzter).zeilen.map((z) => z.platz), [4, 5]);
  assert.equal(H.tabellenAuszug(tabelle.map((z) => ({ ...z, eigen: false }))), null);
  assert.equal(H.tabellenAuszug(null), null);
  assert.equal(H.tabellenAuszug([]), null);
});

test("Neu fuer dich: beim ersten Aufruf nichts, aber eine Grundlinie", () => {
  const clips = [{ id: 3, titel: "A" }, { id: 5, titel: "B" }];
  const analysen = [{ id: 2, gegner: "HSG X", datum: "2026-10-25", video_da: true },
                    { id: 4, gegner: "Y", video_da: false }];
  const r = H.neuFuerDich({ clips, analysen, gesehen: null });
  assert.deepEqual(r.items, []);
  assert.deepEqual(r.grundlinie, { clip: 5, analyse: 2 });          // Analysen ohne Video zaehlen nicht
});

test("Neu fuer dich: nur Neueres als die Grundlinie, Clips zuerst, hoechstens drei", () => {
  const clips = [{ id: 3, titel: "A" }, { id: 5, titel: "B" }, { id: 6, titel: "C" }, { id: 7, titel: "D" }];
  const analysen = [{ id: 2, gegner: "HSG X", datum: "2026-10-25", video_da: true },
                    { id: 4, gegner: "Y", datum: "2026-11-01", video_da: true }];
  const r = H.neuFuerDich({ clips, analysen, gesehen: { clip: 5, analyse: 2 } });
  assert.deepEqual(r.items.map((i) => i.art + i.id), ["clip7", "clip6", "analyse4"]);
  assert.equal(r.items[2].titel, "Videoanalyse: Y");
  assert.equal(r.items[0].titel, "D");
  assert.equal(r.anzahl, 3);
});

test("Neu fuer dich: nach dem Ansehen ist es nicht mehr neu", () => {
  const g = H.alsGesehen({ clip: 5, analyse: 2 }, "clip", 7);
  assert.deepEqual(g, { clip: 7, analyse: 2 });
  assert.deepEqual(H.alsGesehen({ clip: 5, analyse: 2 }, "clip", 3), { clip: 5, analyse: 2 });   // nie rueckwaerts
  assert.deepEqual(H.alsGesehen(null, "analyse", 4), { clip: 0, analyse: 4 });
});

// ------------------------------------------------------- Aufgabenliste des Trainers
const termine = [
  tr(1, HEUTE, { anwesend: 9, abgesagt: 2, unsicher: 1, kader: 16, uhrzeit: "20:00" }),
  tr(2, "2026-11-05", { anwesend: 5, abgesagt: 3 }),
  tr(3, "2026-11-10", { anwesend: 8 }),
  sp(4, "2026-10-31", { hat_nachbereitung: 0, gegner: "SG X" }),
  sp(5, "2026-10-10", { hat_nachbereitung: 0 }),
  sp(6, "2026-10-30", { hat_nachbereitung: 1 }),
];

test("Aufgaben: Reihenfolge duenn, ohne Antwort, Nachbereitung, To-Dos", () => {
  const a = H.trainerAufgaben({ trainings: termine, todosWartend: 2, heute: HEUTE });
  assert.deepEqual(a.map((x) => x.art), ["duenn", "offen", "nachbereitung", "todos"]);
  assert.equal(a[0].titel, "Donnerstag: nur 5 Zusagen");
  assert.equal(a[1].titel, "4 ohne Antwort");
  assert.ok(a[1].sub.includes("heute"));
  assert.equal(a[2].titel, "Nachbereitung offen");
  assert.ok(a[2].sub.includes("SG X"));
  assert.equal(a[3].titel, "2 To-Dos warten auf Feedback");
});

test("Aufgaben: Ziele zeigen auf den Termin bzw. die passende Seite", () => {
  const a = H.trainerAufgaben({ trainings: termine, todosWartend: 1, heute: HEUTE });
  assert.deepEqual(a[0].ziel, { ober: "training", unter: "trainings", termin: 2 });
  assert.deepEqual(a[1].ziel, { ober: "training", unter: "trainings", termin: 1 });
  assert.deepEqual(a[2].ziel, { ober: "training", unter: "trainings", termin: 4 });
  assert.deepEqual(a[3].ziel, { ober: "team", unter: "todos" });
  assert.equal(a[3].titel, "1 To-Do wartet auf Feedback");
});

test("Aufgaben: offene Video-Fragen stehen vor den To-Dos und oeffnen das Video", () => {
  const fragen = [
    { ziel: "clip:5", anzahl: 1, von: ["Anna"], titel: "Kreisanspiel" },
    { ziel: "szene:7", anzahl: 3, von: ["Bea", "Clara"], titel: "S1-z3 · Spielzug A" },
  ];
  const a = H.trainerAufgaben({ trainings: [], todosWartend: 1, fragen, heute: HEUTE });
  assert.deepEqual(a.map((x) => x.art), ["frage", "frage", "todos"]);
  assert.equal(a[0].titel, "Frage von Anna");
  assert.equal(a[0].sub, "Kreisanspiel");
  assert.deepEqual(a[0].ziel, { video: "clip:5", titel: "Kreisanspiel" });
  assert.equal(a[1].titel, "3 offene Fragen");
});

test("Aufgaben: hoechstens drei Video-Zeilen, ohne Fragen keine", () => {
  const viele = [1, 2, 3, 4, 5].map((i) => ({ ziel: "clip:" + i, anzahl: 1, von: ["A"], titel: "V" + i }));
  assert.equal(H.trainerAufgaben({ trainings: [], todosWartend: 0, fragen: viele, heute: HEUTE }).length, 3);
  assert.deepEqual(H.trainerAufgaben({ trainings: [], todosWartend: 0, fragen: [], heute: HEUTE }), []);
});

test("Aufgaben: alte Spiele (ueber 14 Tage) und fertige Nachbereitung tauchen nicht auf", () => {
  const a = H.trainerAufgaben({ trainings: termine, todosWartend: 0, heute: HEUTE });
  assert.equal(a.filter((x) => x.art === "nachbereitung").length, 1);
  assert.ok(!a.some((x) => x.art === "todos"));
});

test("Aufgaben: ohne Anlass eine leere Liste", () => {
  assert.deepEqual(H.trainerAufgaben({ trainings: [tr(1, "2026-11-20")], todosWartend: 0, heute: HEUTE }), []);
  assert.deepEqual(H.trainerAufgaben({ trainings: [], todosWartend: 0, heute: HEUTE }), []);
});

test("Aufgaben: 'ohne Antwort' nur fuer den naechsten Termin innerhalb von drei Tagen", () => {
  const spaet = [tr(1, "2026-11-12", { anwesend: 3, abgesagt: 1, kader: 16 })];
  const a = H.trainerAufgaben({ trainings: spaet, todosWartend: 0, heute: HEUTE });
  assert.ok(!a.some((x) => x.art === "offen"));
  const nah = [tr(1, "2026-11-05", { anwesend: 8, abgesagt: 4, kader: 16 })];
  const b = H.trainerAufgaben({ trainings: nah, todosWartend: 0, heute: HEUTE });
  assert.equal(b.find((x) => x.art === "offen").titel, "4 ohne Antwort");
  const alle = [tr(1, "2026-11-05", { anwesend: 10, abgesagt: 4, unsicher: 2, kader: 16 })];
  assert.ok(!H.trainerAufgaben({ trainings: alle, todosWartend: 0, heute: HEUTE }).some((x) => x.art === "offen"));
});

test("Aufgaben: heute und morgen heissen so, nicht wie der Wochentag", () => {
  const a = H.trainerAufgaben({ trainings: [tr(1, HEUTE, { anwesend: 4 }), tr(2, "2026-11-04", { anwesend: 5 })],
                                todosWartend: 0, heute: HEUTE });
  assert.equal(a[0].titel, "Heute: nur 4 Zusagen");
  assert.equal(a[1].titel, "Morgen: nur 5 Zusagen");
});

test("Aufgaben: freiwillige Trainings (Freitag) lösen weder 'dünn' noch 'ohne Antwort' aus", () => {
  const frei = tr(1, "2026-11-06", { anwesend: 2, abgesagt: 3, kader: 16, freiwillig: 1 });
  assert.deepEqual(H.trainerAufgaben({ trainings: [frei], todosWartend: 0, heute: HEUTE }), []);
  const pflicht = tr(1, "2026-11-06", { anwesend: 2, abgesagt: 3, kader: 16, freiwillig: 0 });
  assert.ok(H.trainerAufgaben({ trainings: [pflicht], todosWartend: 0, heute: HEUTE }).some((x) => x.art === "duenn"));
});

test("Aufgaben: das nächste Pflicht-Training zählt für 'ohne Antwort', auch wenn ein freiwilliges davor liegt", () => {
  const l = [tr(1, "2026-11-04", { anwesend: 1, kader: 16, freiwillig: 1 }),
             tr(2, "2026-11-05", { anwesend: 9, abgesagt: 2, unsicher: 1, kader: 16, freiwillig: 0 })];
  const a = H.trainerAufgaben({ trainings: l, todosWartend: 0, heute: HEUTE });
  assert.equal(a.find((x) => x.art === "offen").ziel.termin, 2);
  assert.ok(!a.some((x) => x.art === "duenn"));
});

if (fails) { console.log(`\n${fails} Test(s) fehlgeschlagen`); process.exit(1); }
console.log("\nAlle Tests bestanden");
