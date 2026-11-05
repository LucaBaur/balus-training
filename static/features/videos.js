import { merkeGeladen, vorZeit } from "../core/aktualisieren.js";
import { analyseZurueckView, oeffneAnalyseDetail, oeffneSzenenClip, setzeAnalyseZurueckView, zeigeSzenenNotiz } from "./analysen.js";
import { api } from "../core/api.js";
import { aktRolle } from "../core/konto.js";
import { _nameKey, filtereSzenen, gruppiereNachName, namenMitZahl, nutzungPunkt, szenenStatus } from "./nutzung.js";
import { aktOber, gehe, mitScrollRueckkehr, scrollNachRenderAnwenden, zeigeView } from "../core/router.js";
import { nutzungMelden } from "../core/tracking.js";
import { $, datumKurz, escape, toast } from "../core/ui.js";

// ============================================================ Szenen-Videos ==
//  Einzelne Spielszenen, geschnitten und beschriftet am PC (Projekt
//  "Balu-Videoschnitt"). Eine Spielerin sieht nur die ihr zugeordneten Clips;
//  die Trainerin sieht alle, kann sie umhaengen und loeschen. Der Upload
//  passiert im Schnittwerkzeug, nicht hier. Online-only (Streaming braucht Netz).
let videoClips = null;
let videoSpiele = null;     // nur Spielerinnen: alle Spielanalysen (Ich -> Videos)
let videoKader = null;      // nur Trainerin: Kader fuer die Zuordnung
let aktVideo = null;
export async function ladeVideos() {
  const el = $("#videos-liste");
  if (!videoClips) el.innerHTML = '<p class="hinweis">Lädt…</p>';
  try {
    videoClips = await api("/api/clips");
    if (aktRolle !== "trainer") {
      try { videoSpiele = await api("/api/analysen"); } catch (_) { if (!videoSpiele) videoSpiele = []; }
    }
    if (aktRolle === "trainer" && !videoKader) {
      try { videoKader = await api("/api/spieler"); } catch (_) { videoKader = []; }
    }
    if (aktRolle === "trainer") {                      // alle Spielzuege je Spiel; ohne Netz bleibt der letzte Stand
      try { szenenDaten = await api("/api/szenen-uebersicht"); } catch (_) { /* alter Stand oder leer */ }
    }
    $("#aktual-leiste-videos").classList.toggle("hidden", aktRolle !== "trainer");   // ↻ nur fuer den Trainer
    merkeGeladen("videos");
    renderVideos();
    scrollNachRenderAnwenden();
  } catch (_) {
    if (!videoClips) {
      el.innerHTML = '<p class="hinweis">Videos konnten nicht geladen werden – ' +
        'dafür brauchst du eine Verbindung.</p>';
    }
  }
}
// ---- Trainer: alle Spielzuege je Spiel (statt nur der manuell hochgeladenen Clips) ----
let szenenDaten = null;     // Antwort von /api/szenen-uebersicht
const szenenFilter = { sortierung: "zeit", name: null, nurOffen: false, mitEreignissen: false };
// Haken je Zustand: komplett angeschaut / nur angetippt / nie geoeffnet
const SZENEN_SYMBOL = { komplett: "✓", angetippt: "◐", offen: "○" };
function szenenZeile(s, mitSpiel) {
  const namen = { komplett: [], angetippt: [], offen: [] };
  for (const n of s.beteiligt) namen[szenenStatus(s, n)]?.push(n);
  const wer = s.kein_video
    ? "kein Video – Ansicht nicht messbar"
    : ["komplett", "angetippt", "offen"].filter((z) => namen[z].length)
        .map((z) => `<span class="${z === "komplett" ? "" : "nk-offen"}">${SZENEN_SYMBOL[z]} ${escape(namen[z].join(", "))}</span>`).join(" · ")
      || "keine Beteiligte mit Konto";
  const zahl = s.kein_video ? "–" : `${namen.komplett.length} von ${s.beteiligt.length}`;
  const kopf = `${nutzungPunkt(s.ampel)}<span><b class="su-id">${escape(s.id)}</b> ${escape(s.label)}`
    + `<small>${escape([mitSpiel ? s.spiel : "", s.zeit, s.kommentare ? "💬 " + s.kommentare : ""].filter(Boolean).join(" · "))}</small>`
    + `<small class="su-wer">${wer}</small></span>`;
  const titel = s.clip_id
    ? `<button type="button" class="su-titel" data-clip="${s.clip_id}" data-sid="${escape(s.id)}">${kopf}</button>`
    : `<span class="su-titel">${kopf}</span>`;
  return `<div class="nk-zeile su-zeile">${titel}<b class="nk-dauer">${zahl}</b></div>`;
}
function renderSzenenUebersicht() {
  if (!szenenDaten) return '<p class="hinweis">Spielzüge werden geladen …</p>';
  const spiele = szenenDaten.spiele || [];
  if (!spiele.length) {
    return '<p class="hinweis">Noch keine Spielanalyse. Spielzüge kommen aus „Balu-Spielanalyse“ ' +
      'und werden am PC mit „Balu-Videoschnitt“ geschnitten.</p>';
  }
  const f = szenenFilter;
  const optionen = { name: f.name, nurOffen: f.nurOffen, mitEreignissen: f.mitEreignissen };
  const alle = spiele.flatMap((g) => g.szenen);
  const chips = namenMitZahl(filtereSzenen(alle, { mitEreignissen: f.mitEreignissen }));
  const knopf = (aktiv, attr, text) => `<button type="button" class="su-knopf${aktiv ? " aktiv" : ""}" ${attr}>${escape(text)}</button>`;
  let html = '<div class="su-leiste">'
    + knopf(f.sortierung === "zeit", 'data-sort="zeit"', "Zeitverlauf")
    + knopf(f.sortierung === "name", 'data-sort="name"', "Nach Name")
    + `<label><input type="checkbox" data-schalter="nurOffen"${f.nurOffen ? " checked" : ""}> Nur offene</label>`
    + `<label><input type="checkbox" data-schalter="mitEreignissen"${f.mitEreignissen ? " checked" : ""}> Ereignisse einblenden</label>`
    + '</div><div class="su-chips">'
    + knopf(!f.name, 'data-name=""', "Alle " + chips.reduce((n, c) => n + c.anzahl, 0))
    + chips.map((c) => knopf(f.name && _nameKey(f.name) === _nameKey(c.name), `data-name="${escape(c.name)}"`, `${c.name} ${c.anzahl}`)).join("")
    + "</div>";
  const karte = (titel, items, mitSpiel) => {
    const offen = items.filter((s) => s.fehlt && s.fehlt.length).length;
    return `<details class="nutz-karte${offen ? " nie" : ""}" open>
      <summary><span class="nk-name">${escape(titel)}</span>
        <span class="nk-zahlen">${items.length} ${items.length === 1 ? "Eintrag" : "Einträge"}${offen ? ` · <b>${offen}</b> mit Offenem` : ""}</span></summary>
      <div class="nk-detail">${items.map((s) => szenenZeile(s, mitSpiel)).join("")}</div></details>`;
  };
  let treffer = 0;
  if (f.sortierung === "name") {
    const gefiltert = filtereSzenen(alle, optionen);
    treffer = gefiltert.length;
    html += gruppiereNachName(gefiltert).map((g) => karte(g.name, g.items, true)).join("");
  } else {
    for (const g of spiele) {
      const items = filtereSzenen(g.szenen, optionen);
      treffer += items.length;
      if (items.length) html += karte(g.spiel || "Spiel " + g.analyse_id, items, false);
    }
  }
  if (!treffer) html += '<p class="hinweis">Keine Einträge für diesen Filter.</p>';
  return html + '<p class="hinweis">✓ komplett angeschaut (mindestens 60 %) · ◐ nur angetippt · ○ nie geöffnet. '
    + "„x von y“ = wie viele der Beteiligten ihn komplett gesehen haben. Tippen öffnet den Clip.</p>";
}
// Klicks der Spielzug-Uebersicht: Filter und Clip oeffnen (Delegation - die Ansicht wird neu gezeichnet)
function szenenKlick(e) {
  const t = e.target.closest("button[data-sort], button[data-name], button[data-clip], input[data-schalter]");
  if (!t) return;
  if (t.dataset.clip) {
    const s = (szenenDaten.spiele || []).flatMap((g) => g.szenen).find((x) => x.id === t.dataset.sid);
    if (!s) return;
    oeffneSzenenClip(+t.dataset.clip, s.id + " · " + s.label,
      { text: s.label + " (" + s.id + ")", farbe: s.ampel || "grau", kommentar: s.kommentar || "",
        zeit: [s.spiel, s.zeit].filter(Boolean).join(" · ") });
    return;
  }
  if (t.dataset.sort) szenenFilter.sortierung = t.dataset.sort;
  else if (t.dataset.schalter) szenenFilter[t.dataset.schalter] = t.checked;
  else szenenFilter.name = t.dataset.name || null;
  const y = window.scrollY;
  renderVideos();
  window.scrollTo(0, y);
}
function renderTrainerVideos() {
  const el = $("#videos-liste");
  el.innerHTML = "";
  const box = document.createElement("div");
  box.className = "su-voll";
  box.innerHTML = renderSzenenUebersicht();
  box.addEventListener("click", szenenKlick);
  el.appendChild(box);
  const h = document.createElement("h3");
  h.className = "videos-h su-voll";
  h.textContent = "Eigene Clips";
  el.appendChild(h);
  if (!(videoClips || []).length) {
    const p = document.createElement("p");
    p.className = "hinweis su-voll";
    p.textContent = "Noch keine eigenen Clips. Sie werden am PC mit „Balu-Videoschnitt“ hochgeladen.";
    el.appendChild(p);
  }
  for (const c of videoClips || []) el.appendChild(videoKarte(c));
}
function renderVideos() {
  const el = $("#videos-liste");
  if (aktRolle === "trainer") { renderTrainerVideos(); return; }
  const clips = videoClips || [];
  const spiele = videoSpiele || [];
  if (!clips.length && !spiele.length) {
    el.innerHTML = '<p class="hinweis">Für dich sind noch keine Videos hinterlegt.</p>';
    return;
  }
  el.innerHTML = "";
  if (spiele.length) {
    const h = document.createElement("h3");
    h.className = "videos-h";
    h.textContent = "Spiele";
    el.appendChild(h);
    for (const a of spiele) el.appendChild(spielKarte(a));
  }
  if (clips.length) {
    if (spiele.length) {
      const h = document.createElement("h3");
      h.className = "videos-h";
      h.textContent = "Einzelne Szenen";
      el.appendChild(h);
    }
    for (const c of clips) el.appendChild(videoKarte(c));
  }
  if (aktRolle !== "trainer") {                       // Transparenz: Spielerinnen wissen, dass mitgezaehlt wird
    const p = document.createElement("p");
    p.className = "hinweis";
    p.textContent = "Dein Trainer sieht, welche Videos du angeschaut hast.";
    el.appendChild(p);
  }
}
// Ein Spiel mit Videoanalyse: Gegner, Datum, wie viele Szenen es fuer die Spielerin gibt.
function spielKarte(a) {
  const karte = document.createElement("button");
  karte.className = "video-karte";
  const meta = [a.datum ? datumKurz(a.datum) : "", a.art].filter(Boolean).join(" · ");
  const n = (a.meine_events || 0) + (a.meine_zuege || 0);
  const szenen = n ? n + (n === 1 ? " Szene für dich" : " Szenen für dich") : "keine Szenen für dich";
  karte.innerHTML = `<span class="vk-titel">${escape(a.gegner)}</span>`
    + (meta ? `<span class="vk-meta">${escape(meta)}</span>` : "")
    + `<span class="vk-notiz">Videoanalyse · ${escape(szenen)}${a.video_da ? "" : " · Video folgt"}</span>`;
  karte.addEventListener("click", () => oeffneAnalyseDetail(a.id));
  return karte;
}
function videoKarte(c) {
  const karte = document.createElement("button");
  karte.className = "video-karte";
  const meta = [];
  if (c.spiel_datum) meta.push(datumKurz(c.spiel_datum));
  if (c.dauer_s) meta.push(Math.round(c.dauer_s) + " s");
  let inner = `<span class="vk-titel">${escape(c.titel)}</span>`;
  if (meta.length) inner += `<span class="vk-meta">${escape(meta.join(" · "))}</span>`;
  if (c.notiz) inner += `<span class="vk-notiz">${escape(c.notiz)}</span>`;
  if (aktRolle === "trainer") {
    const namen = (c.spieler || []).map((s) => s.name).join(", ") || "niemandem zugeordnet";
    inner += `<span class="vk-spieler">${escape(namen)}${c.kommentare ? " · 💬 " + c.kommentare : ""}</span>`;
  }
  karte.innerHTML = inner;
  karte.addEventListener("click", () => oeffneVideo(c));
  return karte;
}
export function oeffneVideo(c) {
  nutzungMelden("video", "clip:" + c.id, c.titel);
  wiedergabeBeobachten("clip:" + c.id, c.titel);
  ladeKommentare("clip:" + c.id);
  aktVideo = c;
  setzeAnalyseZurueckView(null);
  zeigeSzenenNotiz(null);
  $("#btn-video-zurueck").textContent = "← Videos";
  $("#vd-titel").textContent = c.titel;
  const player = $("#vd-player");
  player.src = "/api/clips/" + c.id + "/video";
  player.load();
  const teile = [];
  if (c.spiel_datum) teile.push(datumKurz(c.spiel_datum));
  if (c.notiz) teile.push(c.notiz);
  $("#vd-meta").textContent = teile.join(" · ");
  renderVideoAktionen(c);
  zeigeView("view-video-detail");
}
// Echte Wiedergabe: "geoeffnet" (video) sagt nur, dass der Player aufging. Hier zaehlt die
// tatsaechlich abgespielte Zeit; ab 60 % der Laenge geht EIN Ereignis "gespielt" raus.
// Vorspringen zaehlt nicht mit (nur kleine Zeitspruenge zwischen zwei timeupdate-Events).
// Nur fuer kurze Clips; beim ganzen Spiel (spiel:) waere 60 % der falsche Massstab.
let _wiedergabe = null;       // { ziel, titel, gesehen (s), letzte (s), gemeldet }
export function wiedergabeBeobachten(ziel, titel) {
  _wiedergabe = ziel ? { ziel, titel, gesehen: 0, letzte: null, gemeldet: false } : null;
}
(function () {
  const p = $("#vd-player");
  if (!p) return;
  p.addEventListener("timeupdate", () => {
    const w = _wiedergabe;
    if (!w || w.gemeldet || p.paused || !(p.duration > 0)) return;
    const d = p.currentTime - (w.letzte ?? p.currentTime);
    w.letzte = p.currentTime;
    if (d > 0 && d < 1.5) w.gesehen += d;
    if (w.gesehen >= 0.6 * p.duration) {
      w.gemeldet = true;
      nutzungMelden("gespielt", w.ziel, w.titel);
    }
  });
  p.addEventListener("seeking", () => { if (_wiedergabe) _wiedergabe.letzte = null; });
})();
// ---- Fragen & Kommentare unter dem Video -------------------------------------
//  Sichtbar fuer alle, die das Video sehen duerfen. "Nur fuer Trainer" macht einen
//  Kommentar privat (Trainer + Verfasserin); Antworten in einem privaten Faden bleiben
//  privat (das erzwingt der Server, nicht dieses UI). Online-only wie das Video selbst.
let _kommentarZiel = null;
let _kommentarListe = [];
let _kommentarAntwortAuf = null;       // id des Kommentars, auf den gerade geantwortet wird
export async function ladeKommentare(ziel) {
  _kommentarZiel = ziel;
  _kommentarAntwortAuf = null;
  _kommentarListe = [];
  if (!ziel) { $("#vd-kommentare").innerHTML = ""; return; }
  renderKommentare();
  try {
    const liste = await api("/api/kommentare?ziel=" + encodeURIComponent(ziel));
    if (_kommentarZiel === ziel) { _kommentarListe = liste; renderKommentare(); }   // nicht in ein anderes Video rendern
  } catch (_) { /* ohne Netz: Eingabe bleibt leer sichtbar, Senden meldet den Fehler */ }
}
function kommentarFehlertext(e) {
  try { return JSON.parse(e.message).detail || e.message; } catch (_) { return e.message; }
}
function renderKommentare() {
  const box = $("#vd-kommentare");
  if (!_kommentarZiel) { box.innerHTML = ""; return; }
  const trainer = aktRolle === "trainer";
  const entwurf = box.querySelector("#km-text") ? box.querySelector("#km-text").value : "";
  const privatGewaehlt = box.querySelector("#km-privat") ? box.querySelector("#km-privat").checked : false;
  const antworten = {};
  for (const k of _kommentarListe) if (k.antwort_auf) (antworten[k.antwort_auf] = antworten[k.antwort_auf] || []).push(k);
  const eintrag = (k, istAntwort) => `<div class="km${istAntwort ? " km-antwort" : ""}${k.nur_trainer ? " km-privat" : ""}" data-km-id="${k.id}">
      <div class="km-kopf"><b>${escape(k.name)}</b>${k.trainer ? '<span class="km-badge">Trainer</span>' : ""}`
    + `${k.nur_trainer ? '<span class="km-lock">🔒 nur Trainer</span>' : ""}<small>${escape(vorZeit(k.zeit))}</small></div>
      <p class="km-text">${escape(k.text)}</p>
      <div class="km-knoepfe">${istAntwort ? "" : `<button type="button" data-km-antwort="${k.id}">Antworten</button>`}`
    + `${k.eigene || trainer ? `<button type="button" data-km-loeschen="${k.id}">Löschen</button>` : ""}</div></div>`;
  const oben = _kommentarListe.filter((k) => !k.antwort_auf);
  const liste = oben.length
    ? oben.map((k) => eintrag(k, false) + (antworten[k.id] || []).map((a) => eintrag(a, true)).join("")).join("")
    : '<p class="hinweis">Noch keine Fragen oder Kommentare.</p>';
  const ziel = _kommentarAntwortAuf && _kommentarListe.find((k) => k.id === _kommentarAntwortAuf);
  const erzwungenPrivat = !!(ziel && ziel.nur_trainer);
  box.innerHTML = `<h3 class="videos-h">Fragen &amp; Kommentare</h3>
    <div class="km-liste">${liste}</div>
    <div class="km-neu">
      ${ziel ? `<div class="km-an">Antwort an ${escape(ziel.name)} <button type="button" data-km-abbruch>✕</button></div>` : ""}
      <textarea id="km-text" rows="3" maxlength="1000" placeholder="${trainer ? "Kommentar oder Antwort …" : "Frage oder Kommentar zu diesem Video …"}"></textarea>
      ${trainer ? "" : `<label class="km-privatwahl"><input type="checkbox" id="km-privat"${erzwungenPrivat || privatGewaehlt ? " checked" : ""}${erzwungenPrivat ? " disabled" : ""}> 🔒 Nur für Trainer sichtbar</label>`}
      <button type="button" id="km-senden" class="primaer">Senden</button>
    </div>`;
  $("#km-text").value = entwurf;                       // Entwurf bleibt beim Neuzeichnen erhalten
}
async function sendeKommentar() {
  const feld = $("#km-text");
  const text = feld.value.trim();
  if (!text) return;
  const knopf = $("#km-senden");
  knopf.disabled = true;
  knopf.textContent = "Sendet …";              // bei schlechtem Netz dauert es: sichtbar machen, dass etwas laeuft
  const privat = $("#km-privat");
  try {
    _kommentarListe = await api("/api/kommentare", "POST", {
      ziel: _kommentarZiel, text, nur_trainer: privat ? privat.checked : false,
      antwort_auf: _kommentarAntwortAuf,
    });
    const neueId = Math.max(0, ..._kommentarListe.filter((k) => k.eigene).map((k) => k.id));
    _kommentarAntwortAuf = null;
    feld.value = "";
    if (privat) privat.checked = false;
    renderKommentare();
    // Rueckmeldung: Tastatur zu, Bestaetigung, zum neuen Kommentar scrollen. Er steht UEBER dem
    // Eingabefeld und liegt sonst (vor allem bei offener Tastatur) ausserhalb des Sichtbaren.
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    toast("Kommentar gesendet ✓");
    const neu = $("#vd-kommentare").querySelector(`[data-km-id="${neueId}"]`);
    if (neu) neu.scrollIntoView({ block: "center", behavior: "smooth" });
  } catch (e) {
    toast("Konnte nicht senden: " + kommentarFehlertext(e));
    knopf.disabled = false;
    knopf.textContent = "Senden";
  }
}
$("#vd-kommentare").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.id === "km-senden") { sendeKommentar(); return; }
  if (b.dataset.kmAbbruch !== undefined) { _kommentarAntwortAuf = null; renderKommentare(); return; }
  if (b.dataset.kmAntwort) {
    _kommentarAntwortAuf = +b.dataset.kmAntwort;
    renderKommentare();
    $("#km-text").focus();
    return;
  }
  if (b.dataset.kmLoeschen) {
    if (b.dataset.scharf !== "1") { b.dataset.scharf = "1"; b.textContent = "Wirklich löschen?"; return; }
    try {
      await api("/api/kommentare/" + b.dataset.kmLoeschen + "/loeschen", "POST");
      _kommentarListe = _kommentarListe.filter((k) => k.id !== +b.dataset.kmLoeschen
                                                       && k.antwort_auf !== +b.dataset.kmLoeschen);
      renderKommentare();
    } catch (err) { toast("Konnte nicht löschen: " + kommentarFehlertext(err)); }
  }
});
function stoppeVideoPlayer() {
  const p = $("#vd-player");
  if (!p) return;
  wiedergabeBeobachten(null);
  ladeKommentare(null);
  p.pause();
  p.removeAttribute("src");
  p.load();
}
function renderVideoAktionen(c) {
  const box = $("#vd-aktionen");
  box.innerHTML = "";
  if (aktRolle !== "trainer") return;
  const umhaengen = document.createElement("button");
  umhaengen.className = "plan-edit-btn";
  umhaengen.textContent = "👥 Spielerinnen zuordnen";
  umhaengen.addEventListener("click", () => videoZuordnenDialog(c));
  const loeschen = document.createElement("button");
  loeschen.className = "plan-edit-btn gefahr";
  loeschen.textContent = "🗑 Löschen";
  let scharf = false;
  loeschen.addEventListener("click", async () => {
    if (!scharf) { scharf = true; loeschen.textContent = "Wirklich löschen?"; return; }
    try {
      await api("/api/clips/" + c.id + "/loeschen", "POST");
      toast("Clip gelöscht.");
      videoClips = null;
      stoppeVideoPlayer();
      gehe(aktOber, "videos");
    } catch (e) { toast("Fehler: " + e.message); }
  });
  box.appendChild(umhaengen);
  box.appendChild(loeschen);
}
function videoZuordnenDialog(c) {
  const box = $("#vd-aktionen");
  box.innerHTML = "";
  const gewaehlt = new Set((c.spieler || []).map((s) => s.id));
  const liste = document.createElement("div");
  liste.className = "video-zuordnen";
  for (const sp of (videoKader || [])) {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = gewaehlt.has(sp.id);
    cb.addEventListener("change", () => {
      if (cb.checked) gewaehlt.add(sp.id); else gewaehlt.delete(sp.id);
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" " + sp.name));
    liste.appendChild(label);
  }
  const speichern = document.createElement("button");
  speichern.className = "primaer";
  speichern.textContent = "Speichern";
  speichern.addEventListener("click", async () => {
    try {
      const akt = await api("/api/clips/" + c.id, "POST", { spieler_ids: [...gewaehlt] });
      toast("Zuordnung gespeichert ✓");
      videoClips = null;
      oeffneVideo(akt);
    } catch (e) { toast("Fehler: " + e.message); }
  });
  const abbrechen = document.createElement("button");
  abbrechen.textContent = "Abbrechen";
  abbrechen.addEventListener("click", () => renderVideoAktionen(c));
  box.appendChild(liste);
  box.appendChild(speichern);
  box.appendChild(abbrechen);
}
$("#btn-video-zurueck").addEventListener("click", () => {
  stoppeVideoPlayer();
  if (analyseZurueckView) {                 // kam aus einem Spielerprofil
    const v = analyseZurueckView;
    setzeAnalyseZurueckView(null);
    $("#btn-video-zurueck").textContent = "← Videos";
    mitScrollRueckkehr(() => zeigeView(v));
    return;
  }
  mitScrollRueckkehr(() => gehe(aktOber, "videos"));
});
