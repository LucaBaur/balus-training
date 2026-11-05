import { api } from "../core/api.js";
import { videosOber } from "./home.js";
import { eigeneSpielerId } from "../core/konto.js";
import { gehe, mitScrollRueckkehr, zeigeView } from "../core/router.js";
import { nutzungMelden } from "../core/tracking.js";
import { $, datumKurz, escape } from "../core/ui.js";
import { ladeKommentare, wiedergabeBeobachten } from "./videos.js";

// ========================================================= Spielanalysen ==
//  Ganzes Spielvideo + Zeitstempel (Tore, Wuerfe, Fehler, Spielzuege mit Ampel),
//  erfasst am PC in "Balu-Spielanalyse". Hier nur Anzeige: Statistik und die
//  Szenen der Spielerin; ein Tipp springt im Spielvideo zur Stelle. Spielerinnen
//  sehen nur Eigenes (der Server filtert) und keine Trainer-Kommentare.
const ANALYSE_EVENT = {
  tor: "Tor", fehlwurf: "Fehlwurf", ballverlust: "Ballverlust",
  strafe: "Zeitstrafe", siebenmeter: "7-Meter", parade: "Parade",
};
const ANALYSE_AMPEL = { gruen: "Tor", orange: "Okay", rot: "Fehler" };
export async function ladeAnalysen(sid) {
  try { return await Sync.apiOffline("/api/spieler/" + sid + "/analyse"); }
  catch (_) { return []; }
}
function analyseZeit(t) {
  t = Math.max(0, Math.floor(t));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0");
}
// Ein Spiel: Kacheln, Spielzug-Ampel und die Szenenliste. `ohneTitel` fuer die
// Detailansicht, die den Gegner schon als Ueberschrift hat.
function analyseSpielHtml(a, sid, ohneTitel) {
  const st = a.stats;
  const kacheln = [
    [st.tore, "Tore"], [st.fehlwuerfe, "Fehlwürfe"], [st.ballverluste, "Ballverluste"],
    [st.paraden, "Paraden"], [st.vorlagen, "Vorlagen"], [st.strafen, "Strafen/7m"],
  ].filter(([n]) => n > 0)
   .map(([n, l]) => `<span class="an-kachel"><b>${n}</b>${l}</span>`).join("");
  const ampel = st.zuege
    ? `<div class="an-ampel">${st.zuege} Spielzüge:
        <span class="an-p gruen">${st.gruen}</span><span class="an-p orange">${st.orange}</span><span class="an-p rot">${st.rot}</span></div>`
    : "";
  const szenen = [
    ...a.events.map((e) => ({
      t: e.t, farbe: e.typ === "tor" ? "gruen" : e.typ === "fehlwurf" ? "orange" : e.typ === "ballverlust" ? "rot" : "grau",
      text: ANALYSE_EVENT[e.typ] + (e.detail ? " · " + e.detail : "") + (e.assist_id && e.spieler_id !== sid ? " (Vorlage)" : ""),
      clip: e.clip_id,
    })),
    ...a.zuege.map((z) => ({
      t: z.t_start, bis: z.t_ende, farbe: z.ampel, text: "Spielzug " + z.name + " – " + ANALYSE_AMPEL[z.ampel],
      kommentar: z.kommentar, clip: z.clip_id,
    })),
  ].sort((x, y) => x.t - y.t);
  const spielbar = a.video_da || szenen.some((x) => x.clip);
  const zeilen = !spielbar
    ? '<p class="hinweis">Das Video ist noch nicht hochgeladen.</p>'
    : !szenen.length
      ? '<p class="hinweis">Für dich wurden in diesem Spiel keine Szenen erfasst.</p>'
      : szenen.map((x) => `<button class="an-szene" data-analyse="${a.id}" data-t="${x.t}" data-titel="${escape("TVG – " + a.gegner)}" data-text="${escape(x.text)}" data-farbe="${escape(x.farbe)}"
          data-kommentar="${escape(x.kommentar || "")}" data-bis="${x.bis != null ? x.bis : ""}"
          data-clip="${x.clip || ""}" data-voll="${a.video_da ? 1 : ""}">
          <span class="an-punkt ${x.farbe}"></span>
          <span class="an-text">${escape(x.text)}${x.kommentar ? `<small>${escape(x.kommentar)}</small>` : ""}</span>
          <span class="an-zeit">${analyseZeit(x.t)}</span></button>`).join("");
  const titel = ohneTitel ? ""
    : `<div class="an-titel">TVG – ${escape(a.gegner)}${a.datum ? `<small>${escape(datumKurz(a.datum))}</small>` : ""}</div>`;
  return `<div class="an-spiel">${titel}<div class="an-kacheln">${kacheln}</div>${ampel}<div class="an-szenen">${zeilen}</div></div>`;
}
// Mehrere Spiele untereinander - so sieht der Trainer sie im Spielerdetail.
export function analyseBlockHtml(liste, sid, alsKarte) {
  if (!liste || !liste.length) return "";
  const spiele = liste.map((a) => analyseSpielHtml(a, sid)).join("");
  const kopf = '<div class="ik-kopf">🎬 Spielanalyse</div>';
  return alsKarte
    ? `<section class="ich-karte">${kopf}${spiele}</section>`
    : `<div class="profil-analyse">${kopf}${spiele}</div>`;
}
// "Mein Profil": nur die Zahlen - je Spiel eine Zeile, darunter die Summe. Die Szenen
// und Videos stehen unter Ich -> Videos; ein Tipp auf ein Spiel fuehrt dorthin.
const STAT_FELDER = [["tore", "Tore"], ["fehlwuerfe", "Fehlwürfe"], ["ballverluste", "Ballverluste"],
                     ["paraden", "Paraden"], ["vorlagen", "Vorlagen"], ["strafen", "Strafen/7m"]];
function statKacheln(st) {
  return STAT_FELDER.filter(([k]) => st[k] > 0)
    .map(([k, l]) => `<span class="an-kachel"><b>${st[k]}</b>${l}</span>`).join("")
    || '<span class="hinweis">keine Aktionen erfasst</span>';
}
export function statistikBlockHtml(liste) {
  const kopf = '<div class="ik-kopf">🎬 Meine Spielstatistik</div>';
  if (!liste || !liste.length) {
    return `<section class="ich-karte">${kopf}<p class="hinweis">Für dich wurden noch keine Spielaktionen erfasst.</p></section>`;
  }
  const summe = { zuege: 0, gruen: 0, orange: 0, rot: 0 };
  for (const [k] of STAT_FELDER) summe[k] = 0;
  const zeilen = liste.map((a) => {
    for (const k of Object.keys(summe)) summe[k] += a.stats[k] || 0;
    const ampel = a.stats.zuege
      ? `<div class="an-ampel">${a.stats.zuege} Spielzüge:
          <span class="an-p gruen">${a.stats.gruen}</span><span class="an-p orange">${a.stats.orange}</span><span class="an-p rot">${a.stats.rot}</span></div>`
      : "";
    return `<button class="stat-zeile" data-spiel="${a.id}">
      <span class="sz-titel">TVG – ${escape(a.gegner)}${a.datum ? `<small>${escape(datumKurz(a.datum))}</small>` : ""}</span>
      <div class="an-kacheln">${statKacheln(a.stats)}</div>${ampel}</button>`;
  }).join("");
  const ampelSumme = summe.zuege
    ? `<div class="an-ampel">${summe.zuege} Spielzüge:
        <span class="an-p gruen">${summe.gruen}</span><span class="an-p orange">${summe.orange}</span><span class="an-p rot">${summe.rot}</span></div>`
    : "";
  const spiele = liste.length === 1 ? "1 Spiel" : liste.length + " Spiele";
  return `<section class="ich-karte" id="ich-statistik">${kopf}${zeilen}
    <div class="stat-summe"><span class="sz-titel">Insgesamt<small>${spiele}</small></span>
      <div class="an-kacheln">${statKacheln(summe)}</div>${ampelSumme}</div></section>`;
}
// ---- Videoanalyse eines Spiels (Ich -> Videos -> Spiel) ----------------------
//  Dieselbe Szenenliste wie frueher im Profil; ein Tipp auf eine Szene oeffnet den
//  Clip, "Ganzes Spiel ansehen" das komplette Spielvideo. Wer im Spiel nicht
//  vorkommt, sieht statt der Szenen einen Hinweis, kann aber das ganze Spiel ansehen.
let aktAnalyse = null;
export async function oeffneAnalyseDetail(aid) {
  const el = $("#analyse-detail-inhalt");
  el.innerHTML = '<p class="hinweis">Lädt…</p>';
  zeigeView("view-analyse-detail");
  let a;
  try { a = await api("/api/analysen/" + aid); }           // direkt vom Server: soll nie einen fremden Cache-Stand zeigen
  catch (_) {
    el.innerHTML = '<p class="hinweis">Die Videoanalyse konnte nicht geladen werden – dafür brauchst du eine Verbindung.</p>';
    return;
  }
  aktAnalyse = a;
  nutzungMelden("video", "analyse:" + a.id, a.gegner);
  const meta = [a.datum ? datumKurz(a.datum) : "", a.art].filter(Boolean).join(" · ");
  el.innerHTML = `<h2>Videoanalyse gegen ${escape(a.gegner)}</h2>
    ${meta ? `<div class="vd-meta">${escape(meta)}</div>` : ""}
    ${a.video_da ? '<button id="analyse-ganzes" class="primaer gross">▶ Ganzes Spiel ansehen</button>' : ""}
    <h3 class="videos-h">Deine Szenen</h3>
    ${analyseSpielHtml(a, eigeneSpielerId(), true)}`;
  const ganzes = $("#analyse-ganzes");
  if (ganzes) ganzes.addEventListener("click", () => oeffneAnalyseVideo(a.id, 0, "TVG – " + a.gegner, null));
}
$("#btn-analyse-zurueck").addEventListener("click", () => mitScrollRueckkehr(() => gehe(videosOber(), "videos")));
export let analyseZurueckView = null;
export function setzeAnalyseZurueckView(wert) { analyseZurueckView = wert; return wert; }
export function zeigeSzenenNotiz(info) {
  const box = $("#vd-notiz");
  box.className = "vd-notiz" + (info && info.farbe ? " " + info.farbe : "");
  box.replaceChildren();
  if (!info) return;
  const titel = document.createElement("div");
  titel.className = "vn-titel";
  titel.textContent = info.text;
  box.appendChild(titel);
  if (info.zeit) {
    const meta = document.createElement("div");
    meta.className = "vn-meta";
    meta.textContent = info.zeit;
    box.appendChild(meta);
  }
  if (info.kommentar) {
    const label = document.createElement("span");
    label.className = "vn-label";
    label.textContent = "Kommentar vom Trainer";
    const text = document.createElement("p");
    text.className = "vn-kommentar";
    text.textContent = info.kommentar;           // textContent: Freitext wird nie als HTML gelesen
    box.append(label, text);
  }
  if (info.voll) {                                   // aus dem Clip ins ganze Spiel wechseln
    const knopf = document.createElement("button");
    knopf.className = "plan-edit-btn vn-voll";
    knopf.textContent = "Im ganzen Spiel ab hier";
    knopf.addEventListener("click", info.voll);
    box.appendChild(knopf);
  }
}
// Von wo kam man ins Video? (Beim Wechsel Clip -> ganzes Spiel bleibt das urspruengliche Ziel.)
function merkeZurueckView() {
  const aktiv = document.querySelector(".view:not(.hidden)");
  if (aktiv && aktiv.id !== "view-video-detail") analyseZurueckView = aktiv.id;
}
export function oeffneSzenenClip(cid, titel, info) {
  nutzungMelden("video", "szene:" + cid, titel);
  wiedergabeBeobachten("szene:" + cid, titel);
  ladeKommentare("szene:" + cid);
  merkeZurueckView();
  $("#vd-titel").textContent = titel;
  $("#vd-meta").textContent = "Szene";
  $("#vd-aktionen").innerHTML = "";
  zeigeSzenenNotiz(info);
  $("#btn-video-zurueck").textContent = "← Zurück";
  const player = $("#vd-player");
  player.addEventListener("loadedmetadata", () => { player.play().catch(() => {}); }, { once: true });
  player.src = "/api/szenen/" + cid + "/video";
  player.load();
  zeigeView("view-video-detail");
}
export function oeffneAnalyseVideo(aid, t, titel, info) {
  nutzungMelden("video", "spiel:" + aid, titel);
  wiedergabeBeobachten(null);                      // ganzes Spiel: kein 60-%-Massstab
  ladeKommentare("spiel:" + aid);
  merkeZurueckView();
  $("#vd-titel").textContent = titel;
  $("#vd-meta").textContent = "ab " + analyseZeit(t);
  $("#vd-aktionen").innerHTML = "";
  zeigeSzenenNotiz(info);
  $("#btn-video-zurueck").textContent = "← Zurück";
  const player = $("#vd-player");
  const start = Math.max(0, t - 3);                // etwas Anlauf vor der Szene
  player.addEventListener("loadedmetadata", () => { player.currentTime = start; player.play().catch(() => {}); },
    { once: true });
  player.src = "/api/analysen/" + aid + "/video";
  player.load();
  zeigeView("view-video-detail");
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-analyse]");
  if (!b) return;
  const bis = b.dataset.bis !== "" ? +b.dataset.bis : null;
  const aid = +b.dataset.analyse, t = +b.dataset.t, titel = b.dataset.titel;
  const info = {
    text: b.dataset.text, farbe: b.dataset.farbe, kommentar: b.dataset.kommentar,
    zeit: bis != null ? analyseZeit(t) + " – " + analyseZeit(bis) : "bei " + analyseZeit(t),
  };
  if (b.dataset.clip) {                       // kurzer Clip: laedt in Sekunden, auch ueber Funnel/Handy
    if (b.dataset.voll) info.voll = () => oeffneAnalyseVideo(aid, t, titel, { ...info, voll: null });
    oeffneSzenenClip(+b.dataset.clip, titel, info);
  } else {
    oeffneAnalyseVideo(aid, t, titel, info);  // kein Clip vorhanden: ganzes Spiel an der Stelle
  }
});
