import { api } from "../core/api.js";
import { aktRolle } from "../core/konto.js";
import { gehe, zeigeView } from "../core/router.js";
import { aktTraining, terminDetails } from "./termine.js";
import { $, datumTeile, escape, mdLite, toast } from "../core/ui.js";

export function renderTrainingPlan() {
  const el = $("#td-plan");
  const d = aktTraining;
  if (aktRolle !== "trainer") { el.innerHTML = ""; return; }

  const bloecke = d.bloecke || [];
  const hatPlan = d.plan_markdown && d.plan_markdown.trim();
  const hatInhalt = d.inhalt && d.inhalt.trim();

  if (bloecke.length) {
    el.innerHTML = `<div class="td-plan-kopf">Trainingsplan <span class="nur-trainer">nur für Trainer</span></div>`;
    el.appendChild(planZeitstrahl(d));
    el.appendChild(planKnopf("✏️ Plan bearbeiten", () => oeffnePlanEditor(d)));
    return;
  }

  // Noch keine Bloecke: alten Text zeigen und das Umwandeln anbieten.
  if (hatPlan) el.innerHTML = `<div class="td-plan-kopf">Trainingsplan <span class="nur-trainer">nur für Trainer</span></div>` + mdLite(d.plan_markdown);
  else if (hatInhalt) el.innerHTML = `<div class="td-plan-kopf">Inhalt</div>` + mdLite(d.inhalt);
  else el.innerHTML = `<p class="hinweis">Für diese Einheit steht noch nichts.</p>`;

  if (hatPlan || hatInhalt) {
    el.appendChild(planKnopf("In Blöcke übernehmen", () => bloeckeAusText(d), "primaer"));
    el.appendChild(planKnopf("Text bearbeiten", startPlanEdit));
  } else {
    el.appendChild(planKnopf("Training aufschreiben", () => oeffnePlanEditor(d), "primaer"));
  }
}
function planKnopf(text, fn, extra) {
  const b = document.createElement("button");
  b.className = "plan-edit-btn" + (extra ? " " + extra : "");
  b.textContent = text;
  b.addEventListener("click", fn);
  return b;
}
// Alten Plantext serverseitig in Bloecke zerlegen (jede Ueberschrift ein Block).
async function bloeckeAusText(d) {
  try {
    const r = await api("/api/trainings/" + d.id + "/blocks/aus-text", "POST");
    d.bloecke = r.bloecke || [];
    await patchBloeckeCache(d.id, d.bloecke);
    renderTrainingPlan();
    toast(`${d.bloecke.length} Blöcke angelegt – jetzt kannst du Zeiten ergänzen.`);
  } catch (e) {
    toast(navigator.onLine ? ("Fehler: " + e.message)
      : "Kein Netz – das Umwandeln braucht eine Verbindung.");
  }
}
function startPlanEdit() {
  const el = $("#td-plan");
  const ta = document.createElement("textarea");
  ta.className = "plan-editor";
  ta.value = aktTraining.plan_markdown || "";
  ta.rows = 14;
  ta.placeholder = "Trainingsplan (Markdown: # Überschrift, - Liste, **fett**) …";
  const leiste = document.createElement("div");
  leiste.className = "plan-edit-leiste";
  const speichern = document.createElement("button");
  speichern.className = "primaer"; speichern.textContent = "Speichern";
  speichern.addEventListener("click", () => savePlan(ta.value));
  const abbrechen = document.createElement("button");
  abbrechen.textContent = "Abbrechen";
  abbrechen.addEventListener("click", renderTrainingPlan);
  leiste.appendChild(speichern); leiste.appendChild(abbrechen);
  el.innerHTML = `<div class="td-plan-kopf">Plan bearbeiten</div>`;
  el.appendChild(ta); el.appendChild(leiste);
  ta.focus();
}
async function savePlan(markdown) {
  const d = aktTraining;
  try {
    // Immer über die Outbox: online sofort, offline gepuffert (Token dedupliziert).
    const r = await Sync.senden("/api/trainings/" + d.id + "/plan", { markdown });
    d.plan_markdown = markdown;                 // optimistisch lokal
    await patchTrainingCache(d.id, markdown);   // GET-Cache konsistent halten
    renderTrainingPlan();
    toast(r.gesendet ? "Plan gespeichert ✓"
      : "Offline gespeichert – wird im WLAN synchronisiert.");
  } catch (e) { toast("Fehler: " + e.message); }
}
// Den gespiegelten GET-Cache mitziehen, damit die Änderung auch offline sofort
// stimmt (Detail-Plan + hat_plan in der Liste).
async function patchTrainingCache(id, markdown) {
  const gesetzt = !!(markdown && markdown.trim());
  try {
    const detail = await LocalDB.get("responses", "/api/trainings/" + id);
    if (detail && detail.daten) {
      detail.daten.plan_markdown = markdown;
      await LocalDB.put("responses", { pfad: "/api/trainings/" + id, daten: detail.daten, ts: Date.now() });
    }
    const liste = await LocalDB.get("responses", "/api/trainings");
    if (liste && Array.isArray(liste.daten)) {
      const t = liste.daten.find((x) => x.id === id);
      if (t) { t.hat_plan = gesetzt ? 1 : 0;
        await LocalDB.put("responses", { pfad: "/api/trainings", daten: liste.daten, ts: Date.now() }); }
    }
  } catch (_) { /* Cache-Patch ist best-effort */ }
}
$("#btn-training-zurueck").addEventListener("click", () => gehe("training", "trainings"));
$("#btn-plan-zurueck").addEventListener("click", planVerlassen);
// ================================================ Trainingsplan in Bloecken ==
//  "Wann mache ich was": Bloecke mit optionaler Dauer. Aus den Dauern rechnet
//  die App die Uhrzeiten - man plant in Minuten, denkt aber in Uhrzeiten.
//  Alles hier ist NUR fuer Trainer; jede Stelle prueft die Rolle selbst.

let planTraining = null;       // Training-Detail, das gerade bearbeitet wird
let planBloecke = [];          // Arbeitskopie der Bloecke
let planTimer = null;          // Entprellung fuer Tipp-Aenderungen
let planUebungen = null;       // Titel aus der Uebungssammlung (einmal geladen)
let planChipsOffen = false;
function zeitZuMinuten(z) {
  const m = /^(\d{1,2}):(\d{2})/.exec(z || "");
  return m ? (+m[1]) * 60 + (+m[2]) : null;
}
function minutenZuZeit(m) {
  return String(Math.floor(m / 60) % 24).padStart(2, "0") + ":" +
         String(Math.round(m) % 60).padStart(2, "0");
}
const planSumme = (b) => (b || []).reduce((s, x) => s + (Number(x.dauer_min) || 0), 0);
// Nur-Lesen-Ansicht: Uhrzeit, was, wie lange.
function planZeitstrahl(d) {
  const box = document.createElement("div");
  box.className = "zeitstrahl";
  let t = zeitZuMinuten(d.uhrzeit);
  for (const b of d.bloecke || []) {
    const dauer = Number(b.dauer_min) || 0;
    const zeile = document.createElement("div");
    zeile.className = "zs-zeile";
    zeile.innerHTML =
      `<span class="zs-uhr">${t != null && dauer ? minutenZuZeit(t) : ""}</span>
       <span class="zs-txt"><b>${escape(b.titel || "Ohne Titel")}</b>` +
      `${b.notiz ? `<small>${escape(b.notiz)}</small>` : ""}</span>
       <span class="zs-dauer">${dauer ? dauer + "′" : ""}</span>`;
    box.appendChild(zeile);
    if (t != null && dauer) t += dauer;
  }
  return box;
}
function oeffnePlanEditor(d) {
  if (aktRolle !== "trainer") return;
  planTraining = d;
  planBloecke = (d.bloecke || []).map((b) =>
    ({ dauer_min: b.dauer_min, titel: b.titel || "", notiz: b.notiz || "" }));
  planChipsOffen = false;
  renderPlanSeite();
  zeigeView("view-plan");
}
function renderPlanSeite() {
  const d = planTraining;
  if (!d) return;
  const dt = datumTeile(d.datum);
  $("#plan-titel").textContent = "Training aufschreiben";
  $("#plan-meta").innerHTML =
    `${dt.wt} ${escape(dt.tag)}${d.uhrzeit ? " · ab " + escape(d.uhrzeit) : ""}` +
    `${d.titel ? " · " + escape(d.titel) : ""} <span class="nur-trainer">nur für Trainer</span>`;

  renderPlanBilanz();
  renderPlanBloecke();
  renderPlanWerkzeug();
}
function renderPlanBilanz() {
  const d = planTraining;
  const summe = planSumme(planBloecke);
  const start = zeitZuMinuten(d.uhrzeit);
  const ohne = planBloecke.filter((b) => !Number(b.dauer_min)).length;
  const el = $("#plan-bilanz");
  el.className = "plan-bilanz";
  el.innerHTML =
    `<div class="pz"><b>${summe}</b><span>Minuten geplant · ${planBloecke.length} ` +
    `${planBloecke.length === 1 ? "Block" : "Blöcke"}</span></div>` +
    `<div class="prest">` +
    (start != null && summe
      ? `Beginn ${escape(d.uhrzeit)} · Ende ${minutenZuZeit(start + summe)}`
      : start != null ? `Beginn ${escape(d.uhrzeit)} – noch keine Dauer eingetragen`
      : `Ohne Uhrzeit am Termin gibt es keine Uhrzeiten im Plan.`) +
    (ohne ? ` · ${ohne} ohne Dauer` : "") +
    `</div><div class="plan-status" id="plan-status"></div>`;
}
function renderPlanBloecke() {
  const el = $("#plan-bloecke");
  el.innerHTML = "";
  if (!planBloecke.length) {
    el.innerHTML = `<div class="plan-leer"><p>Noch kein Block. Fang mit dem Einlaufen an.</p></div>`;
    return;
  }
  let t = zeitZuMinuten(planTraining.uhrzeit);
  planBloecke.forEach((b, i) => {
    const dauer = Number(b.dauer_min) || 0;
    const k = document.createElement("div");
    k.className = "block";

    const oben = document.createElement("div");
    oben.className = "block-oben";
    oben.innerHTML = `<span class="b-uhr">${t != null && dauer ? minutenZuZeit(t) : "—"}</span>`;

    const dau = document.createElement("input");
    dau.className = "b-dauer"; dau.type = "number"; dau.min = "1"; dau.max = "300";
    dau.inputMode = "numeric"; dau.placeholder = "–";
    dau.value = dauer || "";
    dau.setAttribute("aria-label", "Dauer in Minuten");
    dau.addEventListener("input", () => {
      b.dauer_min = dau.value === "" ? null : (parseInt(dau.value, 10) || null);
      renderPlanBilanz();
      planUhrzeitenAuffrischen();
      planSpaeterSpeichern();
    });
    oben.appendChild(dau);
    oben.appendChild(el2("span", "b-min", "Min."));

    const wz = document.createElement("div");
    wz.className = "b-werkzeug";
    wz.appendChild(werkzeug("↑", "Nach oben", i === 0, () => planTauschen(i, i - 1)));
    wz.appendChild(werkzeug("↓", "Nach unten", i === planBloecke.length - 1, () => planTauschen(i, i + 1)));
    wz.appendChild(werkzeug("✕", "Block löschen", false, () => planBlockWeg(i), "weg"));
    oben.appendChild(wz);
    k.appendChild(oben);

    const ti = document.createElement("input");
    ti.className = "b-titel"; ti.type = "text"; ti.maxLength = 120;
    ti.value = b.titel || ""; ti.placeholder = "Was wird gemacht?";
    ti.setAttribute("aria-label", "Titel des Blocks");
    ti.addEventListener("input", () => { b.titel = ti.value; planSpaeterSpeichern(); });
    k.appendChild(ti);

    const no = document.createElement("input");
    no.className = "b-notiz"; no.type = "text"; no.maxLength = 500;
    no.value = b.notiz || ""; no.placeholder = "Notiz – Aufbau, Variante, worauf achten";
    no.setAttribute("aria-label", "Notiz");
    no.addEventListener("input", () => { b.notiz = no.value; planSpaeterSpeichern(); });
    k.appendChild(no);

    el.appendChild(k);
    if (t != null && dauer) t += dauer;
  });
}
function el2(tag, klasse, text) {
  const e = document.createElement(tag);
  e.className = klasse; e.textContent = text;
  return e;
}
function werkzeug(zeichen, titel, aus, fn, extra) {
  const b = document.createElement("button");
  b.textContent = zeichen; b.title = titel; b.disabled = !!aus;
  if (extra) b.className = extra;
  b.addEventListener("click", fn);
  return b;
}
// Uhrzeiten nachziehen, ohne die Eingabefelder neu zu bauen (sonst springt
// der Cursor beim Tippen aus dem Minutenfeld).
function planUhrzeitenAuffrischen() {
  let t = zeitZuMinuten(planTraining.uhrzeit);
  document.querySelectorAll("#plan-bloecke .b-uhr").forEach((e, i) => {
    const dauer = Number((planBloecke[i] || {}).dauer_min) || 0;
    e.textContent = t != null && dauer ? minutenZuZeit(t) : "—";
    if (t != null && dauer) t += dauer;
  });
}
function planTauschen(a, b) {
  if (b < 0 || b >= planBloecke.length) return;
  const x = planBloecke[a]; planBloecke[a] = planBloecke[b]; planBloecke[b] = x;
  renderPlanSeite(); planJetztSpeichern();
}
function planBlockWeg(i) {
  const raus = planBloecke.splice(i, 1)[0];
  renderPlanSeite(); planJetztSpeichern();
  toast(`„${raus.titel || "Block"}" entfernt.`);
}
function planBlockNeu(titel, dauer) {
  planBloecke.push({ dauer_min: dauer || null, titel: titel || "", notiz: "" });
  renderPlanSeite(); planJetztSpeichern();
  const felder = document.querySelectorAll("#plan-bloecke .b-titel");
  if (felder.length && !titel) felder[felder.length - 1].focus();
}
function renderPlanWerkzeug() {
  const el = $("#plan-werkzeug");
  el.innerHTML = "";

  const neu = document.createElement("button");
  neu.className = "knopf-plan primaer";
  neu.textContent = "＋ Block hinzufügen";
  neu.addEventListener("click", () => planBlockNeu());
  el.appendChild(neu);

  const auf = document.createElement("button");
  auf.className = "knopf-plan";
  auf.textContent = (planChipsOffen ? "▾ " : "▸ ") + "Aus der Übungssammlung";
  auf.addEventListener("click", async () => {
    planChipsOffen = !planChipsOffen;
    if (planChipsOffen) await ladePlanUebungen();
    renderPlanWerkzeug();
  });
  el.appendChild(auf);

  if (planChipsOffen) {
    const box = document.createElement("div");
    box.className = "uebung-chips";
    if (planUebungen === null) box.innerHTML = '<p class="hinweis">Lädt…</p>';
    else if (!planUebungen.length) box.innerHTML = '<p class="hinweis">Keine Übungen gefunden.</p>';
    else planUebungen.forEach((name) => {
      const c = document.createElement("button");
      c.className = "uchip"; c.textContent = "＋ " + name;
      c.addEventListener("click", () => { planBlockNeu(name, 20); toast(`„${name}" angehängt.`); });
      box.appendChild(c);
    });
    el.appendChild(box);
  }

  const fertig = document.createElement("button");
  fertig.className = "knopf-plan";
  fertig.textContent = "Fertig";
  fertig.addEventListener("click", planVerlassen);
  el.appendChild(fertig);
}
async function ladePlanUebungen() {
  if (planUebungen !== null) return;
  try {
    const seiten = await Sync.apiOffline("/api/seiten?kategorie=uebung");
    const namen = (seiten || []).map((s) => (s.titel || "").trim()).filter(Boolean);
    planUebungen = [...new Set(namen)].sort((a, b) => a.localeCompare(b, "de"));
  } catch (_) { planUebungen = []; }
}
// -------------------------------------------------------------- Speichern ---
function planStatus(text) {
  const el = document.getElementById("plan-status");
  if (el) el.textContent = text || "";
}
function planSpaeterSpeichern() {
  planStatus("ändert…");
  clearTimeout(planTimer);
  planTimer = setTimeout(planJetztSpeichern, 900);
}
async function planJetztSpeichern() {
  clearTimeout(planTimer);
  const d = planTraining;
  if (!d) return;
  const bloecke = planBloecke.map((b) => ({
    dauer_min: Number(b.dauer_min) || null,
    titel: (b.titel || "").trim(),
    notiz: (b.notiz || "").trim() || null,
  }));
  planStatus("speichert…");
  try {
    // Ueber die Outbox: online sofort, offline gepuffert. Der Endpunkt ersetzt
    // den ganzen Plan, ein wiederholter Versuch verdoppelt also nichts.
    const r = await Sync.senden("/api/trainings/" + d.id + "/blocks", { bloecke });
    d.bloecke = bloecke;
    await patchBloeckeCache(d.id, bloecke);
    planStatus(r.gesendet ? "gespeichert ✓" : "offline gespeichert – wird synchronisiert");
  } catch (e) {
    planStatus("nicht gespeichert: " + e.message);
  }
}
// GET-Cache mitziehen, damit der Plan auch offline sofort stimmt.
async function patchBloeckeCache(id, bloecke) {
  try {
    const detail = await LocalDB.get("responses", "/api/trainings/" + id);
    if (detail && detail.daten) {
      detail.daten.bloecke = bloecke;
      await LocalDB.put("responses",
        { pfad: "/api/trainings/" + id, daten: detail.daten, ts: Date.now() });
    }
    const liste = await LocalDB.get("responses", "/api/trainings");
    if (liste && Array.isArray(liste.daten)) {
      const t = liste.daten.find((x) => x.id === id);
      if (t) {
        t.hat_plan = bloecke.length ? 1 : t.hat_plan;
        t.plan_minuten = planSumme(bloecke);
        await LocalDB.put("responses", { pfad: "/api/trainings", daten: liste.daten, ts: Date.now() });
      }
    }
    terminDetails.delete(id);      // Namen/Plan beim naechsten Aufklappen frisch
  } catch (_) { /* Cache ist Beiwerk */ }
}
async function planVerlassen() {
  await planJetztSpeichern();
  if (aktTraining && planTraining && aktTraining.id === planTraining.id) {
    aktTraining.bloecke = planTraining.bloecke;
    renderTrainingPlan();
    zeigeView("view-training-detail");
  } else {
    gehe("training", "trainings");
  }
}
