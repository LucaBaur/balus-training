import { api } from "../core/api.js";
import { aktRolle } from "../core/konto.js";
import { aktOber, aktUnter, gehe, zeigeView } from "../core/router.js";
import { $, escape, mdLite, toast } from "../core/ui.js";

// -------------------------------------------------------------- Wiki/Seiten --
//  Eine Ansicht für alle Freitext-Bereiche (Playbook/Gegner/Übungen/Statistik/
//  Saison/Notizen). `kat` ist eine Kategorie oder eine Liste von Kategorien.
//
//  BAUM: Seiten mit `parent_id` erscheinen eingerückt unter ihrer Gruppe, in
//  beliebiger Tiefe (Playbook: Spielzüge > Allgemeine Spielzüge > Jugo).
//  Reihenfolge kommt aus `sortierung`, bei Gleichstand alphabetisch.
//  Trainer können Seiten hier anlegen, bearbeiten und löschen.

const WIKI_MAX_TIEFE = 6;          // Reissleine gegen kaputte parent_id-Ketten
let aktWikiKats = [];              // Kategorien der aktuellen Liste
let aktWikiTitel = "";
let aktWikiSeiten = [];            // zuletzt geladene Liste (für das Anlege-Formular)
let aktSeite = null;               // aktuell geöffnete Wiki-Seite
// Zugeklappte Gruppen überleben den Neustart der App (sonst klappt jede
// Sitzung wieder alles auf).
const wikiZugeklappt = new Set((() => {
  try { return JSON.parse(localStorage.getItem("wikiZugeklappt") || "[]"); }
  catch (_) { return []; }
})());
function merkeZugeklappt() {
  try {
    localStorage.setItem("wikiZugeklappt", JSON.stringify([...wikiZugeklappt]));
  } catch (_) { /* privater Modus o. ä. — dann eben nur für diese Sitzung */ }
}
export async function ladeWiki(kat, titel) {
  aktWikiKats = Array.isArray(kat) ? kat.slice() : [kat];
  aktWikiTitel = titel || "Wiki";
  $("#wiki-titel").textContent = aktWikiTitel;
  renderWikiNeu();
  const el = $("#wiki-liste");
  el.innerHTML = '<p class="hinweis">Lädt…</p>';
  const teile = await Promise.all(aktWikiKats.map((k) =>
    Sync.apiOffline("/api/seiten?kategorie=" + encodeURIComponent(k)).catch(() => [])));
  aktWikiSeiten = teile.flat();
  renderWikiListe();
}
// Baum aus der flachen Liste: alles mit gültigem parent_id wird Kind, der Rest
// steht oben. Beide Ebenen sind nach `sortierung` sortiert.
function wikiBaum() {
  const vorhanden = new Set(aktWikiSeiten.map((s) => s.id));
  const kinder = new Map();
  const oben = [];
  for (const s of aktWikiSeiten) {
    if (s.parent_id && vorhanden.has(s.parent_id)) {
      if (!kinder.has(s.parent_id)) kinder.set(s.parent_id, []);
      kinder.get(s.parent_id).push(s);
    } else {
      oben.push(s);
    }
  }
  const sortiere = (a, b) => (a.sortierung || 0) - (b.sortierung || 0) ||
    (a.titel || "").localeCompare(b.titel || "", "de");
  oben.sort(sortiere);
  for (const liste of kinder.values()) liste.sort(sortiere);
  return { oben, kinder };
}
function renderWikiListe() {
  const el = $("#wiki-liste");
  if (!aktWikiSeiten.length) {
    el.innerHTML = '<p class="hinweis">Noch keine Einträge.</p>';
    return;
  }
  const { oben, kinder } = wikiBaum();
  el.innerHTML = "";
  for (const s of oben) el.appendChild(wikiKnoten(s, kinder, 0));
}
// Eine Seite samt allem, was unter ihr hängt: ohne Kinder eine Zeile, mit
// Kindern eine aufklappbare Gruppe.
function wikiKnoten(s, kinder, tiefe) {
  const ks = tiefe < WIKI_MAX_TIEFE ? (kinder.get(s.id) || []) : [];
  return ks.length ? wikiGruppe(s, ks, kinder, tiefe)
                   : wikiZeile(s, tiefe ? "kind" : "");
}
// Eine normale Seitenzeile. Leere Seiten sind für Spielerinnen nicht anklickbar,
// für Trainer schon (dort wird der Inhalt ja erst geschrieben).
function wikiZeile(s, extraKlasse) {
  const z = document.createElement("button");
  z.className = "wiki-zeile" + (s.hat_inhalt ? "" : " leer") +
    (extraKlasse ? " " + extraKlasse : "");
  z.innerHTML = `<span class="wz-titel">${escape(s.titel)}</span>` +
    (s.hat_inhalt ? '<span class="wz-pfeil">›</span>' : '<span class="wz-leer">leer</span>');
  if (s.hat_inhalt || aktRolle === "trainer") {
    z.addEventListener("click", () => oeffneSeite(s.id));
  }
  return z;
}
// Gruppenkopf + eingerückte Unterseiten. Der Kopf klappt auf/zu; das „›"
// daneben öffnet die Gruppenseite selbst (Text direkt an der Gruppe).
function wikiGruppe(g, ks, kinder, tiefe) {
  const zu = wikiZugeklappt.has(g.id);
  const box = document.createElement("div");
  box.className = "wiki-gruppe";

  const kinderBox = document.createElement("div");
  kinderBox.className = "wiki-kinder" + (zu ? " hidden" : "");
  for (const k of ks) kinderBox.appendChild(wikiKnoten(k, kinder, tiefe + 1));

  const kopf = document.createElement("div");
  kopf.className = "wiki-zeile gruppe" + (tiefe ? " kind" : "");
  const toggle = document.createElement("button");
  toggle.className = "wz-toggle";
  toggle.setAttribute("aria-expanded", zu ? "false" : "true");
  toggle.innerHTML = `<span class="wz-caret">${zu ? "▸" : "▾"}</span>` +
    `<span class="wz-titel">${escape(g.titel)}</span>` +
    `<span class="wz-anzahl">${ks.length}</span>`;
  toggle.addEventListener("click", () => {
    const jetztZu = !wikiZugeklappt.has(g.id);
    if (jetztZu) wikiZugeklappt.add(g.id); else wikiZugeklappt.delete(g.id);
    merkeZugeklappt();
    kinderBox.classList.toggle("hidden", jetztZu);
    toggle.setAttribute("aria-expanded", jetztZu ? "false" : "true");
    toggle.querySelector(".wz-caret").textContent = jetztZu ? "▸" : "▾";
  });
  kopf.appendChild(toggle);
  if (g.hat_inhalt || aktRolle === "trainer") {
    const auf = document.createElement("button");
    auf.className = "wz-open";
    auf.textContent = "›";
    auf.title = "Gruppenseite öffnen";
    auf.addEventListener("click", () => oeffneSeite(g.id));
    kopf.appendChild(auf);
  }

  box.appendChild(kopf);
  box.appendChild(kinderBox);
  return box;
}
// ------------------------------------------------- Seiten anlegen (Trainer) --
function renderWikiNeu() {
  const el = $("#wiki-neu");
  if (!el) return;
  el.innerHTML = "";
  if (aktRolle !== "trainer") return;
  const btn = document.createElement("button");
  btn.className = "wiki-neu-btn";
  btn.textContent = "＋ Neue Seite";
  btn.addEventListener("click", zeigeWikiNeuForm);
  el.appendChild(btn);
}
function zeigeWikiNeuForm() {
  const el = $("#wiki-neu");
  el.innerHTML = "";
  const form = document.createElement("div");
  form.className = "wiki-neu-form";

  const titel = document.createElement("input");
  titel.type = "text";
  titel.placeholder = "Titel der neuen Seite";

  // Ziel: oberste Ebene je Kategorie oder als Unterseite einer Seite dieser
  // Ebene. Der Wert kodiert beides: "kat:<kategorie>" oder "unter:<id>".
  const ziel = document.createElement("select");
  for (const k of aktWikiKats) {
    const o = document.createElement("option");
    o.value = "kat:" + k;
    o.textContent = aktWikiKats.length > 1 ? `Oberste Ebene (${k})` : "Oberste Ebene";
    ziel.appendChild(o);
  }
  // Jede Seite kann Gruppe werden; die Einrückung zeigt, wo sie im Baum hängt.
  const { oben, kinder } = wikiBaum();
  (function sammle(liste, tiefe) {
    for (const s of liste) {
      const o = document.createElement("option");
      o.value = "unter:" + s.id;
      o.textContent = "Unter " + "· ".repeat(tiefe) + "„" + s.titel + "“";
      ziel.appendChild(o);
      if (tiefe + 1 < WIKI_MAX_TIEFE) sammle(kinder.get(s.id) || [], tiefe + 1);
    }
  })(oben, 0);

  const leiste = document.createElement("div");
  leiste.className = "plan-edit-leiste";
  const anlegen = document.createElement("button");
  anlegen.className = "primaer";
  anlegen.textContent = "Anlegen";
  anlegen.addEventListener("click", () => {
    const [art, wert] = ziel.value.split(":");
    const parent = art === "unter" ? Number(wert) : null;
    const kategorie = art === "unter"
      ? (aktWikiSeiten.find((s) => s.id === parent) || {}).kategorie
      : wert;
    wikiSeiteAnlegen(titel.value, parent, kategorie);
  });
  const abbrechen = document.createElement("button");
  abbrechen.textContent = "Abbrechen";
  abbrechen.addEventListener("click", renderWikiNeu);
  leiste.appendChild(anlegen); leiste.appendChild(abbrechen);

  form.appendChild(titel); form.appendChild(ziel); form.appendChild(leiste);
  el.appendChild(form);
  titel.focus();
}
// Anlegen und Löschen brauchen die vom Server vergebene ID bzw. verändern die
// Struktur -> bewusst NICHT über die Outbox, sondern nur online.
async function wikiSeiteAnlegen(titel, parentId, kategorie) {
  titel = (titel || "").trim();
  if (!titel) { toast("Bitte einen Titel eingeben."); return; }
  if (!Sync.serverOnline) { toast("Neue Seiten gehen nur online."); return; }
  try {
    const r = await api("/api/seiten", "POST",
                        { titel, kategorie, parent_id: parentId });
    await Sync.frischHolen("/api/seiten?kategorie=" + encodeURIComponent(kategorie));
    await ladeWiki(aktWikiKats, aktWikiTitel);
    toast("Seite angelegt ✓");
    if (r && r.id) oeffneSeite(r.id);
  } catch (e) { toast("Fehler: " + e.message); }
}
// ------------------------------------------------------------ Seiten-Detail --
async function oeffneSeite(id) {
  let s = null;
  try { s = await Sync.apiOffline("/api/seiten/" + id); } catch (_) {}
  if (!s) { toast("Seite nicht verfügbar (einmal online öffnen)."); return; }
  aktSeite = s;
  renderSeite();
  zeigeView("view-wiki-detail");
}
function renderSeite() {
  const s = aktSeite;
  $("#wd-titel").textContent = s.titel;
  $("#wd-body").innerHTML = s.markdown ? mdLite(s.markdown)
    : '<p class="hinweis">Diese Seite ist leer.</p>';
  const akt = $("#wd-aktionen");
  akt.innerHTML = "";
  if (aktRolle !== "trainer") return;
  const bearbeiten = document.createElement("button");
  bearbeiten.className = "plan-edit-btn";
  bearbeiten.textContent = s.markdown ? "✏️ Bearbeiten" : "✏️ Inhalt hinzufügen";
  bearbeiten.addEventListener("click", startSeiteEdit);
  const loeschen = document.createElement("button");
  loeschen.className = "plan-edit-btn gefahr";
  loeschen.textContent = s.kategorie === "playbook" ? "🗄 Archivieren" : "🗑 Löschen";   // Spielzuege werden nur archiviert
  loeschen.addEventListener("click", loescheSeite);
  akt.appendChild(bearbeiten); akt.appendChild(loeschen);
}
function startSeiteEdit() {
  const s = aktSeite;
  $("#wd-body").innerHTML = "";
  const box = $("#wd-aktionen");
  box.innerHTML = "";
  const titel = document.createElement("input");
  titel.type = "text";
  titel.className = "wd-titel-editor";
  titel.value = s.titel;
  titel.placeholder = "Titel";
  const ta = document.createElement("textarea");
  ta.className = "plan-editor";
  ta.rows = 16;
  ta.value = s.markdown || "";
  ta.placeholder = "Inhalt (Markdown: ## Überschrift, - Liste, **fett**) …";
  const leiste = document.createElement("div");
  leiste.className = "plan-edit-leiste";
  const speichern = document.createElement("button");
  speichern.className = "primaer";
  speichern.textContent = "Speichern";
  speichern.addEventListener("click", () => speichereSeite(titel.value, ta.value));
  const abbrechen = document.createElement("button");
  abbrechen.textContent = "Abbrechen";
  abbrechen.addEventListener("click", renderSeite);
  leiste.appendChild(speichern); leiste.appendChild(abbrechen);
  box.appendChild(titel); box.appendChild(ta); box.appendChild(leiste);
  ta.focus();
}
async function speichereSeite(titel, markdown) {
  titel = (titel || "").trim();
  if (!titel) { toast("Der Titel darf nicht leer sein."); return; }
  const s = aktSeite;
  try {
    // Wie beim Trainingsplan über die Outbox: online sofort, offline gepuffert.
    const r = await Sync.senden("/api/seiten/" + s.id, { titel, markdown });
    s.titel = titel; s.markdown = markdown;   // optimistisch lokal
    await patchSeiteCache(s);
    renderSeite();
    toast(r.gesendet ? "Seite gespeichert ✓"
      : "Offline gespeichert – wird im WLAN synchronisiert.");
  } catch (e) { toast("Fehler: " + e.message); }
}
// Den gespiegelten GET-Cache mitziehen (Detail + Titel/„leer" in der Liste).
async function patchSeiteCache(s) {
  try {
    await LocalDB.put("responses", { pfad: "/api/seiten/" + s.id, daten: s, ts: Date.now() });
    const pfad = "/api/seiten?kategorie=" + encodeURIComponent(s.kategorie);
    const liste = await LocalDB.get("responses", pfad);
    if (liste && Array.isArray(liste.daten)) {
      const e = liste.daten.find((x) => x.id === s.id);
      if (e) {
        e.titel = s.titel;
        e.hat_inhalt = (s.markdown && s.markdown.trim()) ? 1 : 0;
        await LocalDB.put("responses", { pfad, daten: liste.daten, ts: Date.now() });
      }
    }
  } catch (_) { /* Cache-Patch ist best-effort */ }
}
async function loescheSeite() {
  const s = aktSeite;
  const archiv = s.kategorie === "playbook";      // Spielzug: Name bleibt, Text und Ansicht werden entfernt
  const frage = archiv
    ? `„${s.titel}“ archivieren? Text und Ansicht werden entfernt, der Name bleibt (alte Spiele zeigen den `
      + "Spielzug weiter an). Unterseiten bleiben erhalten."
    : `„${s.titel}“ wirklich löschen? Unterseiten bleiben erhalten.`;
  if (!confirm(frage)) return;
  if (!Sync.serverOnline) { toast((archiv ? "Archivieren" : "Löschen") + " geht nur online."); return; }
  try {
    await api("/api/seiten/" + s.id + "/loeschen", "POST", {});
    try { await LocalDB.loesche("responses", "/api/seiten/" + s.id); } catch (_) {}
    await Sync.frischHolen("/api/seiten?kategorie=" + encodeURIComponent(s.kategorie));
    toast(archiv ? "Spielzug archiviert ✓" : "Seite gelöscht ✓");
    gehe(aktOber, aktUnter);
  } catch (e) { toast("Fehler: " + e.message); }
}
$("#btn-wiki-zurueck").addEventListener("click", () => gehe(aktOber, aktUnter));
