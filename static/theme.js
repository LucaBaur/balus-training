"use strict";

// ============================================================================
//  theme.js — Darstellung hell / dunkel / automatisch.
//  Die Wahl liegt in localStorage ("darstellung"). "auto" folgt dem Gerät
//  (prefers-color-scheme). Angewendet wird sie als data-theme am <html>-Element;
//  das CSS stellt darüber die Farben um. Läuft im <head> VOR dem ersten Zeichnen,
//  damit beim Start nichts kurz in der falschen Farbe aufblitzt.
//  Der Speicher kann fehlen oder werfen (privates Fenster): dann gilt "auto".
// ============================================================================

(function () {
  const MODI = ["auto", "hell", "dunkel"];
  // Farbe der Statusleiste (theme-color): der Kopf der App in beiden Darstellungen.
  const FARBEN = { hell: "#122F5E", dunkel: "#0B1E3D" };
  const SCHLUESSEL = "darstellung";

  const normiere = (wahl) => (MODI.includes(wahl) ? wahl : "auto");

  function effektiv(wahl, systemDunkel) {
    const w = normiere(wahl);
    return w === "auto" ? (systemDunkel ? "dunkel" : "hell") : w;
  }

  function laden(speicher) {
    try { return normiere(speicher && speicher.getItem(SCHLUESSEL)); } catch (_) { return "auto"; }
  }

  function speichern(speicher, wahl) {
    const w = normiere(wahl);
    try { if (speicher) speicher.setItem(SCHLUESSEL, w); } catch (_) { /* Wahl gilt trotzdem bis zum Neuladen */ }
    return w;
  }

  function anwenden(doc, wahl, systemDunkel) {
    const e = effektiv(wahl, systemDunkel);
    doc.documentElement.dataset.theme = e;
    const meta = doc.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = FARBEN[e];
    return e;
  }

  window.Theme = { MODI, FARBEN, normiere, effektiv, laden, speichern, anwenden };
})();
