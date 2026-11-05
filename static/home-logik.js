"use strict";

// ============================================================================
//  home-logik.js — Was auf den Startseiten steht, als reine Funktionen.
//  Nimmt Daten der API (Termine, Tabelle, Clips, Analysen) und liefert, was die
//  Oberfläche zeigen soll. Kein DOM, kein Netz: so lässt es sich testen.
// ============================================================================

(function () {
  const SPIEL_ARTEN = ["testspiel", "ligaspiel"];
  const TAGE = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
  const TAG_MS = 86400000;
  const GRENZE_DUENN = 5;           // bis hier "nur n Zusagen" (wie terminStufe "kritisch" in app.js)
  const VORAUS_TAGE = 14;           // so weit schaut die Warnung für dünne Termine
  const ANTWORT_TAGE = 3;           // "ohne Antwort" nur für den Termin in den nächsten Tagen
  const NACHBEREITUNG_TAGE = 14;    // so lange zählt ein Spiel als "Nachbereitung offen"

  const istSpiel = (t) => SPIEL_ARTEN.includes(t.art);
  const mittag = (iso) => new Date((iso || "") + "T12:00:00");

  function wochentag(iso) {
    const d = mittag(iso);
    return !iso || isNaN(d) ? "" : TAGE[d.getDay()];
  }

  const tageZwischen = (von, bis) => Math.round((mittag(bis) - mittag(von)) / TAG_MS);

  // "heute", "morgen" oder der Wochentag - klein geschrieben, wie mitten im Satz.
  function relativ(heute, datum) {
    const n = tageZwischen(heute, datum);
    return n === 0 ? "heute" : n === 1 ? "morgen" : wochentag(datum);
  }
  const gross = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  const nachDatum = (a, b) => (a.datum || "").localeCompare(b.datum || "") || (a.id - b.id);
  const kommend = (liste, heute) => (liste || []).filter((t) => (t.datum || "") >= heute).sort(nachDatum);

  // Das nächste Training (Spiele zählen nicht).
  const naechstesTraining = (liste, heute) => kommend(liste, heute).find((t) => !istSpiel(t)) || null;

  const naechsteSpiele = (liste, heute, n = 3) => kommend(liste, heute).filter(istSpiel).slice(0, n);

  // Termine, auf die diese Person noch nicht geantwortet hat; `ohneId` lässt eins weg
  // (das, das schon groß oben steht).
  const offeneAntworten = (liste, heute, ohneId = null) =>
    kommend(liste, heute).filter((t) => !t.meine_status && t.id !== ohneId);

  // Die eigene Zeile der Tabelle mit je einem Nachbarn darüber und darunter.
  function tabellenAuszug(tabelle) {
    const z = tabelle || [];
    const i = z.findIndex((r) => r.eigen);
    if (i < 0) return null;
    const zeile = (r) => ({ platz: r.platz, team: r.team, punkte: `${r.punkte_plus}:${r.punkte_minus}`, eigen: !!r.eigen });
    return {
      platz: z[i].platz,
      punkte: `${z[i].punkte_plus}:${z[i].punkte_minus}`,
      zeilen: z.slice(Math.max(0, i - 1), Math.min(z.length, i + 2)).map(zeile),
    };
  }

  // "Neu für dich": Clips und Videoanalysen, die seit dem letzten Ansehen dazugekommen sind.
  // `gesehen` = {clip, analyse} (höchste gesehene ID) oder null beim allerersten Mal: dann
  // wird nichts als neu gemeldet, sondern nur die Grundlinie gemerkt - sonst wäre bei der
  // ersten Nutzung alles "neu".
  function neuFuerDich({ clips, analysen, gesehen }) {
    const cl = clips || [];
    const an = (analysen || []).filter((a) => a.video_da);
    const hoechste = (l) => l.reduce((m, x) => Math.max(m, x.id), 0);
    const grundlinie = { clip: hoechste(cl), analyse: hoechste(an) };
    if (!gesehen) return { items: [], anzahl: 0, grundlinie };
    const neueClips = cl.filter((c) => c.id > (gesehen.clip || 0)).sort((a, b) => b.id - a.id)
      .map((c) => ({ art: "clip", id: c.id, titel: c.titel, sub: c.notiz || "" }));
    const neueAnalysen = an.filter((a) => a.id > (gesehen.analyse || 0)).sort((a, b) => b.id - a.id)
      .map((a) => ({ art: "analyse", id: a.id, titel: `Videoanalyse: ${a.gegner}`, sub: a.datum || "" }));
    const alle = [...neueClips, ...neueAnalysen];
    return { items: alle.slice(0, 3), anzahl: alle.length, grundlinie };
  }

  // Nach dem Ansehen: die höchste gesehene ID merken, nie rückwärts.
  function alsGesehen(gesehen, art, id) {
    const basis = gesehen || { clip: 0, analyse: 0 };
    return { ...basis, [art]: Math.max(basis[art] || 0, id) };
  }

  // Aufgabenliste des Trainers ("Braucht dich"), wichtigstes zuerst.
  function trainerAufgaben({ trainings, todosWartend, fragen, heute }) {
    const alle = trainings || [];
    const bald = kommend(alle, heute);
    const aufgaben = [];
    const ziel = (t) => ({ ober: "training", unter: "trainings", termin: t.id });

    // 1. Termine, bei denen es nicht reicht
    bald.filter((t) => !t.freiwillig && tageZwischen(heute, t.datum) <= VORAUS_TAGE && (t.anwesend || 0) <= GRENZE_DUENN)
      .slice(0, 3).forEach((t) => {
        const n = t.anwesend || 0;
        aufgaben.push({
          art: "duenn", stufe: "warn",
          titel: `${gross(relativ(heute, t.datum))}: nur ${n} ${n === 1 ? "Zusage" : "Zusagen"}`,
          sub: [t.titel || "Termin", t.uhrzeit].filter(Boolean).join(" · "),
          ziel: ziel(t),
        });
      });

    // 2. Wer hat noch nicht geantwortet? Nur für den nächsten Termin in den nächsten Tagen.
    const erster = bald.find((t) => !t.freiwillig);      // freiwillige Trainings: kein Nachfragen
    if (erster && tageZwischen(heute, erster.datum) <= ANTWORT_TAGE) {
      const antworten = (erster.anwesend || 0) + (erster.abgesagt || 0) + (erster.unsicher || 0);
      const offen = Math.max(0, (erster.kader || 0) - antworten);
      if (offen > 0) {
        aufgaben.push({
          art: "offen", stufe: "info", titel: `${offen} ohne Antwort`,
          sub: `${erster.titel || "Termin"} · ${relativ(heute, erster.datum)}`, ziel: ziel(erster),
        });
      }
    }

    // 3. Gespielte Spiele ohne Nachbereitung (nur die letzten zwei Wochen)
    (alle.filter((t) => istSpiel(t) && (t.datum || "") < heute && t.hat_nachbereitung === 0
                        && tageZwischen(t.datum, heute) <= NACHBEREITUNG_TAGE)
      .sort((a, b) => nachDatum(b, a)).slice(0, 2)).forEach((t) => {
        aufgaben.push({
          art: "nachbereitung", stufe: "info", titel: "Nachbereitung offen",
          sub: t.gegner ? `Spiel gegen ${t.gegner} · ${wochentag(t.datum)}` : (t.titel || "Spiel"), ziel: ziel(t),
        });
      });

    // 4. Fragen und Kommentare von Spielerinnen zu Videos, auf die noch keine Antwort kam
    (fragen || []).slice(0, 3).forEach((f) => {
      aufgaben.push({
        art: "frage", stufe: "info",
        titel: f.anzahl === 1 ? `Frage von ${(f.von || [])[0] || "einer Spielerin"}` : `${f.anzahl} offene Fragen`,
        sub: f.titel || "Video", ziel: { video: f.ziel, titel: f.titel || "Video" },
      });
    });

    // 5. To-Dos, deren Woche vorbei ist und zu denen noch Feedback fehlt
    // (`todosWartend` zaehlt schon nur die abgelaufenen Wochen, siehe db.todos_team)
    if (todosWartend > 0) {
      aufgaben.push({
        art: "todos", stufe: "info",
        titel: todosWartend === 1 ? "1 To-Do wartet auf Feedback" : `${todosWartend} To-Dos warten auf Feedback`,
        sub: "Wochenziele der Spielerinnen", ziel: { ober: "team", unter: "todos" },
      });
    }
    return aufgaben;
  }

  window.HomeLogik = {
    istSpiel, wochentag, relativ, naechstesTraining, naechsteSpiele, offeneAntworten,
    tabellenAuszug, neuFuerDich, alsGesehen, trainerAufgaben,
  };
})();
