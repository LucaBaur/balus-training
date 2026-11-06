"use strict";

// ============================================================================
//  kasse-logik.js — Mannschaftskasse als reine Funktionen (kein DOM, kein Netz).
//
//  Geld wird überall als GANZE CENT geführt (Integer), nie als Kommazahl: 0,10 + 0,20
//  ergibt als Gleitkomma 0,30000000000000004, als Cent exakt 30. Umgerechnet wird nur
//  an den Rändern: beim Anzeigen (euro) und beim Eingeben (parseEuro).
//  Die Grenze unten gilt am Server genauso (daten/kasse.py, KASSE_MAX_CENT).
// ============================================================================

(function () {
  const MAX_CENT = 1000000;           // 10.000 €: fängt vergessene Kommas ab
  const NBSP = " ";              // geschütztes Leerzeichen: "12,50 €" bricht nicht um

  // Die vier Arten einer Buchung. `spielerin`: gehört der Posten einer Spielerin?
  const ARTEN = [
    { key: "forderung", label: "Strafe / Beitrag", spielerin: true, hinweis: "Die Spielerin schuldet der Kasse Geld." },
    { key: "einzahlung", label: "Einzahlung", spielerin: true, hinweis: "Die Spielerin hat in die Kasse bezahlt." },
    { key: "ausgabe", label: "Ausgabe", spielerin: false, hinweis: "Die Kasse bezahlt etwas, z. B. Getränke." },
    { key: "einnahme", label: "Einnahme", spielerin: false, hinweis: "Sonstiges Geld in der Kasse, z. B. eine Spende." },
  ];

  // 1250 -> "12,50 €", 100000 -> "1.000,00 €", -1000 -> "−10,00 €" (echtes Minuszeichen).
  function euro(cent) {
    let n = Math.round(Number(cent));
    if (!isFinite(n)) n = 0;
    const betrag = Math.abs(n);
    const euros = String(Math.floor(betrag / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    const rest = String(betrag % 100).padStart(2, "0");
    return (n < 0 ? "−" : "") + euros + "," + rest + NBSP + "€";
  }

  // "12,50" / "12.50" / "1.234,56" / "12" / "5 €" -> Cent. Ungültig, null oder zu hoch -> null.
  // Es wird mit Text gerechnet, nicht mit Kommazahlen (0,29 * 100 wäre 28,999…).
  function parseEuro(text) {
    if (typeof text !== "string") return null;
    const s = text.replace(/€/g, "").replace(/\s+/g, "");
    if (!s) return null;
    let euros, cent;
    if (s.includes(",")) {
      // Deutsch: Punkte trennen Tausender, das Komma die Cent.
      const m = /^(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{1,2}))?$/.exec(s);
      if (!m) return null;
      euros = m[1]; cent = m[2];
    } else if (/^\d+\.\d{1,2}$/.test(s)) {
      [euros, cent] = s.split(".");                       // "12.50": ein Punkt mit ein, zwei Stellen = Dezimalpunkt
    } else {
      const m = /^(\d{1,3}(?:\.\d{3})+|\d+)$/.exec(s);    // "1.000": Tausenderpunkte
      if (!m) return null;
      euros = m[1];
    }
    const gesamt = parseInt(euros.replace(/\./g, ""), 10) * 100 + (cent ? parseInt(cent.padEnd(2, "0"), 10) : 0);
    return gesamt > 0 && gesamt <= MAX_CENT ? gesamt : null;
  }

  // Was die Buchung für das Bargeld der Kasse bedeutet. Eine Forderung ist noch kein Geld.
  function wirkung(b) {
    if (b.storniert) return 0;
    if (b.art === "einzahlung" || b.art === "einnahme") return b.betrag_cent;
    if (b.art === "ausgabe") return -b.betrag_cent;
    return 0;
  }

  const kassenstand = (buchungen) => buchungen.reduce((summe, b) => summe + wirkung(b), 0);

  // Katalogposten -> Betrag in Cent. Je Einheit (Min/Teil) wird mit der Anzahl multipliziert, Trainer zahlen das
  // Doppelte. Kasten-Posten (cent null) und Unsinn geben null: dann traegt die Kassenwartin den Betrag selbst ein.
  function katalogBetrag(eintrag, anzahl, trainer) {
    if (!eintrag || typeof eintrag.cent !== "number") return null;
    let n = 1;
    if (eintrag.einheit) {
      n = Number(anzahl);
      if (!Number.isInteger(n) || n < 1) return null;
    }
    const cent = eintrag.cent * n * (trainer ? 2 : 1);
    return cent <= MAX_CENT ? cent : null;
  }

  // Buchungstext zum Katalogposten, hoechstens 120 Zeichen (Grenze am Server).
  function katalogText(eintrag, anzahl, trainer) {
    const zusatz = [];
    if (eintrag.einheit) zusatz.push(Number(anzahl) + " " + eintrag.einheit);
    if (trainer) zusatz.push("Trainer ×2");
    const text = eintrag.label + (zusatz.length ? " (" + zusatz.join(", ") + ")" : "");
    return text.slice(0, 120);
  }

  function offenText(cent) {
    if (cent > 0) return "schuldet " + euro(cent);
    if (cent < 0) return "hat " + euro(-cent) + " Guthaben";
    return "alles bezahlt";
  }

  window.KasseLogik = { MAX_CENT, ARTEN, euro, parseEuro, wirkung, kassenstand, offenText, katalogBetrag, katalogText };
})();
