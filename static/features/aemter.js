import { api } from "../core/api.js";
import { aktBenutzer, aktRolle, eigeneSpielerId, setzeBenutzer } from "../core/konto.js";
import { gehe } from "../core/router.js";
import { $, datumTeile, escape, heuteIso, toast } from "../core/ui.js";

// ================================================================== Ämter ====
//  Ämter der Mannschaft (aemter.py). Hier wird nur gezeigt, was die Rolle oder das Amt erlaubt;
//  die Rechte prüft der Server bei jedem Aufruf. Wie bei den To-Dos geht das Schreiben nur online.
//  Reiter "Mannschaft" (Spielerin) bzw. Saison (Trainer) mit zwei Seiten:
//    Ämter   wer hat welches Amt, was heißt das; der Trainer vergibt sie
//    Listen  Trikots, Leibchen, Getränke, Bussle: wer ist dran, wer wie oft
let aemterDaten = null;                 // Antwort von /api/aemter
const aemterBearbeiten = new Set();     // Ämter, die der Trainer gerade bearbeitet
const aemterEntwurf = new Map();        // ungespeicherter Beschreibungstext je Amt
const listenDaten = new Map();          // amt_id -> Antwort von /api/aemter/:id/liste
const listenOffen = new Set();          // aufgeklappte Listen; bleibt beim Neuzeichnen
const listenGesehen = new Set();        // Listen, deren Startzustand (auf/zu) schon gesetzt wurde
export const hatRecht = (r) => !!(aktBenutzer && (aktBenutzer.rechte || []).includes(r));
export const amtOber = () => (aktRolle === "trainer" ? "saison" : "mannschaft");
const amtFehler = (e) => {
  try { return JSON.parse(e.message).detail || e.message; } catch (_) { return e.message; }
};
export async function ladeAemter() {
  const el = $("#aemter-inhalt");
  if (!aemterDaten) el.innerHTML = '<p class="hinweis">Lädt…</p>';
  try {
    aemterDaten = await api("/api/aemter");
    renderAemter();
  } catch (_) {
    if (!aemterDaten) el.innerHTML = '<p class="hinweis">Die Ämter konnten nicht geladen werden – dafür brauchst du eine Verbindung.</p>';
  }
}
function amtKarte(a) {
  const sid = eigeneSpielerId();
  const verwalten = aemterDaten.kann_verwalten;
  const edit = verwalten && aemterBearbeiten.has(a.id);
  const namen = a.inhaber.length
    ? a.inhaber.map((i) => `<span class="amt-chip${i.spieler_id === sid ? " ich" : ""}">${escape(i.name)}</span>`).join("")
    : '<span class="amt-leer">noch niemand</span>';
  let editor = "";
  if (edit) {
    const hat = new Set(a.inhaber.map((i) => i.spieler_id));
    const text = aemterEntwurf.has(a.id) ? aemterEntwurf.get(a.id) : a.beschreibung;
    editor = `<div class="amt-editor">
      <label>Beschreibung<textarea rows="3" maxlength="500" data-amt-text="${a.id}">${escape(text)}</textarea></label>
      <button type="button" class="todo-knopf primaer" data-amt-speichern="${a.id}">Beschreibung speichern</button>
      <div class="amt-wahl-titel">Wer hat das Amt? Antippen zum Vergeben oder Entziehen.</div>
      <div class="amt-inhaber">${aemterDaten.kader.map((k) =>
        `<button type="button" class="amt-chip wahl${hat.has(k.id) ? " an" : ""}" data-amt-inhaber="${a.id}" data-sp="${k.id}" data-an="${hat.has(k.id) ? 0 : 1}">${escape(k.name)}</button>`).join("")}</div>
    </div>`;
  }
  return `<article class="amt-karte${a.meine ? " meine" : ""}">
    <div class="amt-kopf"><h3>${escape(a.name)}</h3>${verwalten
      ? `<button type="button" class="amt-edit" data-amt-edit="${a.id}">${edit ? "Fertig" : "Bearbeiten"}</button>` : ""}</div>
    <p class="amt-text">${a.beschreibung ? escape(a.beschreibung) : '<span class="amt-leer">Noch keine Beschreibung.</span>'}</p>
    <div class="amt-inhaber">${namen}</div>
    ${(a.rechte || []).length ? `<p class="amt-recht">Gibt das Recht: ${escape(a.rechte.join(", "))}</p>` : ""}
    ${a.hat_liste ? `<button type="button" class="amt-link" data-amt-liste="${a.id}">Liste ansehen ›</button>` : ""}
    ${editor}</article>`;
}
function renderAemter() {
  const el = $("#aemter-inhalt");
  const alle = aemterDaten.aemter;
  const meine = alle.filter((a) => a.meine);
  const rest = alle.filter((a) => !a.meine);
  const neu = aemterDaten.kann_verwalten
    ? `<details class="amt-neu"><summary>＋ Neues Amt</summary>
         <input id="amt-neu-name" type="text" maxlength="60" placeholder="Name, z. B. Zeugwart" />
         <textarea id="amt-neu-text" rows="2" maxlength="500" placeholder="Was macht das Amt?"></textarea>
         <button type="button" class="todo-knopf primaer" data-amt-neu>Amt anlegen</button>
       </details>` : "";
  el.innerHTML = neu
    + (meine.length ? `<h3 class="todo-titel">Deine Ämter</h3>${meine.map(amtKarte).join("")}` : "")
    + `<h3 class="todo-titel">${meine.length ? "Weitere Ämter" : "Alle Ämter"}</h3>${rest.map(amtKarte).join("")}`;
}
// Nach einer Änderung an den eigenen Ämtern holt die App sich /api/me neu (Profil-Menü, Rechte).
async function meNeuLaden() {
  try { setzeBenutzer(await api("/api/me")); } catch (_) {}
}
$("#aemter-inhalt").addEventListener("input", (e) => {
  const t = e.target.closest("[data-amt-text]");
  if (t) aemterEntwurf.set(Number(t.dataset.amtText), t.value);
});
$("#aemter-inhalt").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  const d = b.dataset;
  if (d.amtEdit) {
    const id = Number(d.amtEdit);
    if (aemterBearbeiten.has(id)) aemterBearbeiten.delete(id); else aemterBearbeiten.add(id);
    renderAemter();
    return;
  }
  if (d.amtListe) { listenOffen.add(Number(d.amtListe)); listenGesehen.add(Number(d.amtListe)); gehe(amtOber(), "listen"); return; }
  b.disabled = true;
  try {
    if (d.amtInhaber) {
      await api(`/api/aemter/${d.amtInhaber}/inhaber`, "POST", { spieler_id: Number(d.sp), da: d.an === "1" });
      if (Number(d.sp) === eigeneSpielerId()) meNeuLaden();
    } else if (d.amtSpeichern) {
      const id = Number(d.amtSpeichern);
      const text = aemterEntwurf.has(id) ? aemterEntwurf.get(id) : (aemterDaten.aemter.find((a) => a.id === id) || {}).beschreibung || "";
      await api(`/api/aemter/${id}/beschreibung`, "POST", { beschreibung: text });
      aemterEntwurf.delete(id);
      toast("Beschreibung gespeichert ✓");
    } else if (b.hasAttribute("data-amt-neu")) {
      const name = $("#amt-neu-name").value.trim();
      if (!name) { toast("Bitte einen Namen eintragen."); b.disabled = false; return; }
      await api("/api/aemter", "POST", { name, beschreibung: $("#amt-neu-text").value.trim() });
      toast("Amt angelegt ✓");
    } else { b.disabled = false; return; }
    aemterDaten = await api("/api/aemter");
    renderAemter();
  } catch (err) { toast("Fehler: " + amtFehler(err)); b.disabled = false; }
});
// ---- Listen --------------------------------------------------------------
export async function ladeListen() {
  const el = $("#listen-inhalt");
  if (!listenDaten.size) el.innerHTML = '<p class="hinweis">Lädt…</p>';
  try {
    aemterDaten = await api("/api/aemter");
    const mit = aemterDaten.aemter.filter((a) => a.hat_liste);
    const daten = await Promise.all(mit.map((a) => api(`/api/aemter/${a.id}/liste`)));
    mit.forEach((a, i) => {
      listenDaten.set(a.id, daten[i]);
      if (!listenGesehen.has(a.id)) {                  // Startzustand: aufgeklappt, wenn ich die Liste pflege
        listenGesehen.add(a.id);
        if (daten[i].darf_pflegen) listenOffen.add(a.id);
      }
    });
    renderListen();
  } catch (_) {
    if (!listenDaten.size) el.innerHTML = '<p class="hinweis">Die Listen konnten nicht geladen werden – dafür brauchst du eine Verbindung.</p>';
  }
}
function listenTermin(a, d, t) {
  const sid = eigeneSpielerId();
  const dt = datumTeile(t.datum);
  const darf = d.darf_pflegen;
  const fahrten = a.typ === "fahrten";
  const hat = new Set(t.zugeteilt.map((z) => z.spieler_id));
  const x = (id) => `<button type="button" class="chip-x" data-lt-weg="${id}" aria-label="Entfernen">×</button>`;
  const namen = t.zugeteilt.map((z) => {
    const ich = z.spieler_id === sid ? " ich" : "";
    if (fahrten || !darf) return `<span class="amt-chip${ich}">${!fahrten && z.erledigt ? "☑ " : ""}${escape(z.name)}${darf ? x(z.spieler_id) : ""}</span>`;
    return `<span class="amt-chip${ich}${z.erledigt ? " fertig" : ""}"><button type="button" class="chip-haken" data-lt-erledigt="${z.spieler_id}" data-an="${z.erledigt ? 0 : 1}" title="${z.erledigt ? "Wieder öffnen" : "Abhaken"}">${z.erledigt ? "☑" : "☐"} ${escape(z.name)}</button>${x(z.spieler_id)}</span>`;
  }).join("") || `<span class="amt-leer">${fahrten ? "niemand fährt selbst" : "noch niemand eingeteilt"}</span>`;
  const bussleText = t.status === "da" ? "Bussle da" : t.status === "nicht_da" ? "Bussle nicht da" : "Bussle: noch nicht geklärt";
  const bussle = !fahrten ? "" : darf
    ? `<div class="lt-bussle">
         <button type="button" class="${t.status === "da" ? "an" : ""}" data-lt-bussle="da">Bussle da</button>
         <button type="button" class="${t.status === "nicht_da" ? "an nein" : ""}" data-lt-bussle="nicht_da">Bussle nicht da</button>
       </div>`
    : `<div class="lt-bussle"><span class="amt-chip${t.status === "da" ? " an" : t.status === "nicht_da" ? " nein" : ""}">${bussleText}</span></div>`;
  const frage = fahrten ? "Wer fährt selbst?" : "Wer ist dran?";
  const wahl = !darf ? "" : `<div class="lt-wahl">
      <select aria-label="${frage}"><option value="">${frage}</option>${
        d.zaehler.filter((z) => !hat.has(z.spieler_id)).map((z) => `<option value="${z.spieler_id}">${escape(z.name)} (${z.anzahl}×)</option>`).join("")}</select>
      <button type="button" class="todo-knopf primaer" data-lt-zuteilen>${fahrten ? "Eintragen" : "Einteilen"}</button>
    </div>`;
  const wo = t.heim === 0 && t.abfahrt ? ` · Abfahrt ${escape(t.abfahrt)}` : "";
  return `<div class="liste-termin" data-training="${t.training_id}">
      <div class="lt-kopf"><b>${dt.wt} ${dt.tag}</b><span>${escape(t.titel || "")}${wo}</span></div>
      ${bussle}
      ${fahrten ? '<div class="amt-wahl-titel">Fährt selbst mit dem Auto</div>' : ""}
      <div class="amt-inhaber">${namen}</div>${wahl}</div>`;
}
function listenKarte(a) {
  const d = listenDaten.get(a.id);
  if (!d) return "";
  const sid = eigeneSpielerId();
  const heute = heuteIso();
  const kommend = d.termine.filter((t) => t.datum >= heute);
  const vorbei = d.termine.filter((t) => t.datum < heute).reverse();
  const dran = kommend.find((t) => t.zugeteilt.some((z) => z.spieler_id === sid));
  const dd = dran ? datumTeile(dran.datum) : null;
  const hinweis = dran ? `du: ${dd.wt} ${dd.tag}` : (d.darf_pflegen ? "du pflegst diese Liste" : "");
  const zaehler = d.zaehler.map((z) =>
    `<span class="amt-chip${z.spieler_id === sid ? " ich" : ""}" title="${z.offen ? z.offen + " noch nicht abgehakt" : ""}">${escape(z.name)} <b>${z.anzahl}×</b>${z.offen ? ' <i class="offen">●</i>' : ""}</span>`).join("");
  return `<details class="liste-karte" data-amt="${a.id}" ${listenOffen.has(a.id) ? "open" : ""}>
    <summary><span class="lk-name">${escape(a.name)}</span>${hinweis ? `<small>${escape(hinweis)}</small>` : ""}</summary>
    <p class="amt-text">${escape(a.beschreibung)}</p>
    <div class="amt-wahl-titel">Wie oft dran seit dem 1. Juli · wer am seltensten, steht vorne</div>
    <div class="amt-inhaber">${zaehler}</div>
    <h4 class="lk-titel">Kommende Termine</h4>
    ${kommend.length ? kommend.map((t) => listenTermin(a, d, t)).join("") : '<p class="hinweis">Keine Termine in den nächsten Wochen.</p>'}
    ${vorbei.length ? `<details class="lk-vorbei"><summary>Zuletzt (${vorbei.length})</summary>${vorbei.map((t) => listenTermin(a, d, t)).join("")}</details>` : ""}
  </details>`;
}
function renderListen() {
  const el = $("#listen-inhalt");
  const mit = aemterDaten.aemter.filter((a) => a.hat_liste);
  el.innerHTML = mit.length ? mit.map(listenKarte).join("") : '<p class="hinweis">Es gibt noch keine Listen.</p>';
}
// "toggle" sprudelt nicht nach oben, darum im Capture-Modus lauschen.
$("#listen-inhalt").addEventListener("toggle", (e) => {
  const k = e.target;
  if (!k.classList || !k.classList.contains("liste-karte")) return;
  const id = Number(k.dataset.amt);
  if (k.open) listenOffen.add(id); else listenOffen.delete(id);
}, true);
$("#listen-inhalt").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  const zeile = b && b.closest(".liste-termin");
  if (!b || b.disabled || !zeile) return;
  const amtId = Number(b.closest(".liste-karte").dataset.amt);
  const training_id = Number(zeile.dataset.training);
  const d = b.dataset;
  let pfad, body;
  if (d.ltZuteilen !== undefined) {
    const sp = zeile.querySelector("select").value;
    if (!sp) { toast("Bitte eine Spielerin auswählen."); return; }
    pfad = "zuteilung"; body = { training_id, spieler_id: Number(sp), da: true };
  } else if (d.ltWeg) {
    pfad = "zuteilung"; body = { training_id, spieler_id: Number(d.ltWeg), da: false };
  } else if (d.ltErledigt) {
    pfad = "erledigt"; body = { training_id, spieler_id: Number(d.ltErledigt), erledigt: d.an === "1" };
  } else if (d.ltBussle) {
    const jetzt = (listenDaten.get(amtId).termine.find((t) => t.training_id === training_id) || {}).status;
    pfad = "bussle"; body = { training_id, status: jetzt === d.ltBussle ? null : d.ltBussle };   // zweites Antippen nimmt es zurück
  } else return;
  b.disabled = true;
  try {
    await api(`/api/aemter/${amtId}/${pfad}`, "POST", body);
    listenDaten.set(amtId, await api(`/api/aemter/${amtId}/liste`));
    renderListen();
  } catch (err) { toast("Fehler: " + amtFehler(err)); b.disabled = false; }
});
// Home: "Du bist dran" mit den Aufgaben aus den Listen (nur Spielerinnen).
export async function renderHomeAemter() {
  const el = $("#home-aemter");
  if (!eigeneSpielerId() || aktRolle !== "spieler") { el.innerHTML = ""; return; }
  let liste = [];
  try { liste = (await api("/api/aemter/meine-aufgaben")).aufgaben; } catch (_) {}
  if (!liste.length) { el.innerHTML = ""; return; }
  const heute = heuteIso();
  const zeilen = liste.slice(0, 3).map((a) => {
    const dt = datumTeile(a.datum);
    const was = a.typ === "fahrten" ? "du fährst selbst mit dem Auto" : "du bist dran";
    const offen = a.typ === "zuteilung" && a.datum < heute && !a.erledigt ? " · noch offen" : "";
    return `<p class="ht-text"><b>${escape(a.amt)}</b> · ${was}<br><span class="ht-sub">${dt.wt} ${dt.tag} · ${escape(a.titel || "")}${offen}</span></p>`;
  }).join("");
  el.innerHTML = `<button type="button" class="ht-karte ziel"><div class="ht-kopf"><b>Du bist dran</b></div>${zeilen}</button>`;
  el.querySelector("button").addEventListener("click", () => gehe("mannschaft", "listen"));
}
