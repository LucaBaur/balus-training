import { renderHomeAemter } from "./aemter.js";
import { ladeAnalysen, oeffneAnalyseDetail, oeffneAnalyseVideo, oeffneSzenenClip } from "./analysen.js";
import { api } from "../core/api.js";
import { aktBenutzer, aktRolle, eigeneSpielerId } from "../core/konto.js";
import { ligaHolen, ligaHomeKarte, ligaNaechste } from "./liga.js";
import { renderPushBox } from "./push.js";
import { gehe, icon } from "../core/router.js";
import { ART_WORT, istSpiel, oeffneTraining, rsvpFuellen, terminArt } from "./termine.js";
import { todoLetztesFeedback } from "./todos.js";
import { $, datumKurz, datumTeile, escape, heuteIso, toast } from "../core/ui.js";
import { oeffneVideo } from "./videos.js";

// ------------------------------------------------------------------ Home ----
//  Eine Startseite, zwei Gesichter. Spielerin: das Nächste zum Antworten steht groß oben,
//  darunter was neu für sie ist. Trainer: oben die Liste "Braucht dich".
//  Welche Termine/Neuigkeiten gezeigt werden, entscheidet home-logik.js (getestet).
let _homeHeroId = null;      // das große Training oben; steht nicht noch einmal unter "Antwort fehlt"
export async function ladeHome() {
  $("#view-home").classList.toggle("home-trainer", aktRolle === "trainer");
  renderPushBox();
  renderHomeAufgaben();
  await renderHomeHero();
  renderHomeOffen();
  renderHomeNeu();
  renderHomeTodo();
  renderHomeAemter();
  renderHomeSpiele();
  renderHomeTabelle();
  renderHomeSchnell();
}
async function renderHomeHero() {
  const el = $("#home-naechstes");
  let liste = [];
  try { liste = await Sync.apiOffline("/api/trainings"); } catch (_) {}
  const t = HomeLogik.naechstesTraining(liste, heuteIso());
  _homeHeroId = t ? t.id : null;
  if (!t) {
    el.className = "home-karte";
    el.innerHTML = '<div class="hk-titel">Nächstes Training</div><p class="hk-leer">Kein anstehendes Training gefunden.</p>';
    return;
  }
  const d = datumTeile(t.datum);
  const sid = eigeneSpielerId();
  const ortTeil = t.ort && !(t.titel || "").includes(t.ort) ? " · " + t.ort : "";
  el.className = "home-karte hero";
  el.innerHTML =
    `<div class="hk-titel">Nächstes Training</div>
     <div class="hk-name">${escape(HomeLogik.wochentag(t.datum))}, ${escape(d.tag)}${t.uhrzeit ? " · " + escape(t.uhrzeit) : ""}</div>
     <div class="hk-datum">${escape((t.titel || "Training") + ortTeil)}</div>
     <div class="hk-zahlen"><span class="zu">${t.anwesend || 0} sagen zu</span>${t.abgesagt ? `<span class="ab">${t.abgesagt} abgesagt</span>` : ""}</div>
     ${sid ? '<div class="td-rsvp hero-rsvp"></div>' : ""}
     <button type="button" class="hk-link">${aktRolle === "trainer" ? "Öffnen und Plan" : "Termin öffnen"} ${icon("chevron")}</button>`;
  if (sid) {
    // Kurz-Objekt: rsvpSenden mutiert es, cacht es aber bewusst NICHT (siehe renderHomeOffen).
    rsvpFuellen(el.querySelector(".hero-rsvp"),
      { id: t.id, teilnahme: t.meine_status ? [{ id: sid, status: t.meine_status, grund: null }] : [] });
  }
  el.querySelector(".hk-link").addEventListener("click", () => {
    gehe("training", "trainings");
    setTimeout(() => oeffneTraining(t.id), 0);
  });
}
const AUFGABE_SYMBOL = { duenn: "alert", offen: "users", nachbereitung: "notes", todos: "checklist", frage: "play" };
// "clip:5" / "szene:12" / "spiel:3" (Ziel eines Kommentars) -> das passende Video oeffnen.
async function oeffneVideoZiel(ziel, titel) {
  const [art, kennung] = ziel.split(":"), id = +kennung;
  try {
    if (art === "clip") {
      const clips = await api("/api/clips");
      const c = clips.find((x) => x.id === id);
      if (!c) { toast("Dieses Video gibt es nicht mehr."); return; }
      gehe("videos", "videos");
      oeffneVideo(c);
    } else if (art === "szene") {
      oeffneSzenenClip(id, titel, null);
    } else if (art === "spiel") {
      oeffneAnalyseVideo(id, 0, titel, null);
    }
  } catch (e) { toast("Konnte das Video nicht öffnen."); }
}
// Trainer: was ihn gerade braucht, wichtigstes zuerst.
async function renderHomeAufgaben() {
  const el = $("#home-aufgaben");
  if (aktRolle !== "trainer") { el.innerHTML = ""; return; }
  let liste = [], todos = 0;
  try { liste = await Sync.apiOffline("/api/trainings"); } catch (_) {}
  let fragen = [];
  // Nur To-Dos, deren Woche vorbei ist: waehrend die Spielerin noch probiert, gibt es nichts zu bewerten.
  try { todos = ((await Sync.apiOffline("/api/todos/team")) || {}).warten_faellig || 0; } catch (_) {}
  try { fragen = (await Sync.apiOffline("/api/fragen-offen")) || []; } catch (_) {}
  const aufgaben = HomeLogik.trainerAufgaben({ trainings: liste, todosWartend: todos, fragen, heute: heuteIso() });
  if (!aufgaben.length) {
    el.innerHTML = `<div class="ha-karte"><div class="ha-kopf">Braucht dich</div>
      <p class="ha-leer">${icon("check")} Gerade ist nichts offen.</p></div>`;
    return;
  }
  el.innerHTML = `<div class="ha-karte"><div class="ha-kopf">Braucht dich</div>` +
    aufgaben.map((a, i) => `<button type="button" class="ha-zeile ${a.stufe}" data-i="${i}">
      <span class="ha-icon">${icon(AUFGABE_SYMBOL[a.art] || "alert")}</span>
      <span class="ha-text"><b>${escape(a.titel)}</b><span>${escape(a.sub)}</span></span>
      <span class="ha-pfeil">${icon("chevron")}</span></button>`).join("") + "</div>";
  el.querySelectorAll(".ha-zeile").forEach((b) => b.addEventListener("click", () => {
    const z = aufgaben[+b.dataset.i].ziel;
    if (z.video) { oeffneVideoZiel(z.video, z.titel); return; }
    gehe(z.ober, z.unter);
    if (z.termin) setTimeout(() => oeffneTraining(z.termin), 0);
  }));
}
// ---- Neu für dich (Spielerin) ----
//  "Neu" heißt: Clip oder Analyse mit höherer ID als beim letzten Besuch von "Videos".
//  Beim ersten Mal wird nur die Grundlinie gemerkt - sonst wäre alles Alte neu.
const neuGesehenLesen = (sid) => {
  try { return JSON.parse(localStorage.getItem("neu_gesehen_" + sid) || "null"); } catch (_) { return null; }
};
const neuGesehenSchreiben = (sid, g) => { try { localStorage.setItem("neu_gesehen_" + sid, JSON.stringify(g)); } catch (_) {} };
async function neuDaten(sid) {
  let clips = [], analysen = [];
  try { clips = (await Sync.apiOffline("/api/clips")) || []; } catch (_) {}
  try { analysen = (await ladeAnalysen(sid)) || []; } catch (_) {}
  return { clips, analysen };
}
function markiereTab(key, neu) {
  const b = document.querySelector(`#tableiste [data-ober="${key}"]`);
  if (b) b.classList.toggle("neu", !!neu);
}
async function renderHomeNeu() {
  const el = $("#home-neu");
  const sid = eigeneSpielerId();
  if (!sid || aktRolle !== "spieler") { el.innerHTML = ""; return; }
  const { clips, analysen } = await neuDaten(sid);
  const gesehen = neuGesehenLesen(sid);
  const r = HomeLogik.neuFuerDich({ clips, analysen, gesehen });
  if (!gesehen) neuGesehenSchreiben(sid, r.grundlinie);
  markiereTab("videos", r.anzahl);
  if (!r.items.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<div class="hn-karte"><div class="hn-kopf">Neu für dich${r.anzahl > r.items.length ? " · " + r.anzahl : ""}</div>` +
    r.items.map((i) => `<button type="button" class="hn-zeile" data-art="${i.art}" data-id="${i.id}">
      <span class="hn-icon">${icon("play")}</span>
      <span class="hn-text"><b>${escape(i.titel)}</b>${i.sub ? `<span>${escape(i.art === "analyse" ? datumKurz(i.sub) : i.sub)}</span>` : ""}</span>
      <span class="hn-neu">neu</span></button>`).join("") + "</div>";
  el.querySelectorAll(".hn-zeile").forEach((b) => b.addEventListener("click", () => {
    gehe("videos", "videos");
    if (b.dataset.art === "analyse") oeffneAnalyseDetail(+b.dataset.id);
  }));
}
// Wer "Videos" öffnet, hat gesehen, was dort steht.
export async function videosAlsGesehenMerken() {
  const sid = eigeneSpielerId();
  if (!sid) return;
  const { clips, analysen } = await neuDaten(sid);
  const hoechste = HomeLogik.neuFuerDich({ clips, analysen, gesehen: null }).grundlinie;
  let g = neuGesehenLesen(sid);
  g = HomeLogik.alsGesehen(g, "clip", hoechste.clip);
  g = HomeLogik.alsGesehen(g, "analyse", hoechste.analyse);
  neuGesehenSchreiben(sid, g);
  markiereTab("videos", false);
}
// Wohin "zurück" aus einer Analyse führt: Spielerin -> Videos, Trainer -> Team/Videos.
export const videosOber = () => (aktRolle === "trainer" ? "team" : "videos");
// ---- Wochenziel (Spielerin) ----
async function renderHomeTodo() {
  const el = $("#home-todo");
  if (!eigeneSpielerId() || aktRolle !== "spieler") { el.innerHTML = ""; return; }
  let d = null;
  try { d = await Sync.apiOffline("/api/todos"); } catch (_) {}
  const todos = (d && d.todos) || [];
  const gewaehlt = todos.find((t) => t.gewaehlt && t.status === "offen");
  const frei = todos.filter((t) => t.status === "offen" && !t.gewaehlt);
  if (gewaehlt) {
    const f = todoLetztesFeedback(gewaehlt);
    el.innerHTML = `<button type="button" class="ht-karte ziel"><div class="ht-kopf"><b>Dein Ziel diese Woche</b></div>
      <p class="ht-text">${escape(gewaehlt.text)}</p>
      ${f && f.feedback ? `<p class="ht-sub">Trainer: ${escape(f.feedback)}</p>` : ""}</button>`;
  } else if (frei.length) {
    el.innerHTML = `<button type="button" class="ht-karte ziel"><div class="ht-kopf"><b>Wähle dein Ziel für diese Woche</b></div>
      <p class="ht-sub">${frei.length === 1 ? "1 Ziel" : frei.length + " Ziele"} zur Auswahl</p></button>`;
  } else { el.innerHTML = ""; return; }
  el.querySelector("button").addEventListener("click", () => gehe("ich", "todo"));
}
// ---- Tabellen-Auszug ----
async function renderHomeTabelle() {
  const el = $("#home-tabelle");
  const d = await ligaHolen();
  const a = d && HomeLogik.tabellenAuszug(d.tabelle);
  if (!a) { el.innerHTML = ""; return; }
  el.innerHTML = `<button type="button" class="ht-karte"><div class="ht-kopf"><b>Tabelle</b><span class="ht-platz">Platz ${a.platz}</span></div>` +
    a.zeilen.map((z) => `<div class="ht-zeile${z.eigen ? " eigen" : ""}"><span>${z.platz}. ${escape(z.team)}</span><b>${escape(z.punkte)}</b></div>`).join("") + "</button>";
  el.querySelector("button").addEventListener("click", () => gehe("home", "liga"));
}
// Die naechsten drei Test-/Ligaspiele. Sie stehen fest oben auf der Startseite:
// Spiele sind die Termine, um die herum die Saison geplant wird - und bei
// Auswaertsspielen ist die Abfahrtszeit das, was man kurz nachschaut.
async function renderHomeSpiele() {
  const el = $("#home-spiele");
  if (!el) return;
  let liste = [];
  try { liste = await Sync.apiOffline("/api/trainings"); } catch (_) { el.innerHTML = ""; return; }

  const heute = new Date().toISOString().slice(0, 10);
  const spiele = (liste || [])
    .filter((t) => istSpiel(t) && (t.datum || "") >= heute)
    .sort((a, b) => (a.datum || "").localeCompare(b.datum || ""))
    .slice(0, 3);

  if (!spiele.length) {
    // Noch nichts selbst eingetragen: die naechsten Spiele aus dem Verbands-Spielplan.
    const aus = await ligaNaechste(3);
    el.innerHTML = '<div class="hs-kopf">Nächste Spiele</div>';
    if (!aus.length) {
      el.innerHTML += '<p class="hinweis">Noch kein Test- oder Ligaspiel eingetragen.</p>';
      return;
    }
    for (const sp of aus) el.appendChild(ligaHomeKarte(sp));
    return;
  }

  el.innerHTML = `<div class="hs-kopf">Nächste Spiele</div>`;
  for (const t of spiele) {
    const d = datumTeile(t.datum);
    const karte = document.createElement("button");
    karte.className = "hs-spiel " + terminArt(t) + (t.heim === 0 ? " auswaerts" : "");
    karte.innerHTML =
      `<span class="hs-datum"><b>${d.wt}</b><span>${escape(d.tag)}</span></span>
       <span class="hs-mitte">
         <span class="hs-titel">${escape(t.titel || ART_WORT[terminArt(t)])}</span>
         <span class="hs-meta">${ART_WORT[terminArt(t)]}` +
        `${t.heim === 0 ? " · auswärts" : " · daheim"}${t.ort ? " · " + escape(t.ort) : ""}</span>
       </span>
       <span class="hs-zeit">${t.heim === 0 && t.abfahrt
          ? `<b>${escape(t.abfahrt)}</b><small>Abfahrt</small>`
          : t.uhrzeit ? `<b>${escape(t.uhrzeit)}</b><small>Anwurf</small>` : ""}</span>`;
    karte.addEventListener("click", () => {
      gehe("training", "trainings");
      setTimeout(() => oeffneTraining(t.id), 0);
    });
    el.appendChild(karte);
  }
}
// „Worauf wartet das Team noch von MIR?" - alle kommenden Termine ohne eigene
// Antwort, jeder direkt hier beantwortbar. Wer ein Spielerprofil hat, sieht
// die Box (auch Trainerinnen, die selbst mitspielen).
export async function renderHomeOffen() {
  const el = $("#home-offen");
  if (!el) return;
  if (!(aktBenutzer && aktBenutzer.spieler_id)) {
    // Spielerin ohne Profil: ohne Hinweis fehlen "Ich" und "Videos" kommentarlos.
    el.innerHTML = aktRolle === "spieler"
      ? '<p class="hinweis">Dein Zugang ist noch keinem Spielerprofil zugeordnet – '
        + 'deshalb fehlen „Ich“ und „Videos“. Tippe oben rechts auf „synchron“ zum '
        + 'Aktualisieren. Hilft das nicht, melde dich beim Trainer.</p>'
      : "";
    return;
  }

  let liste = [];
  try { liste = await Sync.apiOffline("/api/trainings"); } catch (_) { el.innerHTML = ""; return; }

  // Das große Training oben hat seine eigenen Knöpfe, hier stehen nur die übrigen.
  const offen = HomeLogik.offeneAntworten(liste, heuteIso(), _homeHeroId);

  if (!offen.length) {
    el.innerHTML = '<div class="ho-fertig">✓ Für alle kommenden Termine hast du geantwortet.</div>';
    return;
  }

  el.innerHTML = `<div class="ho-kopf">Deine Antwort fehlt noch · ${offen.length}</div>`;
  for (const t of offen) {
    const d = datumTeile(t.datum);
    const karte = document.createElement("div");
    karte.className = "ho-termin";
    karte.innerHTML =
      `<div class="ho-zeile"><span class="ho-datum"><b>${d.wt}</b> ${escape(d.tag)}</span>` +
      `<span class="ho-titel">${escape(t.titel || "Training")}` +
      `${t.uhrzeit ? ` <small>${escape(t.uhrzeit)}</small>` : ""}</span></div>`;
    const box = document.createElement("div");
    box.className = "td-rsvp";
    // Kurz-Objekt: rsvpSenden mutiert es, cacht es aber bewusst NICHT.
    rsvpFuellen(box, { id: t.id, teilnahme: [] });
    karte.appendChild(box);
    el.appendChild(karte);
  }
}
function renderHomeSchnell() {
  const el = $("#home-schnell");
  el.innerHTML = "";
  if (aktRolle !== "trainer") return;               // Spielerinnen haben alles in der Leiste unten
  const ziele = [["team", "rangliste", "chart", "Rangliste"], ["training", "coach", "notes", "Coach"],
                 ["training", "aufstellung", "users", "Aufstellung"], ["taktik", "playbook", "target", "Playbook"]];
  for (const [ober, unter, sym, label] of ziele) {
    const b = document.createElement("button");
    b.className = "schnell-kachel";
    b.innerHTML = `<span class="sk-icon">${icon(sym)}</span><span>${label}</span>`;
    b.addEventListener("click", () => gehe(ober, unter));
    el.appendChild(b);
  }
}
