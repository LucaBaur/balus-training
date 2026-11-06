import { api } from "../core/api.js";
import { eigeneSpielerId } from "../core/konto.js";
import { $, datumKurz, escape, heuteIso, toast } from "../core/ui.js";

// ================================================================== Kasse ====
//  Mannschaftskasse (daten/kasse.py, routen/kasse.py). Der Server entscheidet, was jede sieht:
//  den Kassenstand alle, Posten einer Spielerin nur sie selbst, alles die Kassenwartin und der Trainer.
//  Hier wird nur gezeigt. Gerechnet und formatiert wird in kasse-logik.js (KasseLogik, ganze Cent).
//  Buchen geht nur online, wie bei den Ämtern: Geld soll nicht „später irgendwann“ gebucht werden.
let kasseDaten = null;                       // Antwort von /api/kasse
let entwurf = leererEntwurf();               // Eingabe im Formular; bleibt beim Neuzeichnen erhalten
let sendetGerade = false;
let formOffen = false;                       // Formular aufgeklappt? Gemerkt, weil jedes Neuzeichnen es sonst zuklappt

function leererEntwurf() {
  return { art: "forderung", spieler: "", betrag: "", text: "", datum: "", token: "",
           katalog: "", anzahl: "1", trainer: false };
}
// Ein Token pro Eingabe: scheitert das Absenden (Funkloch), schickt der zweite Versuch dasselbe Token,
// und der Server legt die Buchung nicht doppelt an (Idempotenz). Erst nach Erfolg gibt es ein neues.
function neuesToken() {
  return (crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : "k-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}
const fehlerText = (e) => {
  try { return JSON.parse(e.message).detail || e.message; } catch (_) { return e.message; }
};
const art = (key) => KasseLogik.ARTEN.find((a) => a.key === key);

export async function ladeKasse() {
  const el = $("#kasse-inhalt");
  if (!kasseDaten) el.innerHTML = '<p class="hinweis">Lädt…</p>';
  try {
    kasseDaten = await api("/api/kasse");
    renderKasse();
  } catch (_) {
    if (!kasseDaten) el.innerHTML = '<p class="hinweis">Die Kasse konnte nicht geladen werden – dafür brauchst du eine Verbindung.</p>';
  }
}

function kopfKarte(d) {
  const s = d.stand;
  const mein = d.mein_offen_cent;
  const sid = eigeneSpielerId();
  let meinZeile = "";
  if (sid && mein !== null) {
    meinZeile = mein > 0
      ? `<p class="kasse-mein schuld">Du schuldest der Kasse <b>${KasseLogik.euro(mein)}</b>.</p>`
      : mein < 0
        ? `<p class="kasse-mein">Du hast <b>${KasseLogik.euro(-mein)}</b> Guthaben in der Kasse.</p>`
        : '<p class="kasse-mein">Bei dir ist alles bezahlt ✓</p>';
  }
  const offen = s.offen_cent !== null && s.offen_cent > 0
    ? ` · noch offen ${KasseLogik.euro(s.offen_cent)}` : "";
  return `<article class="amt-karte kasse-stand">
    <span class="kasse-label">Kassenstand</span>
    <b class="kasse-zahl${s.kasse_cent < 0 ? " minus" : ""}">${KasseLogik.euro(s.kasse_cent)}</b>
    <small class="kasse-klein">Eingenommen ${KasseLogik.euro(s.einnahmen_cent)} · ausgegeben ${KasseLogik.euro(s.ausgaben_cent)}${offen}</small>
    ${meinZeile}</article>`;
}

const katalogPosten = () => (kasseDaten.katalog || []).find((k) => k.key === entwurf.katalog);

// Katalogwahl fuellt Text und Betrag vor (Kasten-Posten: Betrag bleibt leer, den traegt die Kassenwartin ein).
// Danach ist alles normal editierbar; das ist nur eine Eingabehilfe, der Server prueft die Buchung wie immer.
function katalogUebernehmen() {
  const p = katalogPosten();
  if (!p) return;
  const cent = KasseLogik.katalogBetrag(p, entwurf.anzahl, entwurf.trainer);
  entwurf.text = KasseLogik.katalogText(p, entwurf.anzahl, entwurf.trainer);
  entwurf.betrag = cent === null ? "" : (cent / 100).toFixed(2).replace(".", ",");
  entwurf.token = "";
}

function katalogFeld() {
  const p = katalogPosten();
  const posten = kasseDaten.katalog || [];
  const wahl = `<label>Aus dem Strafenkatalog<select data-k="katalog"><option value="">– frei eingeben –</option>${posten.map((k) =>
    `<option value="${k.key}"${k.key === entwurf.katalog ? " selected" : ""}>${escape(k.label)} · ${k.cent === null ? "Kasten" : KasseLogik.euro(k.cent) + (k.einheit ? " je " + k.einheit : "")}</option>`).join("")}</select></label>`;
  const anzahl = p && p.einheit
    ? `<label>Anzahl (${escape(p.einheit)})<input data-k="anzahl" type="number" min="1" step="1" inputmode="numeric" value="${escape(entwurf.anzahl)}" /></label>` : "";
  const trainer = p ? `<label class="kasse-check"><input data-k="trainer" type="checkbox"${entwurf.trainer ? " checked" : ""} /> Trainer (alle Strafen ×2)</label>` : "";
  const kasten = p && p.cent === null ? '<p class="kasse-hinweis">Kasten = ½ Radler, ¼ Bier, ¼ Antialk. Den Betrag trägst du selbst ein.</p>' : "";
  return wahl + anzahl + trainer + kasten;
}

function formular(d) {
  const a = art(entwurf.art);
  const spielerWahl = a.spielerin
    ? `<label>Spielerin<select data-k="spieler"><option value="">– auswählen –</option>${d.kader.map((k) =>
        `<option value="${k.id}"${String(k.id) === String(entwurf.spieler) ? " selected" : ""}>${escape(k.name)}</option>`).join("")}</select></label>`
    : "";
  return `<details class="amt-neu kasse-neu"${formOffen ? " open" : ""}><summary>＋ Neue Buchung</summary>
    <label>Was ist passiert?<select data-k="art">${KasseLogik.ARTEN.map((x) =>
      `<option value="${x.key}"${x.key === entwurf.art ? " selected" : ""}>${escape(x.label)}</option>`).join("")}</select></label>
    <p class="kasse-hinweis">${escape(a.hinweis)}</p>
    ${spielerWahl}
    ${entwurf.art === "forderung" ? katalogFeld() : ""}
    <label>Betrag in Euro<input data-k="betrag" type="text" inputmode="decimal" placeholder="z. B. 5,00" value="${escape(entwurf.betrag)}" /></label>
    <label>Wofür?<input data-k="text" type="text" maxlength="120" placeholder="z. B. Zu spät zum Training" value="${escape(entwurf.text)}" /></label>
    <label>Datum<input data-k="datum" type="date" value="${escape(entwurf.datum || heuteIso())}" /></label>
    <button type="button" class="todo-knopf primaer" data-kasse-buchen>Buchen</button>
  </details>`;
}

// Die offenen Strafen sehen alle (Name und Betrag); der Server liefert Spielerinnen nur echte Schulden.
// „Zahlung eintragen“ gibt es nur für die, die buchen dürfen.
function offenListe(d, darf) {
  const sid = eigeneSpielerId();
  const mit = d.offen.filter((o) => o.offen_cent !== 0);
  if (!mit.length) return '<p class="hinweis">Niemand schuldet der Kasse etwas.</p>';
  return `<div class="kasse-liste">${mit.map((o) => `<div class="kasse-zeile">
      <span class="kasse-text"><b>${escape(o.name)}${o.spieler_id === sid ? " (du)" : ""}</b><small>${KasseLogik.offenText(o.offen_cent)}</small></span>
      ${darf && o.offen_cent > 0 ? `<button type="button" class="amt-edit" data-kasse-zahlt="${o.spieler_id}" data-cent="${o.offen_cent}">Zahlung eintragen</button>` : ""}
    </div>`).join("")}</div>`;
}

function buchungZeile(b, darf) {
  const plus = b.art === "einzahlung" || b.art === "einnahme";
  const vorzeichen = b.art === "forderung" ? "" : plus ? "+" : "−";
  const klasse = b.art === "forderung" ? "forderung" : plus ? "plus" : "minus";
  const wer = b.spieler_name ? ` · ${escape(b.spieler_name)}` : "";
  return `<div class="kasse-zeile${b.storniert ? " storniert" : ""}">
    <span class="kasse-text"><b>${escape(b.text)}</b>
      <small>${datumKurz(b.datum)} · ${escape(art(b.art).label)}${wer}${b.storniert ? " · storniert" : ""}</small></span>
    <span class="kasse-betrag ${klasse}">${vorzeichen}${KasseLogik.euro(b.betrag_cent)}</span>
    ${darf && !b.storniert ? `<button type="button" class="amt-edit" data-kasse-storno="${b.id}" aria-label="Buchung stornieren">Stornieren</button>` : ""}
  </div>`;
}

// Die Spielregeln zur Kasse (aus dem Strafenkatalog), fuer alle lesbar.
const REGELN = `<details class="kasse-regeln"><summary>Regeln zur Kasse</summary><ul>
  <li>Für Trainer gelten alle Strafen ×2.</li>
  <li>Strafen werden über SpielerPlus zugeteilt. Die Kassenwarte tragen sie innerhalb einer Woche ein, sonst gilt das für sie als „Amt vergessen“.</li>
  <li>Eine Strafe, die nicht innerhalb einer Woche bezahlt ist, kostet zusätzlich 1 € Zins pro Tag.</li>
  <li>Das Geld der Mannschaftskasse wird für Dienste, Ämter und Mannschaftsevents genutzt.</li>
  <li>Strafen sind anfechtbar: Die Spielerin sagt etwas vor der ganzen Mannschaft, dann wird demokratisch abgestimmt. Stimmt die Mannschaft zu, verdoppelt sich die Strafe, sonst verfällt sie.</li>
  <li>Kasten = ½ Radler, ¼ Bier, ¼ Antialk.</li></ul></details>`;

// Der Strafenkatalog zum Nachlesen: Posten und Preise sehen alle, nicht nur die Buchenden.
function katalogAnzeige(d) {
  const posten = d.katalog || [];
  if (!posten.length) return "";
  return `<details class="kasse-regeln kasse-katalog"><summary>Strafenkatalog</summary><div class="kasse-liste">${posten.map((k) => `<div class="kasse-zeile">
    <span class="kasse-text"><b>${escape(k.label)}</b></span>
    <span class="kasse-betrag">${k.cent === null ? "Kasten" : KasseLogik.euro(k.cent) + (k.einheit ? " je " + escape(k.einheit) : "")}</span></div>`).join("")}</div>
    <p class="kasse-hinweis">Für Trainer gilt alles ×2.</p></details>`;
}

function renderKasse() {
  // Den Zustand „aufgeklappt“ vor dem Neuzeichnen aus dem DOM lesen, nicht aus einem Ereignis: das
  // „toggle“-Ereignis kommt asynchron und ein früheres Neuzeichnen würde noch den alten Wert sehen.
  const altesFormular = $("#kasse-inhalt .kasse-neu");
  if (altesFormular) formOffen = altesFormular.open;
  const d = kasseDaten;
  const darf = d.darf_buchen;
  const liste = d.buchungen.length
    ? `<div class="kasse-liste">${d.buchungen.map((b) => buchungZeile(b, darf)).join("")}</div>`
    : '<p class="hinweis">Noch keine Buchungen.</p>';
  $("#kasse-inhalt").innerHTML = kopfKarte(d)
    + (darf ? formular(d) : "")
    + '<h3 class="todo-titel">Offene Strafen – wer schuldet wie viel?</h3>' + offenListe(d, darf)
    + `<h3 class="todo-titel">${darf ? "Alle Buchungen" : "Deine Buchungen und die der Kasse"}</h3>` + liste
    + katalogAnzeige(d) + REGELN
    + (darf ? '<p class="hinweis">Gebucht wird nie gelöscht: Eine falsche Buchung wird storniert und bleibt zur Kontrolle sichtbar.</p>' : "");
}

// Nach dem Neuzeichnen den Cursor zurueck ins Feld legen (Anzahl wird beim Tippen neu gerechnet).
function refokus(k) {
  const f = $(`#kasse-inhalt [data-k="${k}"]`);
  if (f) { f.focus(); const n = f.value.length; try { f.setSelectionRange(n, n); } catch (_) { /* number-Felder kennen das nicht */ } }
}

// Eingaben merken, ohne neu zu zeichnen (sonst springt der Cursor).
// Jede Änderung der Eingabe verwirft das Token: es gilt nur für eine unveränderte Wiederholung
// (Funkloch beim Absenden), nicht für eine geänderte Buchung.
$("#kasse-inhalt").addEventListener("input", (e) => {
  const k = e.target.dataset && e.target.dataset.k;
  if (k === "anzahl") { entwurf.anzahl = e.target.value; katalogUebernehmen(); renderKasse(); refokus(k); return; }
  if (k && k !== "art" && k !== "katalog" && k !== "trainer") { entwurf[k] = e.target.value; entwurf.token = ""; }
});
// Die Art ändert, welche Felder da sind (Spielerin ja/nein): hier wird neu gezeichnet.
$("#kasse-inhalt").addEventListener("change", (e) => {
  const k = e.target.dataset && e.target.dataset.k;
  if (!k) return;
  entwurf[k] = k === "trainer" ? e.target.checked : e.target.value;
  entwurf.token = "";
  if (k === "art") { entwurf.katalog = ""; renderKasse(); }
  if (k === "katalog") { entwurf.anzahl = "1"; katalogUebernehmen(); renderKasse(); }
  if (k === "trainer") { katalogUebernehmen(); renderKasse(); }
});
$("#kasse-inhalt").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b || b.disabled) return;
  const d = b.dataset;
  if (d.kasseZahlt) {                                    // „Zahlung eintragen“: Formular mit dem offenen Betrag vorbelegen
    entwurf = { ...leererEntwurf(), art: "einzahlung", spieler: d.kasseZahlt,
                betrag: (Number(d.cent) / 100).toFixed(2).replace(".", ","), text: "Einzahlung" };
    const altes = $("#kasse-inhalt .kasse-neu");
    if (altes) altes.open = true;                        // renderKasse übernimmt den Zustand aus dem DOM
    formOffen = true;
    renderKasse();
    const f = $("#kasse-inhalt .kasse-neu");
    if (f) f.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (d.kasseStorno) {
    if (!confirm("Diese Buchung stornieren? Sie bleibt sichtbar, zählt aber nicht mehr.")) return;
    b.disabled = true;
    try {
      await api(`/api/kasse/buchung/${d.kasseStorno}/storno`, "POST");
      toast("Storniert ✓");
      kasseDaten = await api("/api/kasse");
      renderKasse();
    } catch (err) { toast("Fehler: " + fehlerText(err)); b.disabled = false; }
    return;
  }
  if (b.hasAttribute("data-kasse-buchen")) await buchen(b);
});

async function buchen(knopf) {
  if (sendetGerade) return;
  const a = art(entwurf.art);
  const cent = KasseLogik.parseEuro(entwurf.betrag);
  if (cent === null) { toast("Bitte einen Betrag wie 5,00 eintragen (höchstens 10.000 €)."); return; }
  if (a.spielerin && !entwurf.spieler) { toast("Bitte eine Spielerin auswählen."); return; }
  if (!entwurf.text.trim()) { toast("Bitte eintragen, wofür die Buchung ist."); return; }
  if (!entwurf.token) entwurf.token = neuesToken();
  sendetGerade = true;
  knopf.disabled = true;
  try {
    await api("/api/kasse/buchung", "POST", {
      art: a.key, betrag_cent: cent, text: entwurf.text.trim(),
      spieler_id: a.spielerin ? Number(entwurf.spieler) : null,
      datum: entwurf.datum || heuteIso(), token: entwurf.token,
    });
    toast("Gebucht ✓");
    const behalte = { art: entwurf.art, spieler: "" };       // gleiche Art bleibt: mehrere Strafen hintereinander
    entwurf = { ...leererEntwurf(), ...behalte };
    kasseDaten = await api("/api/kasse");
    renderKasse();
  } catch (err) {
    toast("Fehler: " + fehlerText(err));                    // Token bleibt: ein zweiter Versuch bucht nicht doppelt
    knopf.disabled = false;
  } finally {
    sendetGerade = false;
  }
}
