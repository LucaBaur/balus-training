import { merkeGeladen, vorZeit, zeigeAktualisiert } from "../core/aktualisieren.js";
import { api } from "../core/api.js";
import { nutzungBereichName } from "../core/tracking.js";
import { $, escape } from "../core/ui.js";
import { APP_VERSION } from "../core/version.js";

// ---- Nutzung-Hilfen (rein, getestet in tests/nutzung_ui.test.mjs) ----
//  Keine Zugriffe auf DOM oder globalen Zustand - der Test laedt genau diesen Abschnitt.

// Sekunden als "4 Min." / "1 Std. 12 Min."; nichts gemessen -> Gedankenstrich.
function dauerText(sek) {
  if (!sek || sek < 1) return "–";
  if (sek < 60) return "<1 Min.";
  const min = Math.floor(sek / 60), h = Math.floor(min / 60), m = min % 60;
  if (!h) return min + " Min.";
  return h + " Std." + (m ? " " + m + " Min." : "");
}
// "2× · 4 Min."; ohne gemessene Dauer nur "2×" (kein Gedankenstrich-Rauschen in der Zeile).
function anzahlDauer(anzahl, sek) {
  return anzahl + "×" + (sek ? " · " + dauerText(sek) : "");
}
// Ganze Sekunden zwischen zwei Zeitstempeln (ms); 0 = zu kurz/ungueltig, nicht melden.
// Die Grenze entspricht dem Server (30 Min.): laenger am Stueck ist ein vergessener Tab.
export function verweilSegment(startMs, endeMs, grenzeS = 1800) {
  if (!Number.isFinite(startMs) || !Number.isFinite(endeMs) || endeMs <= startMs) return 0;
  return Math.min(Math.round((endeMs - startMs) / 1000), grenzeS);
}
// Anzeigename eines Videos. Der Server loest Spielzuege auf (label/zeit); fehlt das
// (aeltere Daten, geloeschte Szene), bleibt es beim gespeicherten Titel mit Art davor.
function nutzungVideoLabel(v) {
  const aufgeloest = v.label && v.label !== v.titel;
  if (aufgeloest) return v.label + (v.zeit ? " · " + v.zeit : "");
  const art = { clip: "Szene", szene: "Spielzug", spiel: "Ganzes Spiel", analyse: "Videoanalyse" }[String(v.ziel).split(":")[0]] || "Video";
  return art + ": " + (v.titel || v.ziel);
}
// Videos je Spiel buendeln (Reihenfolge = erstes Auftreten); Videos ohne Spiel kommen in "Weitere Videos".
// Innerhalb eines Spiels nach Spielzeit (t) sortiert, das ganze Spiel (ohne t) zuerst; Array.sort ist stabil,
// Eintraege ohne t bleiben also in Eingabereihenfolge.
function gruppiereNachSpiel(videos) {
  const gruppen = new Map();
  for (const v of videos) {
    const name = v.spiel || "Weitere Videos";
    if (!gruppen.has(name)) gruppen.set(name, []);
    gruppen.get(name).push(v);
  }
  return [...gruppen].map(([spiel, items]) => ({
    spiel, items: items.slice().sort((a, b) => (a.t == null ? -1 : a.t) - (b.t == null ? -1 : b.t)),
  }));
}
// Spielzug-Uebersicht (Team -> Videos, Trainer). Eingabe: flache Szenen wie von
// /api/szenen-uebersicht ({id, art, name, spiel, fehlt, gesehen, kein_video}).
export const _nameKey = (n) => String(n || "").trim().toLowerCase();
// Filter: Ereignisse (Tor, Fehlwurf ...) nur auf Wunsch; Name ohne Beachtung der Schreibweise;
// "nur offene" = mindestens eine Beteiligte hat den Clip noch nicht komplett gesehen.
export function filtereSzenen(szenen, { name = null, nurOffen = false, mitEreignissen = false } = {}) {
  const gesucht = name ? _nameKey(name) : null;
  return szenen.filter((s) =>
    (mitEreignissen || s.art === "zug")
    && (!gesucht || _nameKey(s.name) === gesucht)
    && (!nurOffen || (s.fehlt && s.fehlt.length > 0)));
}
// Namens-Chips: [{name, anzahl}], haeufigster zuerst; "Kreisel" und "kreisel" zaehlen zusammen.
export function namenMitZahl(szenen) {
  const zaehler = new Map();
  for (const s of szenen) {
    const k = _nameKey(s.name);
    if (!zaehler.has(k)) zaehler.set(k, { name: s.name, anzahl: 0 });
    zaehler.get(k).anzahl++;
  }
  return [...zaehler.values()].sort((a, b) => b.anzahl - a.anzahl || a.name.localeCompare(b.name, "de"));
}
// "Nach Name": alle Kreisel zusammen ueber alle Spiele; Reihenfolge der Eintraege bleibt wie eingegeben.
export function gruppiereNachName(szenen) {
  const gruppen = new Map();
  for (const s of szenen) {
    const k = _nameKey(s.name);
    if (!gruppen.has(k)) gruppen.set(k, { name: s.name, items: [] });
    gruppen.get(k).items.push(s);
  }
  return [...gruppen.values()].sort((a, b) => b.items.length - a.items.length || a.name.localeCompare(b.name, "de"));
}
// Stand einer Spielerin bei einer Szene: komplett | angetippt (geoeffnet, aber unter 60 %) | offen | kein_video.
export function szenenStatus(szene, spielerName) {
  if (szene.kein_video) return "kein_video";
  const g = (szene.gesehen || []).find((x) => x.name === spielerName);
  return !g ? "offen" : g.gespielt > 0 ? "komplett" : "angetippt";
}
// Anzeige neben dem ↻-Knopf. Ohne Verbindung wird der Stand ausdruecklich als solcher benannt,
// damit alte Daten nie wie frische aussehen. `ts` und `jetzt` in Millisekunden.
export function aktualisiertText(ts, jetzt, online) {
  const uhr = (t) => new Date(t).toTimeString().slice(0, 5);          // HH:MM, Ortszeit
  if (ts == null) return online ? "noch nicht geladen" : "offline – noch nicht geladen";
  if (!online) return "offline – Stand von " + uhr(ts);
  const min = Math.floor(Math.max(0, jetzt - ts) / 60000);
  if (min < 1) return "gerade aktualisiert";
  if (min < 60) return "aktualisiert vor " + min + " Min.";
  return "Stand von " + uhr(ts);
}
// ---- Ende Nutzung-Hilfen ----
// Trainer-Seite: Team -> Nutzung.
let nutzungDaten = null;
export async function ladeNutzung() {
  const el = $("#nutzung-inhalt");
  if (!nutzungDaten) el.innerHTML = '<p class="hinweis">Lädt …</p>';
  try { nutzungDaten = await api("/api/nutzung"); merkeGeladen("nutzung"); }
  catch (_) {
    if (!nutzungDaten) {
      el.innerHTML = '<p class="hinweis">Nutzung konnte nicht geladen werden – dafür brauchst du eine Verbindung.</p>';
      return;
    }
    zeigeAktualisiert();                           // alter Stand: die Anzeige nennt ihn beim Namen
  }
  renderNutzung();
}
function nutzungGeraetZeile(g) {
  const klein = [g.bildschirm.replace("x", "×"), g.modell, g.app_version,
                 g.sw ? "Service Worker aktiv" : "ohne Service Worker", "zuletzt " + vorZeit(g.zuletzt)]
    .filter(Boolean).join(" · ");
  const alt = g.app_version && g.app_version !== APP_VERSION;
  return `<div class="nk-zeile"><span>${escape([g.os, g.browser, g.modus].filter(Boolean).join(" · "))}`
       + `<small${alt ? ' class="alt"' : ""}>${escape(klein)}${alt ? " · ältere Version" : ""}</small></span></div>`;
}
function renderNutzungFehler(fehler, tage) {
  if (!fehler.length) return `<h3 class="nutz-h">Fehler</h3><p class="hinweis">In den letzten ${tage} Tagen wurde kein Fehler gemeldet ✓</p>`;
  let html = `<h3 class="nutz-h">Fehler (letzte ${tage} Tage)</h3>`;
  for (const f of fehler) {
    const quelle = { script: "Skript", promise: "Skript", video: "Video" }[f.quelle] || "Fehler";
    html += `<details class="nutz-karte fehler"><summary>
        <span class="nk-name nk-fehler">${escape(f.meldung)}</span>
        <span class="nk-zuletzt">${f.anzahl}× · ${escape(vorZeit(f.zuletzt))}</span>
        <span class="nk-zahlen">${escape(f.namen.join(", "))}${f.geraete.length ? " · " + escape(f.geraete[0]) : ""}</span></summary>
      <div class="nk-detail">
        <h4>${escape(quelle)}</h4><div class="nk-zeile"><span>${escape(f.meldung)}</span></div>
        ${f.orte.length ? "<h4>Bereich</h4>" + f.orte.map((o) => `<div class="nk-zeile"><span>${escape(nutzungBereichName(o))}</span></div>`).join("") : ""}
        <h4>Geräte</h4>${f.geraete.map((g) => `<div class="nk-zeile"><span>${escape(g)}</span></div>`).join("") || "–"}
        <h4>App-Version</h4><div class="nk-zeile"><span>${escape(f.versionen.join(", ") || "–")}</span></div>
      </div></details>`;
  }
  return html;
}
// Ampelpunkt vor einem Spielzug (Klassen wie in der Spieleransicht: gruen | orange | rot).
export function nutzungPunkt(ampel) {
  return `<span class="an-punkt ${ampel ? escape(ampel) : "leer"}"></span>`;   // "leer" haelt die Spalte frei
}
// Eine Spielerin: wo sie war und wie lange, danach welche ihrer Spielzuege sie noch nicht
// komplett gesehen hat (mit ID). Die Videoliste selbst steht unter Team -> Videos.
function renderNutzungSpielerin(k, tage) {
  const pl = (n, ein, mehr) => `<b>${n}</b> ${n === 1 ? ein : mehr}`;
  const g0 = (k.geraete || [])[0];
  const gerat = g0 ? ` · ${escape([g0.os, g0.browser].filter(Boolean).join(" · "))}`
                     + (g0.app_version ? ` · <span${g0.app_version !== APP_VERSION ? ' class="alt"' : ""}>${escape(g0.app_version)}</span>` : "")
                   : "";
  const zahlen = k.zuletzt
    ? `${pl(k.tage, "Tag", "Tage")} · ${pl(k.besuche, "Besuch", "Besuche")} · <b>${escape(dauerText(k.sekunden_gesamt))}</b>${gerat}`
    : "noch nicht in der App";
  const offen = k.offen ? `<span class="nk-offen"><b>${k.offen}</b> ${k.offen === 1 ? "Spielzug" : "Spielzüge"} nicht gesehen</span>` : "";
  let detail = "";
  if (k.bereiche.length) {
    detail += '<h4>Wo sie war</h4>' + k.bereiche.map((b) =>
      `<div class="nk-zeile"><span>${escape(nutzungBereichName(b.ziel))}<small>${b.anzahl}× geöffnet</small></span>`
      + `<b class="nk-dauer">${escape(dauerText(b.sekunden))}</b></div>`).join("");
  }
  for (const gruppe of gruppiereNachSpiel(k.nicht_gesehen || [])) {
    detail += `<h4>Noch nicht gesehen · ${escape(gruppe.spiel)}</h4>` + gruppe.items.map((n) =>
      `<div class="nk-zeile"><span class="nk-titel">${nutzungPunkt(n.ampel)}<span><b class="su-id">${escape(n.id)}</b> `
      + `${escape(n.label)}<small>${escape(n.zeit || "")}${n.geoeffnet ? " · angetippt, nicht komplett" : ""}</small></span></span></div>`).join("");
  }
  if ((k.geraete || []).length) detail += "<h4>Geräte</h4>" + k.geraete.map(nutzungGeraetZeile).join("");
  if (!k.bereiche.length) {
    detail = '<p class="hinweis">In den letzten ' + tage + ' Tagen nichts aufgerufen.</p>' + detail;
  }
  return `<details class="nutz-karte${k.zuletzt ? "" : " nie"}">
    <summary><span class="nk-name">${escape(k.name)}</span>
      <span class="nk-zuletzt" title="${k.zuletzt ? escape(new Date(k.zuletzt).toLocaleString("de-DE")) : ""}">${escape(vorZeit(k.zuletzt))}</span>
      <span class="nk-zahlen">${zahlen}</span>${offen ? `<span class="nk-zahlen">${offen}</span>` : ""}</summary>
    <div class="nk-detail">${detail}</div></details>`;
}
function renderNutzung() {
  const d = nutzungDaten;
  const el = $("#nutzung-inhalt");
  const konten = [...d.konten].sort((a, b) =>
    (b.zuletzt || "").localeCompare(a.zuletzt || "") || a.name.localeCompare(b.name));
  const seit = d.seit ? new Date(d.seit).toLocaleDateString("de-DE") : "–";
  let html = `<p class="hinweis">Zähler der letzten ${d.tage} Tage, nur Spielerinnen. Erfasst seit ${seit}. `
           + `„Zuletzt aktiv“ zählt auch ältere Besuche. Die Dauer wird erst seit Version 0.59 gemessen `
           + `(nur bei geöffneter App, höchstens 30 Min. am Stück); davor steht „–“. „Nicht gesehen“ heißt: `
           + `nicht komplett angeschaut (mindestens 60 %), unabhängig vom Zeitraum. Die Spielzüge selbst stehen `
           + `unter Team → Videos.</p>`
           + '<h3 class="nutz-h">Spielerinnen</h3>'
           + konten.map((k) => renderNutzungSpielerin(k, d.tage)).join("")
           + renderNutzungFehler(d.fehler || [], d.tage);
  el.innerHTML = html;
}
