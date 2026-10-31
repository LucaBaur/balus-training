// Prueft die reinen Hilfsfunktionen der Ansicht Team -> Nutzung (static/app.js,
// Abschnitt zwischen den Markern "Nutzung-Hilfen"): dauerText, verweilSegment,
// nutzungVideoLabel, gruppiereNachSpiel. Start: node tests/nutzung_ui.test.mjs
import fs from "node:fs";
import vm from "node:vm";

const src = fs.readFileSync(new URL("../static/app.js", import.meta.url), "utf8");
const start = src.indexOf("// ---- Nutzung-Hilfen (rein, getestet");
const ende = src.indexOf("// ---- Ende Nutzung-Hilfen");
if (start < 0 || ende < 0) { console.error("FEHLER Abschnitt 'Nutzung-Hilfen' nicht gefunden"); process.exit(1); }

const ctx = {};
vm.createContext(ctx);
vm.runInContext(src.slice(start, ende)
  + "\nthis.dauerText = dauerText; this.verweilSegment = verweilSegment;"
  + "\nthis.nutzungVideoLabel = nutzungVideoLabel; this.gruppiereNachSpiel = gruppiereNachSpiel;"
  + "\nthis.anzahlDauer = anzahlDauer;", ctx);
const { dauerText, verweilSegment, nutzungVideoLabel, gruppiereNachSpiel, anzahlDauer } = ctx;

let fehler = 0;
function check(name, ist, soll) {
  const ok = JSON.stringify(ist) === JSON.stringify(soll);
  console.log((ok ? "ok   " : "FEHLER ") + name + (ok ? "" : "  -> " + JSON.stringify(ist) + " statt " + JSON.stringify(soll)));
  if (!ok) fehler++;
}

// ------------------------------------------------------------- dauerText ----
check("dauerText: nichts gemessen", dauerText(0), "–");
check("dauerText: null/undefined", [dauerText(null), dauerText(undefined)], ["–", "–"]);
check("dauerText: unter einer Minute", [dauerText(1), dauerText(59)], ["<1 Min.", "<1 Min."]);
check("dauerText: genau eine Minute", dauerText(60), "1 Min.");
check("dauerText: rundet ab", dauerText(119), "1 Min.");
check("dauerText: kurz vor der Stunde", dauerText(3599), "59 Min.");
check("dauerText: volle Stunde ohne Minuten", dauerText(3600), "1 Std.");
check("dauerText: Stunde + Minuten", dauerText(4320), "1 Std. 12 Min.");

// -------------------------------------------------------- verweilSegment ----
//  Eingabe in Millisekunden (Date.now()), Ausgabe ganze Sekunden, 0 = nicht melden.
check("verweilSegment: 5 Sekunden", verweilSegment(0, 5000), 5);
check("verweilSegment: unter einer halben Sekunde zaehlt nicht", verweilSegment(0, 400), 0);
check("verweilSegment: rundet kaufmaennisch", verweilSegment(0, 600), 1);
check("verweilSegment: Ende vor Start", verweilSegment(1000, 500), 0);
check("verweilSegment: kein Start", verweilSegment(null, 100000), 0);
check("verweilSegment: auf 30 Minuten begrenzt", verweilSegment(0, 2_000_000), 1800);
check("verweilSegment: eigene Grenze", verweilSegment(0, 120_000, 60), 60);

// ----------------------------------------------------------- anzahlDauer ----
check("anzahlDauer: mit Dauer", anzahlDauer(2, 38), "2× · <1 Min.");
check("anzahlDauer: ohne Dauer kein Gedankenstrich", anzahlDauer(1, 0), "1×");
check("anzahlDauer: Dauer fehlt (alte Daten)", anzahlDauer(3, undefined), "3×");

// ------------------------------------------------------ nutzungVideoLabel ----
check("Label: Spielzug mit Zeit",
  nutzungVideoLabel({ ziel: "szene:3", titel: "TVG – HSV", label: "Spielzug Kreuz", zeit: "12:03–12:20" }),
  "Spielzug Kreuz · 12:03–12:20");
check("Label: Ereignis mit Zeitpunkt",
  nutzungVideoLabel({ ziel: "szene:4", label: "Tor · Rückraum", zeit: "5:00" }),
  "Tor · Rückraum · 5:00");
check("Label: Spielzug ohne Zeit", nutzungVideoLabel({ ziel: "szene:3", label: "Spielzug Kreuz" }), "Spielzug Kreuz");
check("Label: alte Daten (nur Titel) bleiben lesbar",
  nutzungVideoLabel({ ziel: "szene:3", titel: "TVG – HSV" }), "Spielzug: TVG – HSV");
check("Label: Clip", nutzungVideoLabel({ ziel: "clip:5", titel: "Kreisanspiel", label: "Kreisanspiel" }), "Szene: Kreisanspiel");
check("Label: ganzes Spiel", nutzungVideoLabel({ ziel: "spiel:2", titel: "TVG – HSV", label: "Ganzes Spiel" }), "Ganzes Spiel");
check("Label: unbekannt faellt auf Ziel zurueck", nutzungVideoLabel({ ziel: "x:1" }), "Video: x:1");

// ------------------------------------------------------ gruppiereNachSpiel ----
const items = [
  { ziel: "szene:1", spiel: "TVG – HSV · 14.09.", label: "Spielzug Kreuz" },
  { ziel: "clip:9", spiel: null, label: "Kreisanspiel" },
  { ziel: "szene:2", spiel: "TVG – HSV · 14.09.", label: "Spielzug Doppelpass" },
  { ziel: "szene:7", spiel: "TVG – Kiel · 21.09.", label: "Tor" },
];
const g = gruppiereNachSpiel(items);
check("Gruppen: Reihenfolge nach erstem Auftreten", g.map((x) => x.spiel),
  ["TVG – HSV · 14.09.", "Weitere Videos", "TVG – Kiel · 21.09."]);
check("Gruppen: Eintraege bleiben in Eingabereihenfolge", g[0].items.map((x) => x.ziel), ["szene:1", "szene:2"]);
check("Gruppen: Clips ohne Spiel in eigener Gruppe", g[1].items.map((x) => x.ziel), ["clip:9"]);
check("Gruppen: leere Eingabe", gruppiereNachSpiel([]), []);

const spiel = "TVG – HSV · 14.09.";
const chrono = gruppiereNachSpiel([
  { ziel: "szene:5", spiel, t: 1900 }, { ziel: "spiel:1", spiel, t: null },
  { ziel: "szene:6", spiel, t: 200 }, { ziel: "szene:7", spiel, t: 1210 },
])[0].items.map((x) => x.ziel);
check("Gruppen: im Spiel nach Spielzeit, ganzes Spiel zuerst", chrono, ["spiel:1", "szene:6", "szene:7", "szene:5"]);

if (fehler) { console.error("\n" + fehler + " Test(s) fehlgeschlagen"); process.exit(1); }
console.log("\nAlle Tests bestanden");
