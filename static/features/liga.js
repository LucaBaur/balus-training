import { gehe } from "../core/router.js";
import { $, datumTeile, escape } from "../core/ui.js";

// =================================================================== Liga ====
//  Tabelle und Spielplan der Frauen (Bezirksoberliga) aus handball4all, dem Dienst
//  hinter bwhv.org. Der Server holt und puffert sie (liga.py); hier nur Anzeige.
//  Erreichbar unter Home -> Liga; die Startseite zeigt daraus die naechsten Spiele,
//  solange keine eigenen Test-/Ligaspiele eingetragen sind.
let ligaDaten = null;
const LIGA_QUELLE = "https://www.bwhv.org/spielbetrieb/ergebnisse/tabellen#/league?ogId=216&lId=166266&tId=1495111";
export async function ligaHolen() {
  try { const frisch = await Sync.frischHolen("/api/liga"); if (frisch) ligaDaten = frisch; } catch (_) {}
  if (!ligaDaten) { try { ligaDaten = await Sync.spiegelRoh("/api/liga"); } catch (_) {} }
  return ligaDaten;
}
export async function ligaNaechste(n) {
  const d = await ligaHolen();
  const heute = new Date().toISOString().slice(0, 10);
  return d ? d.spiele.filter((x) => x.status !== "gespielt" && (x.datum || "") >= heute).slice(0, n) : [];
}
const ligaOrt = (sp) => [sp.halle, sp.ort].filter(Boolean).join(", ");
export function ligaHomeKarte(sp) {
  const t = datumTeile(sp.datum);
  const karte = document.createElement("button");
  karte.className = "hs-spiel ligaspiel" + (sp.eigen_heim ? "" : " auswaerts");
  karte.innerHTML =
    `<span class="hs-datum"><b>${t.wt}</b><span>${escape(t.tag)}</span></span>
     <span class="hs-mitte">
       <span class="hs-titel">${escape(sp.heim)} – ${escape(sp.gast)}</span>
       <span class="hs-meta">Ligaspiel · ${sp.eigen_heim ? "daheim" : "auswärts"}${ligaOrt(sp) ? " · " + escape(ligaOrt(sp)) : ""}</span>
     </span>
     <span class="hs-zeit"><b>${escape(sp.zeit)}</b><small>Anwurf</small></span>`;
  karte.addEventListener("click", () => gehe("home", "liga"));
  return karte;
}
export async function ladeLiga() {
  const el = $("#liga-inhalt");
  if (!ligaDaten) {                                  // sofort etwas zeigen: letzter Stand aus dem Speicher
    try { ligaDaten = await Sync.spiegelRoh("/api/liga"); } catch (_) {}
  }
  if (ligaDaten) renderLiga(); else el.innerHTML = '<p class="hinweis">Lädt…</p>';
  const frisch = await Sync.frischHolen("/api/liga");
  if (frisch) { ligaDaten = frisch; renderLiga(); }
  else if (!ligaDaten) {
    el.innerHTML = '<p class="hinweis">Die Tabelle konnte nicht geladen werden – bitte später noch einmal versuchen.</p>';
  }
}
function ligaSpielHtml(sp) {
  const datum = sp.datum
    ? new Date(sp.datum + "T12:00:00").toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" })
    : "";
  const eigen = (name) => /^TV Gerhausen/.test(name) ? ' class="eigen"' : "";
  const ergebnis = sp.status === "offen"
    ? "–:–" : `${sp.tore_heim} : ${sp.tore_gast}`;
  const meta = [ligaOrt(sp), sp.halbzeit ? "Halbzeit " + sp.halbzeit : "", sp.bemerkung].filter(Boolean).join(" · ");
  const route = sp.status !== "gespielt" && !sp.eigen_heim && sp.strasse
    ? ` · <a href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${sp.strasse}, ${sp.plz || ""} ${sp.ort || ""}`)}" target="_blank" rel="noopener">Route</a>`
    : "";
  const live = sp.status === "live" ? '<span class="ls-live">LIVE</span>' : "";
  return `<div class="liga-spiel ${sp.status === "gespielt" ? sp.ergebnis || "" : ""}">
    <div class="ls-kopf"><span>${escape(datum)} · ${escape(sp.zeit)}</span>${live}
      <span class="ls-ort">${sp.eigen_heim ? "daheim" : "auswärts"}</span></div>
    <div class="ls-teams"><span${eigen(sp.heim)}>${escape(sp.heim)}</span>
      <b class="ls-erg">${ergebnis}</b><span${eigen(sp.gast)}>${escape(sp.gast)}</span></div>
    ${meta || route ? `<div class="ls-meta">${escape(meta)}${route}</div>` : ""}</div>`;
}
function renderLiga() {
  const d = ligaDaten;
  const el = $("#liga-inhalt");
  // "Frauen Bezirksoberliga - Hallenrunde 2026/2027": den Ligennamen aus der Rundenzeile nehmen, er steht schon in der Ueberschrift
  const runde = (d.runde || "").replace(d.liga || "", "").replace(/^[\s\-–]+/, "");
  const kopf = [d.region, runde].filter(Boolean).join(" · ");
  let html = `<h2>${escape(d.liga || "Liga")}</h2>${kopf ? `<p class="hinweis">${escape(kopf)}</p>` : ""}`;

  html += '<h3 class="videos-h">Tabelle</h3><div class="liga-scroll"><table class="liga-tab"><thead><tr>'
        + '<th>#</th><th>Mannschaft</th><th>Sp</th><th>S</th><th>U</th><th>N</th><th>Tore</th><th>Pkt</th></tr></thead><tbody>'
        + d.tabelle.map((r) => `<tr class="${r.eigen ? "eigen" : ""}"><td>${r.platz != null ? r.platz : ""}</td>`
          + `<td>${escape(r.team)}</td><td>${r.spiele}</td><td>${r.s}</td><td>${r.u}</td><td>${r.n}</td>`
          + `<td>${r.tore_plus}:${r.tore_minus}</td><td><b>${r.punkte_plus}:${r.punkte_minus}</b></td></tr>`).join("")
        + "</tbody></table></div>";
  const fuss = [d.stand ? "Stand: " + d.stand : "", ...(d.hinweise || [])].filter(Boolean).map(escape).join(" · ");
  html += `<p class="ls-fuss">${fuss}${d.veraltet ? " · <b>Verbandsseite gerade nicht erreichbar, es gilt der letzte bekannte Stand.</b>" : ""}</p>`;

  const heute = new Date().toISOString().slice(0, 10);
  const offen = d.spiele.filter((x) => x.status !== "gespielt");
  const gespielt = d.spiele.filter((x) => x.status === "gespielt").reverse();
  const naechste = offen.filter((x) => (x.datum || "") >= heute);
  html += '<h3 class="videos-h">Nächste Spiele</h3>';
  html += naechste.length ? naechste.slice(0, 4).map(ligaSpielHtml).join("") : '<p class="hinweis">Keine offenen Spiele mehr.</p>';
  if (naechste.length > 4) {
    html += `<details class="liga-mehr"><summary>Alle weiteren Spiele (${naechste.length - 4})</summary>`
          + naechste.slice(4).map(ligaSpielHtml).join("") + "</details>";
  }
  if (gespielt.length) html += '<h3 class="videos-h">Ergebnisse</h3>' + gespielt.map(ligaSpielHtml).join("");
  html += `<p class="ls-fuss">Quelle: <a href="${LIGA_QUELLE}" target="_blank" rel="noopener">Baden-Württembergischer Handball-Verband</a> (handball4all)</p>`;
  el.innerHTML = html;
}
