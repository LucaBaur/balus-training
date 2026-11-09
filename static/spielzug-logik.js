"use strict";

// ============================================================================
//  spielzug-logik.js — Der Entscheidungsbaum eines Spielzugs als reine Funktionen.
//  Kein DOM, kein Netz: so lässt es sich testen (tests/spielzug.test.mjs).
//
//  Baum:   { id, text, reaktion, stellung, video_clip_id, kinder: [...] }
//  Zustand: { wahl: [n, ...], i }   wahl = gewählter Ast an jeder Verzweigung (der Reihe nach),
//                                   i    = Position auf dem Weg, der sich daraus ergibt.
//  Eine Verzweigung ist ein Knoten mit zwei oder mehr Kindern ("Was macht die Abwehr?").
// ============================================================================

(function () {
  // Halbfeld: 1 m = 20 Einheiten, 20 m Breite = 400, gezeigt werden 15 m Tiefe = 300. Die Torlinie
  // liegt oben bei y = 0, das Tor (3 m = 60) sitzt mittig zwischen x = 170 und x = 230.
  const PFOSTEN_L = 170;
  const PFOSTEN_R = 230;
  const FELD_BREITE = 400;
  const SECHS_METER = 120;
  const NEUN_METER = 180;
  // Siebenmetermarke: 1 m breit, 7 m vor dem Tor.
  const SIEBEN_METER = { x1: 190, x2: 210, y: 140 };

  // Abstand eines Punkts zur Torlinie zwischen den Pfosten. Torraum und Freiwurflinie sind genau die
  // Punkte mit Abstand 6 m bzw. 9 m davon: Viertelkreise um die Pfosten, dazwischen 3 m gerade.
  function abstandZumTor(x, y) {
    const nx = Math.min(Math.max(x, PFOSTEN_L), PFOSTEN_R);
    return Math.hypot(x - nx, y);
  }

  // Die Linie mit dem Abstand `r` zum Tor als Punktfolge, von links nach rechts. Am Seitenaus
  // abgeschnitten (die 9-m-Linie trifft es schon nach rund 3 m Tiefe).
  function linienPunkte(r, schritte = 24) {
    const grad = (rad) => (rad * 180) / Math.PI;
    const bogen = (cx, von, bis) => {      // Winkel in Grad, y zeigt nach unten: 180 = links, 90 = unten, 0 = rechts
      const p = [];
      for (let i = 0; i <= schritte; i++) {
        const a = ((von + ((bis - von) * i) / schritte) * Math.PI) / 180;
        p.push([cx + r * Math.cos(a), r * Math.sin(a)]);
      }
      return p;
    };
    // Beginnt der Bogen links ausserhalb des Felds, startet er genau am Seitenaus (x = 0).
    const startL = PFOSTEN_L - r >= 0 ? 180 : grad(Math.acos((0 - PFOSTEN_L) / r));
    const endR = PFOSTEN_R + r <= FELD_BREITE ? 0 : grad(Math.acos((FELD_BREITE - PFOSTEN_R) / r));
    return bogen(PFOSTEN_L, startL, 90).concat(bogen(PFOSTEN_R, 90, endR));
  }

  // Grundaufstellung: Angriff gegen eine 6:0-Abwehr. Die Abwehr steht knapp vor der 6-m-Linie
  // (etwa 6,8 m vom Tor), der Rückraum ausserhalb der 9-m-Linie, der Kreis auf der 6-m-Linie.
  const ANGRIFF_GRUND = {
    LA: [40, 70], HL: [110, 185], RM: [200, 205], HR: [290, 185], RA: [360, 70], KR: [200, 126],
  };
  const ABWEHR_GRUND = {
    D1: [75, 97], D2: [125, 128], D3: [172, 138], D4: [228, 138], D5: [275, 128], D6: [325, 97],
  };
  const BALL_GRUND = "RM";

  const istVerzweigung = (n) => (n.kinder || []).length > 1;

  // Der Weg von der Wurzel aus. An einer Verzweigung ohne (gültige) Wahl hält er an: `offen`.
  function lauf(baum, wahl) {
    const knoten = [];
    let n = baum;
    let k = 0;
    let offen = null;
    while (n) {
      knoten.push(n);
      const kinder = n.kinder || [];
      if (!kinder.length) break;
      if (kinder.length === 1) { n = kinder[0]; continue; }
      const w = (wahl || [])[k];
      if (!Number.isInteger(w) || w < 0 || w >= kinder.length) { offen = n; break; }
      n = kinder[w];
      k++;
    }
    return { knoten, offen };
  }

  const start = () => ({ wahl: [], i: 0 });

  function aktuell(baum, s) {
    const { knoten } = lauf(baum, s.wahl);
    return knoten[Math.min(s.i, knoten.length - 1)];
  }

  function weiter(baum, s) {
    const { knoten } = lauf(baum, s.wahl);
    return s.i < knoten.length - 1 ? { wahl: s.wahl, i: s.i + 1 } : s;
  }

  function zurueck(baum, s) {
    return s.i > 0 ? { wahl: s.wahl, i: s.i - 1 } : s;
  }

  function enthaeltVideo(n) {
    return n.video_clip_id != null || (n.kinder || []).some(enthaeltVideo);
  }

  // Die Auswahl, wenn der aktuelle Schritt eine Verzweigung ist; sonst leer.
  function optionen(baum, s) {
    const n = aktuell(baum, s);
    if (!istVerzweigung(n)) return [];
    return n.kinder.map((k, i) => ({ n: i, reaktion: k.reaktion || "", hatVideo: enthaeltVideo(k) }));
  }

  // Ast n an der aktuellen Verzweigung wählen. Spätere Wahlen gelten nicht mehr (anderer Ast).
  function waehle(baum, s, n) {
    const { knoten } = lauf(baum, s.wahl);
    const hier = knoten[Math.min(s.i, knoten.length - 1)];
    if (!istVerzweigung(hier) || !Number.isInteger(n) || n < 0 || n >= hier.kinder.length) return s;
    const davor = knoten.slice(0, s.i).filter(istVerzweigung).length;
    return { wahl: (s.wahl || []).slice(0, davor).concat([n]), i: s.i + 1 };
  }

  const kopie = (o) => JSON.parse(JSON.stringify(o));

  // Aufstellung je Schritt. Ein Schritt nennt nur, was sich ändert; alles andere bleibt, wie es
  // im Schritt davor war (am Anfang: Grundaufstellung).
  function stellungen(knoten, grund) {
    let aktuellSt = grund
      ? kopie(grund)
      : { angriff: kopie(ANGRIFF_GRUND), abwehr: kopie(ABWEHR_GRUND), ball: BALL_GRUND };
    return knoten.map((n) => {
      const st = (n && n.stellung) || {};
      aktuellSt = {
        angriff: Object.assign({}, aktuellSt.angriff, kopie(st.angriff || {})),
        abwehr: Object.assign({}, aktuellSt.abwehr, kopie(st.abwehr || {})),
        ball: st.ball || aktuellSt.ball,
      };
      return kopie(aktuellSt);
    });
  }

  // Jede Lösung (Blatt) mit ihrem Weg aus Abwehrreaktionen und dem Videostatus.
  function videoUebersicht(baum) {
    const ergebnis = [];
    (function geh(n, pfad) {
      const p = n.reaktion ? pfad.concat([n.reaktion]) : pfad;
      if (!(n.kinder || []).length) {
        ergebnis.push({ pfad: p, hatVideo: n.video_clip_id != null, id: n.id });
        return;
      }
      for (const k of n.kinder) geh(k, p);
    })(baum, []);
    return ergebnis;
  }

  // ------------------------------------------------------------------------ Bearbeiten --
  //  Der Editor ändert den Baum nie an Ort und Stelle: jede Funktion gibt einen NEUEN Baum zurück
  //  (Original bleibt unverändert). So bleibt "Abbrechen" trivial (alten Baum behalten), und die
  //  Funktionen lassen sich ohne Oberfläche testen. Grenzen wie auf dem Server (daten/spielzug.py).
  const MAX_AESTE = 6;
  const MAX_TIEFE = 12;
  const FELD_TIEFE = 300;
  const rund1 = (v) => Math.round(v * 10) / 10;

  function finde(n, id) {
    if (!n) return null;
    if (n.id === id) return n;
    for (const k of n.kinder || []) {
      const r = finde(k, id);
      if (r) return r;
    }
    return null;
  }

  // Der Weg von der Wurzel bis zum Knoten (inklusive), sonst null.
  function pfadZu(n, id) {
    if (!n) return null;
    if (n.id === id) return [n];
    for (const k of n.kinder || []) {
      const r = pfadZu(k, id);
      if (r) return [n].concat(r);
    }
    return null;
  }

  function kleinsteId(n) {
    const eigene = typeof n.id === "number" ? n.id : 0;
    return Math.min(eigene, ...(n.kinder || []).map(kleinsteId));
  }

  // Ein leerer Spielzug: ein Schritt, der die Grundaufstellung erbt. IDs unter 0 sind vorläufig,
  // bis der Server beim Speichern echte vergibt.
  function neuerBaum() {
    return { id: -1, text: "Grundaufstellung", reaktion: null, stellung: {}, video_clip_id: null, kinder: [] };
  }

  // Einen Schritt unter `id` anhängen. Ab dem zweiten Ast braucht jeder Ast eine Beschriftung
  // ("Was macht die Abwehr?"): fehlende werden mit "Reaktion N" vorbelegt. Grenzen erreicht:
  // {baum: unverändert, neueId: null}.
  function fuegeKindEin(baum, id) {
    const b = kopie(baum);
    const pfad = pfadZu(b, id);
    if (!pfad) return { baum, neueId: null };
    const n = pfad[pfad.length - 1];
    if (n.kinder.length >= MAX_AESTE || pfad.length >= MAX_TIEFE) return { baum, neueId: null };
    const neueId = Math.min(kleinsteId(b), 0) - 1;
    n.kinder.push({ id: neueId, text: "Neuer Schritt", reaktion: null, stellung: {}, video_clip_id: null, kinder: [] });
    if (n.kinder.length > 1) {
      n.kinder.forEach((k, i) => { if (!k.reaktion || !k.reaktion.trim()) k.reaktion = "Reaktion " + (i + 1); });
    }
    return { baum: b, neueId };
  }

  // Knoten samt allem darunter entfernen. Die Wurzel zu löschen leert den ganzen Baum (null).
  function loescheKnoten(baum, id) {
    if (baum.id === id) return null;
    const b = kopie(baum);
    (function weg(n) {
      n.kinder = (n.kinder || []).filter((k) => k.id !== id);
      n.kinder.forEach(weg);
    })(b);
    return b;
  }

  const ERLAUBTE_FELDER = ["text", "reaktion", "video_clip_id"];
  function setze(baum, id, felder) {
    const b = kopie(baum);
    const n = finde(b, id);
    if (!n) return baum;
    for (const k of ERLAUBTE_FELDER) if (k in felder) n[k] = felder[k];
    return b;
  }

  // Eine Position ins Feld zwingen: nicht ausserhalb, und niemand im Torraum (dort darf keine Feldspielerin
  // stehen). Wer hineingezogen wird, landet an der 6-m-Linie, in Zugrichtung.
  function begrenze(xy) {
    let x = Math.min(Math.max(xy[0], 0), FELD_BREITE);
    let y = Math.min(Math.max(xy[1], 0), FELD_TIEFE);
    const nx = Math.min(Math.max(x, PFOSTEN_L), PFOSTEN_R);
    const d = Math.hypot(x - nx, y);
    if (d < SECHS_METER) {
      if (d === 0) { y = SECHS_METER; }
      else { x = nx + ((x - nx) / d) * SECHS_METER; y = (y / d) * SECHS_METER; }
    }
    return [rund1(x), rund1(y)];
  }

  function setzePosition(baum, id, seite, name, xy) {
    const namen = seite === "angriff" ? ANGRIFF_GRUND : seite === "abwehr" ? ABWEHR_GRUND : null;
    if (!namen || !(name in namen)) return baum;
    const b = kopie(baum);
    const n = finde(b, id);
    if (!n) return baum;
    n.stellung = n.stellung || {};
    n.stellung[seite] = Object.assign({}, n.stellung[seite], { [name]: begrenze(xy) });
    return b;
  }

  function setzeBall(baum, id, name) {
    if (!(name in ANGRIFF_GRUND)) return baum;
    const b = kopie(baum);
    const n = finde(b, id);
    if (!n) return baum;
    n.stellung = Object.assign({}, n.stellung, { ball: name });
    return b;
  }

  // Alle eigenen Positionen und den Ball eines Schritts verwerfen: er erbt dann wieder vom Schritt davor.
  function setzeZurueck(baum, id) {
    const b = kopie(baum);
    const n = finde(b, id);
    if (!n) return baum;
    n.stellung = {};
    return b;
  }

  // Die Aufstellung an einem Knoten, inklusive allem, was er von den Schritten davor erbt.
  function stellungFuer(baum, id) {
    const pfad = pfadZu(baum, id);
    return pfad ? stellungen(pfad)[pfad.length - 1] : null;
  }

  // Der Zustand (Wahl + Position), der genau auf diesen Knoten zeigt.
  function zustandFuer(baum, id) {
    const pfad = pfadZu(baum, id);
    if (!pfad) return null;
    const wahl = [];
    for (let i = 0; i < pfad.length - 1; i++) {
      if (istVerzweigung(pfad[i])) wahl.push(pfad[i].kinder.findIndex((k) => k.id === pfad[i + 1].id));
    }
    return { wahl, i: pfad.length - 1 };
  }

  // Vorbelegung, wenn ein Trainer zum ersten Mal Text zu einem Playbook-Spielzug schreibt. Nur die
  // Fragen, kein vorgegebener Inhalt; gespeichert wird erst, wenn der Trainer selbst speichert.
  const BESCHREIBUNG_VORLAGE = "## Worum geht es?\n\n\n## Was wollen wir erreichen?\n\n";

  window.SpielzugLogik = {
    BESCHREIBUNG_VORLAGE,
    MAX_AESTE, MAX_TIEFE,
    finde, pfadZu, neuerBaum, fuegeKindEin, loescheKnoten, setze, begrenze, setzePosition, setzeBall,
    setzeZurueck, stellungFuer, zustandFuer,
    ANGRIFF_GRUND, ABWEHR_GRUND, BALL_GRUND,
    PFOSTEN_L, PFOSTEN_R, FELD_BREITE, SECHS_METER, NEUN_METER, SIEBEN_METER,
    abstandZumTor, linienPunkte,
    lauf, start, aktuell, weiter, zurueck, optionen, waehle, stellungen, videoUebersicht,
  };
})();
