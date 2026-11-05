import { analyseBlockHtml, ladeAnalysen } from "./analysen.js";
import { api } from "../core/api.js";
import { TEAM_FARBEN } from "./einteilung.js";
import { ladeKader } from "./kader.js";
import { wappen } from "../core/portraits.js";
import { zeigeView } from "../core/router.js";
import { $, datumKurz, escape, toast } from "../core/ui.js";

// -------------------------------------------------------------- Rangliste ----
export async function ladeRangliste() {
  // Offline-first: erst den letzten bekannten Stand sofort zeigen, dann (online)
  // frisch nachladen. Siehe sync.js / local-db.js.
  const el = $("#rangliste-liste");
  const zeige = (liste) => {
    el.innerHTML = "";
    liste.forEach((p, i) => {
      const zeile = document.createElement("button");
      zeile.className = "rang-zeile";
      zeile.innerHTML = `
        <span class="platz">${i + 1}</span>
        ${wappen(p, 34)}
        <span class="name">${escape(p.name)}${p.position === "Tor" ? ' <span class="tor">TW</span>' : ""}</span>
        <span class="elo">${p.elo}</span>
        <span class="sp">${p.spiele_gesamt} Sp.</span>`;
      zeile.addEventListener("click", () => oeffneSpielerDetail(p));
      el.appendChild(zeile);
    });
  };
  const cached = await Sync.spiegelRoh("/api/rangliste");
  if (cached) zeige(cached);
  const frisch = await Sync.frischHolen("/api/rangliste");
  if (frisch) zeige(frisch);
}
// -------------------------------------------------- Spieler-/Spiel-Detail ----
let detailSpieler = null;      // {id, name, elo, position_angriff, ...}
let detailSpiele = [];         // geladene Spiele der gewaehlten Spielerin
let detailStats = null;        // Kennzahlen der gewaehlten Spielerin
let detailTraining = null;     // Trainings-Anwesenheit der gewaehlten Spielerin
let detailLC = null;           // Laufchallenge-Ergebnis der gewaehlten Spielerin
let detailAnalyse = [];        // Spielanalysen (Statistik + Zeitstempel) der gewaehlten Spielerin
let aktuellesSpiel = null;     // im Spiel-Detail geoeffnetes Spiel
// Wohin „zurück" aus dem Spieler-Detail führt (Rangliste oder Kader).
let detailZurueck = () => { ladeRangliste(); zeigeView("view-rangliste"); };
export async function oeffneSpielerDetail(p, herkunft) {
  try {
    // offline-faehig: einmal online geoeffnet -> danach aus dem GET-Cache
    const d = await Sync.apiOffline("/api/spieler/" + p.id + "/spiele");
    detailSpieler = d.spieler;
    detailSpiele = d.spiele;
    detailStats = d.stats;
    detailTraining = d.training || null;
    detailLC = d.laufchallenge || null;
    detailAnalyse = await ladeAnalysen(p.id);
    // Zurück-Ziel je nach Herkunft (Rangliste bzw. Kader).
    if (herkunft === "kader") {
      $("#btn-detail-zurueck").textContent = "← Kader";
      detailZurueck = () => { ladeKader(); zeigeView("view-kader"); };
    } else {
      $("#btn-detail-zurueck").textContent = "← Rangliste";
      detailZurueck = () => { ladeRangliste(); zeigeView("view-rangliste"); };
    }
    renderSpielerDetail();
    zeigeView("view-spieler-detail");
  } catch (e) {
    toast(navigator.onLine ? ("Fehler: " + e.message)
      : "Offline – diese Details wurden noch nicht geladen. Einmal online öffnen.");
  }
}
// ELO-Verlauf als kleine Inline-SVG-Sparkline (offline-/CSP-sicher, kein Lib).
// Rekonstruiert die ELO nach jedem Spiel aus aktueller ELO + Deltas (neueste
// zuerst), dann von alt nach neu gezeichnet.
function eloSparkline() {
  const deltas = detailSpiele.map((s) => s.delta);   // neueste zuerst
  if (deltas.length < 2) return "";
  let cur = detailSpieler.elo;
  const nach = [cur];                                // elo nach neuestem Spiel
  for (const d of deltas) { cur = cur - d; nach.push(cur); }
  const werte = nach.reverse();                      // alt -> neu (inkl. Startwert)
  const w = 280, h = 56, pad = 5;
  const min = Math.min(...werte), max = Math.max(...werte), span = (max - min) || 1;
  const px = (i) => pad + i * (w - 2 * pad) / (werte.length - 1);
  const py = (v) => pad + (h - 2 * pad) * (1 - (v - min) / span);
  const pts = werte.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");
  const farbe = werte[werte.length - 1] >= werte[0] ? "var(--gruen)" : "var(--b)";
  return `<svg class="elo-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="ELO-Verlauf">` +
    `<polyline fill="none" stroke="${farbe}" stroke-width="2" points="${pts}"/>` +
    `<circle cx="${px(werte.length - 1).toFixed(1)}" cy="${py(werte[werte.length - 1]).toFixed(1)}" r="3.5" fill="${farbe}"/>` +
    `</svg>`;
}
// Bausteine des Profils. Sie werden an ZWEI Stellen gebraucht: im Spieler-
// Detail (Trainerblick auf eine Spielerin) und auf der eigenen Seite "Ich" -
// darum liefern sie HTML zurueck, statt selbst irgendwo hineinzuschreiben.
export function positionsBadges(sp) {
  const badges = [];
  if (sp.position === "Tor") badges.push("Torhüterin");
  if (sp.position_angriff) badges.push("Angriff: " + escape(sp.position_angriff));
  if (sp.position_abwehr) badges.push("Abwehr: " + escape(sp.position_abwehr));
  return badges.length
    ? `<div class="profil-badges">${badges.map((b) => `<span class="pb">${b}</span>`).join("")}</div>` : "";
}
function trainingBlockHtml(tr) {
  if (!tr || !tr.erfasst) return "";
  const q = tr.quote != null ? tr.quote + "%" : "–";
  return `<div class="profil-training">
      <span class="pt-wert">${tr.anwesend}<small>/${tr.anwesend + tr.abgesagt}</small></span>
      <span class="pt-label">Trainings da (${q})</span></div>`;
}
function laufBlockHtml(lc) {
  if (!lc) return "";
  const platz = lc.rang ? `Platz ${lc.rang}${lc.teilnehmer ? " / " + lc.teilnehmer : ""}` : "";
  const andere = lc.andere ? ` · ${lc.andere} andere` : "";
  return `<div class="profil-lauf">
      <div class="pl-kopf">🏃 ${escape(lc.challenge || "Laufchallenge")}</div>
      <div class="pl-zahlen">
        <span class="pl-km">${lc.km}<small>km</small></span>
        <span class="pl-meta">${lc.laeufe} Läufe${andere}</span>
        ${platz ? `<span class="pl-rang">${platz}</span>` : ""}
      </div></div>`;
}
// Profilkopf: Position, Trainings-Anwesenheit, ELO-Sparkline.
function renderProfil() {
  const el = $("#detail-profil");
  if (!el) return;
  const sp = detailSpieler;
  const badgeHtml = positionsBadges(sp);
  // Kopfzeile: Portrait im Wappen, daneben die Positions-Badges.
  const kopfHtml = `<div class="profil-kopf">${wappen(sp, 88)}` +
                   `<div class="pk-text">${badgeHtml || '<span class="pk-leer">Keine Position hinterlegt</span>'}</div></div>`;
  const training = trainingBlockHtml(detailTraining);
  const lauf = laufBlockHtml(detailLC);
  const spark = eloSparkline();
  const sparkBlock = spark
    ? `<div class="profil-elo"><div class="pe-kopf">ELO-Verlauf</div>${spark}</div>` : "";
  el.innerHTML = kopfHtml + training + lauf + analyseBlockHtml(detailAnalyse, sp.id) + sparkBlock;
}
function renderStats() {
  const el = $("#detail-stats");
  const s = detailStats;
  if (!s || (s.siege + s.unent + s.niederlagen) === 0) { el.innerHTML = ""; return; }
  const serieText = s.serie_typ
    ? (s.serie_anzahl + "× " + ({ S: "Sieg", N: "Niederlage", U: "Unent." }[s.serie_typ])
        + (s.serie_anzahl > 1 && s.serie_typ !== "U" ? "e" : ""))
    : "–";
  const kacheln = [
    ["Bilanz", `${s.siege}·${s.unent}·${s.niederlagen}`, "S·U·N"],
    ["Serie", serieText, ""],
    ["Bester", (s.bester > 0 ? "+" : "") + s.bester, "ein Spiel"],
    ["Höchststand", s.peak, "ELO"],
  ];
  el.innerHTML = kacheln.map(([t, w, u]) =>
    `<div class="stat"><span class="s-wert">${w}</span>` +
    `<span class="s-titel">${t}</span>${u ? `<span class="s-unter">${u}</span>` : ""}</div>`
  ).join("");
}
function renderSpielerDetail() {
  $("#detail-name").textContent = `${detailSpieler.name} · ELO ${detailSpieler.elo}`;
  renderProfil();
  renderStats();
  const el = $("#detail-spiele");
  el.innerHTML = "";
  if (!detailSpiele.length) {
    el.innerHTML = '<p class="hinweis">Noch keine Spiele gespielt.</p>';
    return;
  }
  detailSpiele.forEach((s, idx) => {
    const zeile = document.createElement("button");
    zeile.className = "detail-zeile";
    const kl = s.delta > 0 ? "plus" : (s.delta < 0 ? "minus" : "null");
    const vz = s.delta > 0 ? "+" : "";
    const erg = s.ergebnis === "U" ? "Unentschieden"
      : (s.ergebnis === s.mein_team ? "Sieg" : "Niederlage");
    zeile.innerHTML = `
      <span class="d-datum">${datumKurz(s.datum)}</span>
      <span class="d-erg">${erg}</span>
      <span class="d-delta ${kl}">${vz}${s.delta}</span>`;
    zeile.addEventListener("click", () => oeffneSpielDetail(idx));
    el.appendChild(zeile);
  });
}
function oeffneSpielDetail(idx) {
  const s = detailSpiele[idx];
  aktuellesSpiel = s;
  const unent = s.ergebnis === "U";
  // Aeltere Spiele kennen nur team_a/team_b, neuere die ganze Liste.
  const gruppen = s.teams && s.teams.length ? s.teams : [s.team_a, s.team_b];
  $("#spiel-titel").textContent = datumKurz(s.datum) + " · " +
    (unent ? "Unentschieden" : "Sieg Team " + s.ergebnis) +
    (gruppen.length > 2 ? ` · ${gruppen.length} Teams` : "");

  const wrap = $("#spiel-teams");
  wrap.innerHTML = "";
  gruppen.forEach((team, i) => {
    const k = TEAM_FARBEN[i].k;
    const block = document.createElement("div");
    block.id = "spiel-team-" + k;
    wrap.appendChild(block);
    renderTeamBlock("#spiel-team-" + k, "Team " + k, team,
      unent ? "unent" : (s.ergebnis === k ? "sieger" : "verlierer"));
  });

  // Korrektur-Knoepfe passend zur Teamzahl dieses Spiels
  const kk = $("#korrektur-knoepfe");
  kk.innerHTML = "";
  gruppen.forEach((_, i) => {
    const k = TEAM_FARBEN[i].k;
    const b = document.createElement("button");
    b.textContent = "Team " + k;
    b.classList.toggle("aktiv", s.ergebnis === k);
    b.addEventListener("click", () => spielKorrigieren(k));
    kk.appendChild(b);
  });
  const u = document.createElement("button");
  u.textContent = "Unent.";
  u.classList.toggle("aktiv", s.ergebnis === "U");
  u.addEventListener("click", () => spielKorrigieren("U"));
  kk.appendChild(u);

  zeigeView("view-spiel-detail");
}
async function spielKorrigieren(ergebnis) {
  if (!aktuellesSpiel) return;
  if (ergebnis === aktuellesSpiel.ergebnis) { toast("Ergebnis ist schon so eingetragen."); return; }
  try {
    await api("/api/spiel/" + aktuellesSpiel.spiel_id + "/aendern", "POST", { ergebnis });
    toast("Ergebnis geändert — ELOs neu berechnet.");
    await detailNeuLaden(aktuellesSpiel.spiel_id);
  } catch (e) { toast("Fehler: " + e.message); }
}
async function spielLoeschen() {
  if (!aktuellesSpiel) return;
  if (!confirm("Dieses Spiel wirklich löschen? Die ELOs werden neu berechnet.")) return;
  try {
    await api("/api/spiel/" + aktuellesSpiel.spiel_id + "/loeschen", "POST");
    toast("Spiel gelöscht — ELOs neu berechnet.");
    await detailNeuLaden(null);   // zurueck zur Spieler-Uebersicht
  } catch (e) { toast("Fehler: " + e.message); }
}
// Spieler-Detail nach einer Aenderung neu laden; wenn das Spiel noch existiert,
// erneut oeffnen, sonst zurueck zur Uebersicht.
async function detailNeuLaden(spielId) {
  const d = await api("/api/spieler/" + detailSpieler.id + "/spiele");
  detailSpieler = d.spieler;
  detailSpiele = d.spiele;
  detailStats = d.stats;
  detailTraining = d.training || null;
  detailLC = d.laufchallenge || null;
  detailAnalyse = await ladeAnalysen(detailSpieler.id);
  renderSpielerDetail();
  const idx = spielId == null ? -1 : detailSpiele.findIndex((s) => s.spiel_id === spielId);
  if (idx >= 0) oeffneSpielDetail(idx);
  else zeigeView("view-spieler-detail");
}
$("#btn-spiel-loeschen").addEventListener("click", spielLoeschen);
function renderTeamBlock(sel, titel, spieler, klasse) {
  const el = $(sel);
  el.className = "spiel-team " + klasse;
  const label = klasse === "sieger" ? "Sieger"
    : (klasse === "verlierer" ? "Verlierer" : "Unentschieden");
  const items = spieler.map((p) => {
    const hervor = p.id === detailSpieler.id ? " hervor" : "";
    const tw = p.position === "Tor" ? ' <span class="tw">TW</span>' : "";
    return `<li class="${hervor.trim()}">${escape(p.name)}${tw}</li>`;
  }).join("");
  el.innerHTML = `<div class="team-kopf">${titel} · ${label}</div><ul>${items}</ul>`;
}
$("#btn-detail-zurueck").addEventListener("click", () => detailZurueck());
$("#btn-spiel-zurueck").addEventListener("click", () => zeigeView("view-spieler-detail"));
