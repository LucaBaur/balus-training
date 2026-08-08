"use strict";

// ============================================================================
//  teams-local.js — Faire Team-Aufteilung IM BROWSER (Port von teams.py).
//  Damit die Team-Einteilung offline funktioniert. Gleiche Regel wie am Server:
//  zwei moeglichst gleich starke Teams (minimale ELO-Differenz); bei >= 2
//  Torhueterinnen bekommt jedes Team eine. Erwartet Spieler-Objekte mit
//  { id, elo, position } ("Tor"/"Feld").
// ============================================================================

(function () {
  const TOR = "Tor";
  const schnitt = (t) => t.reduce((s, p) => s + p.elo, 0) / t.length;

  // Alle k-elementigen Index-Kombinationen aus 0..n-1 (aufsteigend).
  function* kombis(n, k) {
    const idx = Array.from({ length: k }, (_, i) => i);
    if (k === 0) { yield []; return; }
    while (true) {
      yield idx.slice();
      let i = k - 1;
      while (i >= 0 && idx[i] === n - k + i) i--;
      if (i < 0) return;
      idx[i]++;
      for (let j = i + 1; j < k; j++) idx[j] = idx[j - 1] + 1;
    }
  }

  function anzahlKombis(n, k) {
    let r = 1;
    for (let i = 0; i < k; i++) { r = (r * (n - i)) / (i + 1); if (r > 1e7) return r; }
    return r;
  }

  function besteTeilung(spieler, groesseA, torPflicht) {
    const n = spieler.length;
    let bestes = null;
    for (const combo of kombis(n, groesseA)) {
      const set = new Set(combo);
      const a = combo.map((i) => spieler[i]);
      const b = spieler.filter((_, i) => !set.has(i));
      if (torPflicht) {
        if (!a.some((p) => p.position === TOR)) continue;
        if (!b.some((p) => p.position === TOR)) continue;
      }
      const diff = Math.abs(schnitt(a) - schnitt(b));
      if (!bestes || diff < bestes.diff) bestes = { diff, a, b };
    }
    return bestes;
  }

  // Fallback fuer sehr grosse Gruppen (Brute Force zu teuer): gieriges Verteilen.
  function gierig(spieler, groesseA, torPflicht) {
    const sortiert = [...spieler].sort((x, y) => y.elo - x.elo);
    const n = sortiert.length;
    const A = [], B = [];
    const summe = (t) => t.reduce((s, p) => s + p.elo, 0);
    const gesetzt = new Set();
    if (torPflicht) {
      const tw = sortiert.filter((p) => p.position === TOR);
      if (tw.length >= 2) { A.push(tw[0]); B.push(tw[1]); gesetzt.add(tw[0]); gesetzt.add(tw[1]); }
    }
    for (const p of sortiert) {
      if (gesetzt.has(p)) continue;
      if (A.length >= groesseA) B.push(p);
      else if (B.length >= n - groesseA) A.push(p);
      else if (summe(A) <= summe(B)) A.push(p);
      else B.push(p);
    }
    return [A, B];
  }

  function generiere(spieler) {
    const n = spieler.length;
    if (n < 2) return [spieler.slice(), []];
    const groesseA = Math.floor(n / 2);
    const torPflicht = spieler.filter((p) => p.position === TOR).length >= 2;

    if (anzahlKombis(n, groesseA) > 300000) return gierig(spieler, groesseA, torPflicht);

    let bestes = besteTeilung(spieler, groesseA, torPflicht);
    if (!bestes) bestes = besteTeilung(spieler, groesseA, false); // Tor-Pflicht unerfuellbar
    return [bestes.a, bestes.b];
  }

  // ---- Zwei bis vier Teams (Port von teams.teams_generieren_n) -------------
  //  Ab drei Teams waere die vollstaendige Suche zu teuer: erst gierig
  //  verteilen (Staerkste zuerst ins kleinste/schwaechste Team), danach durch
  //  Tauschen verbessern, solange die Staerke-Spanne kleiner wird.
  const summe = (t) => t.reduce((s, p) => s + p.elo, 0);
  const spanne = (teams) => {
    const s = teams.filter((t) => t.length).map(schnitt);
    return s.length ? Math.max(...s) - Math.min(...s) : 0;
  };
  const torAbdeckung = (teams) =>
    teams.filter((t) => t.some((p) => p.position === TOR)).length;

  function verbessern(teams, torZiel, runden = 40) {
    for (let r = 0; r < runden; r++) {
      const akt = spanne(teams);
      let bestes = null;
      for (let i = 0; i < teams.length; i++) {
        for (let j = i + 1; j < teams.length; j++) {
          for (let x = 0; x < teams[i].length; x++) {
            for (let y = 0; y < teams[j].length; y++) {
              const a = teams[i][x], b = teams[j][y];
              teams[i][x] = b; teams[j][y] = a;
              const neu = spanne(teams), tore = torAbdeckung(teams);
              teams[i][x] = a; teams[j][y] = b;
              if (tore < torZiel || neu >= akt - 1e-9) continue;
              if (!bestes || neu < bestes[0]) bestes = [neu, i, j, x, y];
            }
          }
        }
      }
      if (!bestes) return;
      const [, i, j, x, y] = bestes;
      const a = teams[i][x];
      teams[i][x] = teams[j][y]; teams[j][y] = a;
    }
  }

  function generiereN(spieler, anzahl) {
    anzahl = Math.max(2, Math.min(Number(anzahl) || 2, 4));
    if (anzahl === 2) return generiere(spieler);
    if (spieler.length < anzahl) {
      const t = spieler.map((p) => [p]);
      while (t.length < anzahl) t.push([]);
      return t;
    }
    const teams = Array.from({ length: anzahl }, () => []);
    const tw = spieler.filter((p) => p.position === TOR).sort((a, b) => b.elo - a.elo);
    const feld = spieler.filter((p) => p.position !== TOR).sort((a, b) => b.elo - a.elo);
    tw.forEach((p, i) => teams[i % anzahl].push(p));

    const maxGroesse = Math.ceil(spieler.length / anzahl);
    for (const p of feld) {
      const kand = teams.filter((t) => t.length < maxGroesse);
      const pool = kand.length ? kand : teams;
      let ziel = pool[0];
      for (const t of pool) {
        if (t.length < ziel.length || (t.length === ziel.length && summe(t) < summe(ziel))) ziel = t;
      }
      ziel.push(p);
    }
    verbessern(teams, Math.min(anzahl, tw.length));
    return teams;
  }

  window.TeamsLokal = { generiere, generiereN };
})();
