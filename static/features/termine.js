import { hatRecht } from "./aemter.js";
import { api } from "../core/api.js";
import { ladeHome } from "./home.js";
import { aktBenutzer, aktRolle } from "../core/konto.js";
import { renderNachbereitung } from "./nachbereitung.js";
import { renderTrainingPlan } from "./plan.js";
import { zeigeView } from "../core/router.js";
import { $, anhaengen, datumKurz, datumTeile, escape, toast } from "../core/ui.js";

export let aktTraining = null;        // aktuell geöffnetes Training (Detail/Plan-Editor)
// Trainer: Push-Erinnerung an alle senden, die noch nicht geantwortet haben.
function renderErinnern(d) {
  const el = document.getElementById("td-erinnern");
  if (!el) return;
  if (aktRolle !== "trainer") { el.innerHTML = ""; return; }
  el.innerHTML = '<button id="btn-erinnern">🔔 Erinnerung an Offene senden</button>' +
    (istSpiel(d) ? "" : ' <button id="btn-spabgleich">⟳ Aus SpielerPlus aktualisieren</button>');
  const sp = document.getElementById("btn-spabgleich");
  if (sp) sp.addEventListener("click", async () => {
    sp.disabled = true;
    try {
      const r = await api("/api/spielerplus-abgleich", "POST");
      toast(r.text);
      await Sync.frischHolen("/api/trainings/" + d.id).catch(() => {});
      Sync.frischHolen("/api/trainings").catch(() => {});
      Sync.frischHolen("/api/naechstes-training").catch(() => {});
      oeffneTraining(d.id);
    } catch (e) { toast("Fehler: " + e.message); }
    finally { sp.disabled = false; }
  });
  document.getElementById("btn-erinnern").addEventListener("click", async () => {
    const b = document.getElementById("btn-erinnern");
    b.disabled = true;
    try {
      const r = await api("/api/trainings/" + d.id + "/erinnern", "POST");
      toast(r.offen
        ? `Erinnerung an ${r.offen} Spielerin(nen) – ${r.gesendet} Gerät(e) erreicht.`
        : "Alle haben schon geantwortet.");
    } catch (e) { toast("Fehler: " + e.message); }
    finally { b.disabled = false; }
  });
}
// ==================================================== Termine-Uebersicht =====
//  Wer kann wann? Die Liste zeigt die Zusagen schon in der Zeile, damit man
//  eine duenne Einheit sieht, BEVOR man in der Halle steht. Antippen klappt
//  die Namen auf; die Namen kommen aus /api/trainings/{id} und werden gemerkt.

const offeneTermine = new Set();     // aufgeklappte Termine (id)
export const terminDetails = new Map();     // id -> Detail mit Namen (einmal geladen)
// Traegt die Einheit? Absolute Zahlen, weil Handball Koerper braucht: unter
// sechs Zusagen laesst sich kaum sinnvoll trainieren.
// Spielerinnen sehen nie eine Warnung, und freiwillige Trainings (Freitag, siehe db.FREIWILLIGE_WOCHENTAGE)
// brauchen keine: dort ist es in Ordnung, wenn nur wenige kommen.
function terminStufe(t) {
  if (t.freiwillig || aktRolle !== "trainer") return "ok";
  const zu = t.anwesend || 0;
  if (zu <= 5) return "kritisch";
  if (zu <= 8) return "knapp";
  return "ok";
}
export async function ladeTrainingsListe() {
  $("#trainings-titel").textContent = aktRolle === "spieler" ? "Meine Termine" : "Termine";
  renderTrainingNeu();
  const el = $("#trainings-liste");
  const warn = $("#trainings-warnung");
  if (warn) warn.innerHTML = "";
  el.innerHTML = '<p class="hinweis">Lädt…</p>';
  let liste = [];
  try { liste = await Sync.apiOffline("/api/trainings"); } catch (_) {
    el.innerHTML = '<p class="hinweis">Termine noch nicht verfügbar (einmal online öffnen).</p>';
    return;
  }
  if (!liste.length) { el.innerHTML = '<p class="hinweis">Noch kein Termin eingetragen.</p>'; return; }

  const heute = new Date().toISOString().slice(0, 10);
  const kommend = liste.filter((t) => (t.datum || "") >= heute)
                       .sort((a, b) => (a.datum || "").localeCompare(b.datum || ""));
  const vorbei = liste.filter((t) => (t.datum || "") < heute);   // API liefert absteigend

  el.innerHTML = "";
  if (kommend.length) {
    el.appendChild(gruppenKopf("Kommende Termine"));
    kommend.forEach((t) => el.appendChild(terminKarte(t, false)));
  }
  if (vorbei.length) {
    el.appendChild(gruppenKopf("Vergangen"));
    vorbei.slice(0, 8).forEach((t) => el.appendChild(terminKarte(t, true)));
  }
  renderTerminWarnung(kommend);
}
function gruppenKopf(text) {
  const d = document.createElement("div");
  d.className = "termin-gruppe";
  d.textContent = text;
  return d;
}
// Fruehwarnung: die naechste Einheit, bei der es nicht reicht.
function renderTerminWarnung(kommend) {
  const el = $("#trainings-warnung");
  if (!el) return;
  const duenn = kommend.filter((t) => terminStufe(t) === "kritisch");
  if (!duenn.length) { el.innerHTML = ""; return; }
  const t = duenn[0], d = datumTeile(t.datum);
  const weitere = duenn.length - 1;
  const zusatz = weitere === 0 ? ""
    : weitere === 1 ? ", und eine weitere Einheit ist ähnlich dünn"
    : `, und ${weitere} weitere Einheiten sind ähnlich dünn`;
  el.innerHTML =
    `<div class="termin-warnung"><span class="wz">⚠</span><div>
       <b>${d.wt} ${d.tag}: nur ${t.anwesend || 0} Zusagen</b>
       <p>${escape(t.titel || "Training")} — ${t.abgesagt || 0} abgesagt${zusatz}.
          Früh genug, um zu verschieben, zusammenzulegen oder abzusagen.</p>
     </div></div>`;
}
// Art eines Termins - Altbestand ohne Feld ist ein Training.
export const terminArt = (t) => (t && t.art) || "training";
export const istSpiel = (t) => terminArt(t) !== "training";
export const ART_WORT = { training: "Training", testspiel: "Testspiel", ligaspiel: "Ligaspiel" };
// Zeitzeile eines Spiels: bei Auswaerts steht die Abfahrt vorne - das ist die
// Uhrzeit, nach der sich alle richten muessen.
function spielZeiten(t) {
  const teile = [];
  if (t.heim === 0 && t.abfahrt) teile.push(`<span class="nw">Abfahrt ${escape(t.abfahrt)}</span>`);
  if (t.uhrzeit) teile.push(`<span class="nw">Anwurf ${escape(t.uhrzeit)}</span>`);
  return teile.join(" · ");
}
function terminKarte(t, vergangen) {
  const d = datumTeile(t.datum);
  const stufe = vergangen ? "ok" : terminStufe(t);
  const zu = t.anwesend || 0, ab = t.abgesagt || 0;
  const kader = t.kader || Math.max(zu + ab, 1);
  const auf = offeneTermine.has(t.id);

  const art = document.createElement("article");
  art.className = "termin " + terminArt(t)
    + (vergangen ? " vergangen" : (stufe === "ok" ? "" : " " + stufe))
    + (auf ? " auf" : "");

  const meinChip = t.meine_status === "anwesend" ? '<span class="t-meine ja">DABEI</span>'
    : t.meine_status === "abgesagt" ? '<span class="t-meine nein">ABGESAGT</span>'
    : t.meine_status === "unsicher" ? '<span class="t-meine un">UNSICHER</span>' : "";

  const kopf = document.createElement("button");
  kopf.className = "t-kopf";
  kopf.setAttribute("aria-expanded", auf ? "true" : "false");
  const spiel = istSpiel(t);
  const artChip = spiel
    ? `<span class="t-art ${terminArt(t)}">${ART_WORT[terminArt(t)]}` +
      `${t.heim === 0 ? " · auswärts" : t.heim === 1 ? " · daheim" : ""}</span>`
    : (t.freiwillig ? '<span class="t-art freiwillig">freiwillig</span>' : "");
  const zeitText = spiel ? (spielZeiten(t) || "ohne Uhrzeit")
                         : (t.uhrzeit ? escape(t.uhrzeit) : "ohne Uhrzeit");
  kopf.innerHTML =
    `<span class="t-datum"><b>${d.wt}</b><span>${escape(d.tag)}</span></span>
     <span class="t-mitte"><b>${escape(t.titel || "Training")}</b>${artChip}
       <small>${zeitText}${t.ort ? " · " + escape(t.ort) : ""}` +
      `${t.hat_nachbereitung && aktRolle === "trainer"
          ? '<span class="t-planchip" title="Nachbereitung vorhanden">📝</span>' : ""}` +
      `${t.hat_plan && aktRolle === "trainer"
          ? `<span class="t-planchip">PLAN${t.plan_minuten ? " " + t.plan_minuten + "′" : ""}</span>` : ""}${meinChip}</small>
       <span class="t-bar"><i class="zu" style="width:${(zu / kader) * 100}%"></i>` +
      `<i class="ab" style="width:${(ab / kader) * 100}%"></i></span></span>
     <span class="t-zahl"><b>${zu}</b><small>${stufe === "kritisch" ? "zu wenig" : "Zusagen"}</small></span>`;
  kopf.addEventListener("click", () => {
    if (auf) offeneTermine.delete(t.id); else offeneTermine.add(t.id);
    ladeTrainingsListe();
  });
  art.appendChild(kopf);

  const det = document.createElement("div");
  det.className = "t-detail";
  det.innerHTML = '<p class="t-laedt">Namen werden geladen…</p>';
  art.appendChild(det);
  if (auf) fuelleTerminDetail(det, t);
  return art;
}
async function fuelleTerminDetail(det, t) {
  let d = terminDetails.get(t.id);
  if (!d) {
    try {
      d = await Sync.apiOffline("/api/trainings/" + t.id);
      terminDetails.set(t.id, d);
    } catch (_) {
      det.innerHTML = '<p class="t-laedt">Die Namen gibt es, sobald du einmal online warst.</p>';
      return;
    }
  }
  det.innerHTML = "";
  if (aktBenutzer && aktBenutzer.spieler_id) {
    const box = document.createElement("div");
    box.className = "td-rsvp";
    rsvpFuellen(box, d);
    det.appendChild(box);
  }

  teilnahmeGruppen(det, d);

  if (aktRolle === "trainer" || hatRecht("termine")) det.appendChild(terminAktionen(t));
}
// Wer noch gar nicht geantwortet hat. Der Server liefert dafuer den ganzen
// Kader (Spielerinnen ohne Antwort mit status = null).
function offeneAntworten(teil) {
  return (teil || []).filter((x) => !x.status || x.status === "nominiert");
}
// Die vier Gruppen eines Termins - an ZWEI Stellen gleich (aufgeklappte Zeile
// in der Uebersicht und Termin-Detail), deshalb eine Funktion.
function teilnahmeGruppen(ziel, d) {
  const teil = d.teilnahme || [];
  const grp = (s) => teil.filter((x) => x.status === s);
  anhaengen(ziel, namensGruppe("Zugesagt", "zu", grp("anwesend"), d, false));
  anhaengen(ziel, namensGruppe("Unsicher", "un", grp("unsicher"), d, false));
  anhaengen(ziel, namensGruppe("Abgesagt", "ab", grp("abgesagt"), d, true));
  anhaengen(ziel, namensGruppe("Noch keine Rückmeldung", "offen",
    offeneAntworten(teil), d, false));
}
// Eine Gruppe. Fuer Spielerinnen zum Lesen (Chips bzw. Liste mit Grund),
// fuer Trainer eine Zeile je Name MIT Knoepfen - so laesst sich direkt
// eintragen, wer am Telefon zu- oder abgesagt hat.
function namensGruppe(titel, kl, arr, d, mitGrund) {
  if (!arr.length) return null;
  const g = document.createElement("div");
  g.className = "t-gruppe " + kl;
  const kopf = document.createElement("div");
  kopf.className = "gk";
  kopf.textContent = `${titel} · ${arr.length}`;
  g.appendChild(kopf);

  if (aktRolle === "trainer" && d) {
    const box = document.createElement("div");
    box.className = "tr-zeilen";
    arr.forEach((p) => box.appendChild(trainerZeile(p, d, mitGrund)));
    g.appendChild(box);
    return g;
  }

  if (mitGrund) {                                   // Absagen: Grund daneben
    g.insertAdjacentHTML("beforeend", `<div class="ab-liste">` +
      arr.map((p) =>
        `<div class="ab-zeile"><span class="az-n">${escape(p.name)}</span>` +
        `<span class="az-g${p.grund ? "" : " fehlt"}">${escape(p.grund || "kein Grund angegeben")}</span></div>`
      ).join("") + `</div>`);
    return g;
  }
  g.insertAdjacentHTML("beforeend", `<div class="t-namen">` +
    arr.map((p) => `<span class="t-name">${escape(p.name)}` +
      `${p.position === "Tor" ? ' <span class="tw">TW</span>' : ""}</span>`).join("") +
    `</div>`);
  return g;
}
// Trainer-Zeile: Name + drei Mini-Knoepfe. Der aktive Knopf nochmal getippt
// setzt die Antwort auf "noch offen" zurueck (Vertipper-Korrektur).
function trainerZeile(p, d, mitGrund) {
  const z = document.createElement("div");
  z.className = "tr-zeile";
  const st = p.status || "offen";
  const knopf = (s, zeichen, kl, titel) =>
    `<button class="tzb ${kl}${st === s ? " aktiv" : ""}" data-s="${s}" title="${titel}">${zeichen}</button>`;
  z.innerHTML =
    `<span class="tz-name">${escape(p.name)}` +
    `${p.position === "Tor" ? ' <span class="tw">TW</span>' : ""}` +
    `${p.quelle === "trainer" ? '<span class="tz-quelle" title="vom Trainer eingetragen">✎</span>' : ""}</span>` +
    `${mitGrund ? `<span class="tz-grund">${escape(p.grund || "")}</span>` : ""}` +
    `<span class="tz-knoepfe">` +
      knopf("anwesend", "✓", "ja", "zusagen") +
      knopf("unsicher", "?", "un", "unsicher") +
      knopf("abgesagt", "✗", "nein", "absagen") +
    `</span>`;
  z.querySelectorAll(".tzb").forEach((b) => b.addEventListener("click", () => {
    const neu = b.classList.contains("aktiv") ? "offen" : b.dataset.s;
    trainerRsvpSenden(d, p, neu);
  }));
  return z;
}
// Trainer traegt fuer eine Spielerin ein. Braucht Netz (der Server leitet die
// Spielerin aus der URL ab und prueft die Trainer-Rolle).
async function trainerRsvpSenden(d, p, status) {
  const lab = { anwesend: "zugesagt", unsicher: "unsicher", abgesagt: "abgesagt",
                offen: "wieder offen" };
  try {
    await api("/api/trainings/" + d.id + "/teilnahme/" + p.id, "POST", { status });
    const neu = {
      status: status === "offen" ? null : status,
      quelle: status === "offen" ? null : "trainer",
      grund: null,                      // Grund gehoert zur alten Antwort
    };
    Object.assign(p, neu);
    // dieselbe Spielerin im zwischengespeicherten Detail nachziehen
    const det = terminDetails.get(d.id);
    if (det && det !== d) {
      const q = (det.teilnahme || []).find((x) => x.id === p.id);
      if (q) Object.assign(q, neu);
    }
    if (aktTraining && aktTraining.id === d.id && aktTraining !== d) {
      const q = (aktTraining.teilnahme || []).find((x) => x.id === p.id);
      if (q) Object.assign(q, neu);
    }
    toast(`${p.name}: ${lab[status]} ✓`);
    await Sync.frischHolen("/api/trainings").catch(() => {});
    Sync.frischHolen("/api/trainings/" + d.id).catch(() => {});
    Sync.frischHolen("/api/naechstes-training").catch(() => {});
    zeichneTeilnahmeNeu(d.id);
  } catch (e) {
    toast(navigator.onLine ? ("Fehler: " + e.message)
      : "Kein Netz – Eintragen für andere braucht eine Verbindung.");
  }
}
// Nach einer Aenderung alles neu zeichnen, was diesen Termin zeigt.
function zeichneTeilnahmeNeu(tid) {
  if (aktTraining && aktTraining.id === tid
      && !$("#view-training-detail").classList.contains("hidden")) {
    renderRSVP(aktTraining);
    renderTeilnahme(aktTraining);
  }
  if (!$("#view-trainings").classList.contains("hidden")) ladeTrainingsListe();
  if (!$("#view-home").classList.contains("hidden")) { ladeHome(); }
}
function terminAktionen(t) {
  const akt = document.createElement("div");
  akt.className = "t-aktionen";

  // Plan und Erinnerung sind Trainer-Sache; wer nur das Amt "Balu-Trainings-App" hat, bekommt das Löschen.
  const trainer = aktRolle === "trainer";
  const oeffnen = document.createElement("button");
  oeffnen.textContent = "Öffnen & Plan";
  oeffnen.addEventListener("click", () => oeffneTraining(t.id));
  if (trainer) akt.appendChild(oeffnen);

  const erinnern = document.createElement("button");
  erinnern.textContent = "🔔 Erinnerung senden";
  erinnern.addEventListener("click", async () => {
    erinnern.disabled = true;
    try {
      const r = await api("/api/trainings/" + t.id + "/erinnern", "POST");
      toast(r.offen ? `Erinnerung an ${r.offen} Spielerin(nen) – ${r.gesendet} Gerät(e) erreicht.`
                    : "Alle haben schon geantwortet.");
    } catch (e) { toast("Fehler: " + e.message); }
    finally { erinnern.disabled = false; }
  });
  if (trainer) akt.appendChild(erinnern);

  // Zweistufig statt Rueckfrage-Dialog: erst scharf machen, dann loeschen.
  const weg = document.createElement("button");
  weg.className = "loeschen";
  weg.textContent = "Termin löschen";
  let scharf = false;
  weg.addEventListener("click", () => {
    if (!scharf) {
      scharf = true;
      weg.classList.add("scharf");
      weg.textContent = "Wirklich löschen?";
      setTimeout(() => {
        if (!scharf) return;
        scharf = false; weg.classList.remove("scharf"); weg.textContent = "Termin löschen";
      }, 4000);
      return;
    }
    terminLoeschen(t);
  });
  akt.appendChild(weg);
  return akt;
}
async function terminLoeschen(t) {
  const d = datumTeile(t.datum);
  try {
    await api("/api/trainings/" + t.id + "/loeschen", "POST", {});
    terminDetails.delete(t.id);
    offeneTermine.delete(t.id);
    await Sync.frischHolen("/api/trainings").catch(() => {});
    Sync.frischHolen("/api/naechstes-training").catch(() => {});
    toast(`${d.wt} ${d.tag} gelöscht.`);
    ladeTrainingsListe();
  } catch (e) {
    toast(navigator.onLine ? ("Fehler: " + e.message)
      : "Kein Netz – Löschen braucht eine Verbindung.");
  }
}
// „Neues Training" (nur Trainer/Admin): Datum/Uhrzeit/Ort.
function renderTrainingNeu() {
  const el = document.getElementById("trainings-neu");
  if (!el) return;
  if (aktRolle !== "trainer" && !hatRecht("termine")) { el.innerHTML = ""; return; }
  el.innerHTML =
    `<button id="tn-toggle" class="tn-toggle">＋ Neuer Termin</button>
     <div id="tn-form" class="tn-form hidden">
       <div class="tn-art">
         <button data-art="training" class="aktiv">Training</button>
         <button data-art="testspiel">Testspiel</button>
         <button data-art="ligaspiel">Ligaspiel</button>
       </div>
       <div class="tn-zeile">
         <input id="tn-datum" type="date" />
         <input id="tn-uhrzeit" type="time" title="Beginn bzw. Anwurf" />
       </div>
       <div id="tn-spiel" class="tn-spiel hidden">
         <input id="tn-gegner" type="text" placeholder="Gegner (z. B. TSV Blaustein)" />
         <div class="tn-heim">
           <button data-heim="1" class="aktiv">Heimspiel</button>
           <button data-heim="0">Auswärts</button>
         </div>
         <label id="tn-abfahrt-box" class="tn-abfahrt hidden">
           <span>Abfahrt</span><input id="tn-abfahrt" type="time" />
         </label>
       </div>
       <input id="tn-ort" type="text" placeholder="Ort (z. B. Gerhausen)" />
       <button id="tn-speichern" class="primaer">Anlegen</button>
     </div>`;
  document.getElementById("tn-toggle").addEventListener("click", () =>
    document.getElementById("tn-form").classList.toggle("hidden"));

  // Art umschalten: bei einem Spiel kommen Gegner und Heimrecht dazu.
  const artKnoepfe = el.querySelectorAll(".tn-art button");
  artKnoepfe.forEach((b) => b.addEventListener("click", () => {
    artKnoepfe.forEach((x) => x.classList.toggle("aktiv", x === b));
    tnArt = b.dataset.art;
    document.getElementById("tn-spiel").classList.toggle("hidden", tnArt === "training");
    tnAbfahrtSichtbar();
  }));
  // Heim/Auswaerts: die Abfahrtszeit gibt es nur auswaerts.
  const heimKnoepfe = el.querySelectorAll(".tn-heim button");
  heimKnoepfe.forEach((b) => b.addEventListener("click", () => {
    heimKnoepfe.forEach((x) => x.classList.toggle("aktiv", x === b));
    tnHeim = b.dataset.heim === "1";
    tnAbfahrtSichtbar();
  }));
  document.getElementById("tn-speichern").addEventListener("click", terminAnlegen);
}
let tnArt = "training";
let tnHeim = true;
function tnAbfahrtSichtbar() {
  const box = document.getElementById("tn-abfahrt-box");
  if (box) box.classList.toggle("hidden", tnArt === "training" || tnHeim);
}
async function terminAnlegen() {
  const wert = (id) => (document.getElementById(id).value || "").trim();
  const datum = wert("tn-datum");
  const uhrzeit = wert("tn-uhrzeit");
  const ort = wert("tn-ort");
  const gegner = wert("tn-gegner");
  const abfahrt = wert("tn-abfahrt");
  const spiel = tnArt !== "training";
  if (!datum) { toast("Bitte ein Datum wählen."); return; }
  if (spiel && !gegner) { toast("Bitte den Gegner eintragen."); return; }
  try {
    const r = await api("/api/trainings", "POST", {
      datum, uhrzeit, ort, art: tnArt,
      gegner: spiel ? gegner : null,
      heim: spiel ? tnHeim : null,
      abfahrt: spiel && !tnHeim ? abfahrt : null,
      titel: spiel ? "" : (ort ? "Training " + ort : "Training"),
    });
    const wort = { training: "Training", testspiel: "Testspiel", ligaspiel: "Ligaspiel" }[tnArt];
    toast(r.neu ? wort + " angelegt ✓" : "Termin am Datum aktualisiert ✓");
    ["tn-datum", "tn-uhrzeit", "tn-ort", "tn-gegner", "tn-abfahrt"].forEach((id) => {
      const f = document.getElementById(id); if (f) f.value = "";
    });
    document.getElementById("tn-form").classList.add("hidden");
    // Erst die Liste frisch holen, dann neu zeichnen - sonst rendert die
    // Uebersicht noch den gespiegelten Stand und der neue Termin fehlt.
    await Sync.frischHolen("/api/trainings").catch(() => {});
    ladeTrainingsListe();
  } catch (e) { toast("Fehler: " + e.message); }
}
export async function oeffneTraining(id) {
  let d = null;
  try { d = await Sync.apiOffline("/api/trainings/" + id); } catch (_) {}
  if (!d) { toast("Training nicht verfügbar (einmal online öffnen)."); return; }
  aktTraining = d;
  $("#td-titel").textContent = d.titel || (d.datum ? datumKurz(d.datum) : "Training");
  const teile = [];
  if (d.datum) teile.push(datumKurz(d.datum));
  if (istSpiel(d)) {
    teile.push(ART_WORT[terminArt(d)] + (d.heim === 0 ? " · auswärts" : " · daheim"));
    if (d.heim === 0 && d.abfahrt) teile.push("Abfahrt " + d.abfahrt);
    if (d.uhrzeit) teile.push("Anwurf " + d.uhrzeit);
  } else if (d.uhrzeit) {
    teile.push(d.uhrzeit);
  }
  if (d.ort) teile.push(d.ort);
  $("#td-meta").textContent = teile.join(" · ");
  renderRSVP(d);
  renderTeilnahme(d);
  renderErinnern(d);
  renderTrainingPlan();
  renderNachbereitung(d);
  zeigeView("view-training-detail");
}
// Zusagen/Unsicher/Abgesagt-Listen. Bei Absagen wird der Grund mit angezeigt
// (für Trainer UND Spielerinnen sichtbar).
function renderTeilnahme(d) {
  const el = $("#td-teilnahme");
  el.innerHTML = "";
  teilnahmeGruppen(el, d);
}
// Haeufige Absagegruende zum Antippen. Freitext bleibt daneben moeglich -
// ein leeres Feld verleitet dazu, die Absage einfach abzuschicken.
const ABSAGE_GRUENDE = ["Arbeit", "Urlaub", "Krank", "Verletzt", "Uni / Schule", "Anderer Termin"];
function renderRSVP(d) {
  const el = $("#td-rsvp");
  if (el) rsvpFuellen(el, d);
}
// Eigene Zu-/Absage. Wird an ZWEI Stellen benutzt (Termin-Detail und
// aufgeklappte Zeile in der Uebersicht), deshalb alles ueber `el` gesucht
// und nicht ueber globale IDs.
export function rsvpFuellen(el, d) {
  const sid = aktBenutzer && aktBenutzer.spieler_id;
  if (!sid) { el.innerHTML = ""; return; }          // Trainer / kein Spielerprofil
  if (aktBenutzer.im_kader === false) { el.innerHTML = ""; return; }   // Helferin (ehemalige Spielerin mit Amt): keine Zu-/Absage
  const meine = (d.teilnahme || []).find((t) => t.id === sid);
  const status = meine ? meine.status : null;
  const lab = { anwesend: "Zugesagt ✓", abgesagt: "Abgesagt", unsicher: "Unsicher" };
  const grund = (meine && meine.grund) || "";

  el.innerHTML =
    `<div class="rsvp-kopf">Deine Antwort: <b>${status ? lab[status] : "noch offen"}</b>` +
    `${status === "abgesagt" && grund ? ` – ${escape(grund)}` : ""}</div>
     <div class="rsvp-knoepfe">
       <button class="rsvp-ja${status === "anwesend" ? " aktiv" : ""}" data-s="anwesend">Zusagen</button>
       <button class="rsvp-un${status === "unsicher" ? " aktiv" : ""}" data-s="unsicher">Unsicher</button>
       <button class="rsvp-nein${status === "abgesagt" ? " aktiv" : ""}" data-s="abgesagt">Absagen</button>
     </div>
     <div class="rsvp-grund-box hidden">
       <div class="grund-chips">${ABSAGE_GRUENDE.map((g) =>
         `<button class="gchip${g === grund ? " aktiv" : ""}">${g}</button>`).join("")}</div>
       <div class="rsvp-grund-eingabe">
         <input class="rsvp-grund" type="text" maxlength="60"
                placeholder="Grund für die Absage (Pflicht)" value="${escape(grund)}" />
         <button class="rsvp-grund-senden primaer">Absage senden</button>
       </div>
     </div>`;

  const box = el.querySelector(".rsvp-grund-box");
  const feld = el.querySelector(".rsvp-grund");
  const chips = el.querySelectorAll(".gchip");

  chips.forEach((c) => c.addEventListener("click", () => {
    feld.value = c.classList.contains("aktiv") ? "" : c.textContent;
    chips.forEach((x) => x.classList.toggle("aktiv", x === c && feld.value !== ""));
  }));

  el.querySelectorAll(".rsvp-knoepfe button").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.dataset.s === "abgesagt") {              // Grund ist Pflicht -> erst fragen
        box.classList.remove("hidden");
        feld.focus({ preventScroll: true });
        return;
      }
      box.classList.add("hidden");
      rsvpSenden(b.dataset.s, null, d);
    }));

  el.querySelector(".rsvp-grund-senden").addEventListener("click", () => {
    const g = feld.value.trim();
    if (!g) { toast("Bitte einen Grund angeben – den sieht das ganze Team."); feld.focus(); return; }
    rsvpSenden("abgesagt", g, d);
  });
}
async function rsvpSenden(status, grund, d) {
  d = d || aktTraining;
  try {
    // Online-Aktion (Push/Team-Planung brauchen aktuelle Daten): direkt senden.
    await api("/api/trainings/" + d.id + "/teilnahme", "POST", { status, grund });
    const sid = aktBenutzer.spieler_id;
    // Die eigene Antwort in JEDEM Objekt nachziehen, das diesen Termin zeigt.
    // Bewusst kein terminDetails.set(): `d` kann ein Kurz-Objekt der Home-Box
    // sein - das wuerde die vollstaendige Namensliste im Cache ueberschreiben.
    const setzen = (obj) => {
      if (!obj) return;
      obj.teilnahme = obj.teilnahme || [];
      let m = obj.teilnahme.find((t) => t.id === sid);
      if (!m) { m = { id: sid, name: aktBenutzer.name, position: "Feld" }; obj.teilnahme.push(m); }
      m.status = status; m.grund = grund; m.quelle = "app";
    };
    setzen(d);
    setzen(terminDetails.get(d.id));
    if (aktTraining && aktTraining.id === d.id) setzen(aktTraining);
    toast(status === "abgesagt" ? "Abgesagt – der Grund steht jetzt beim Termin."
                                : "Antwort gespeichert ✓");
    // Zahlen und `meine_status` stimmen erst nach dem Nachladen der Liste.
    await Sync.frischHolen("/api/trainings").catch(() => {});
    Sync.frischHolen("/api/trainings/" + d.id).catch(() => {});
    Sync.frischHolen("/api/naechstes-training").catch(() => {});
    zeichneTeilnahmeNeu(d.id);
  } catch (e) {
    toast(navigator.onLine ? ("Fehler: " + e.message)
      : "Kein Netz – bitte online zu-/absagen.");
  }
}
