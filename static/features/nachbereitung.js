import { api } from "../core/api.js";
import { aktRolle } from "../core/konto.js";
import { aktTraining, istSpiel } from "./termine.js";
import { $, datumKurz, escape, toast } from "../core/ui.js";

// Plan anzeigen. Der Plan ist NUR fuer das Trainerteam - Spielerinnen sehen
// hier gar nichts, auch keinen Hinweis darauf, dass es einen gibt.
// ============================================== Spiel-Nachbereitung (Trainer) ==
//  Drei Textfelder je Spiel: Gedanken, Gegner (fuers Rueckspiel), Ansprache Montag.
//  Der Server haelt sie in eigener Tabelle (nur Trainer). Hier gilt: nichts geht still
//  verloren - jede Eingabe landet sofort als Entwurf in localStorage und bleibt dort,
//  bis der Server das Speichern bestaetigt hat. Scheitert es (Funkloch), bleibt der
//  Entwurf und die Meldung steht dauerhaft da. Hat ein anderer Trainer inzwischen
//  gespeichert, antwortet der Server mit 409 und der Nutzer entscheidet.
const NACHB_FELDER = [
  ["gedanken", "Meine Gedanken", "Eindruck vom Spiel – was ist hängengeblieben?"],
  ["gegner", "Gegner (fürs Rückspiel)", "Wie hat der Gegner gespielt, worauf ist zu achten?"],
  ["ansprache", "Ansprache Montag", "Was will ich im Training zum Spiel und Wochenende sagen?"],
];
let nachb = null;   // { tid, basis, vorspiel_id, kandidaten, frueher, konflikt, status }
let nachbTimer = null;
function nachbEntwurfLesen(tid) {
  try { return JSON.parse(localStorage.getItem("nachb-entwurf-" + tid) || "null"); } catch (_) { return null; }
}
function nachbEntwurfSchreiben(tid, e) {
  try {
    if (e) localStorage.setItem("nachb-entwurf-" + tid, JSON.stringify(e));
    else localStorage.removeItem("nachb-entwurf-" + tid);
    return true;
  } catch (_) { return false; }     // privater Modus / Speicher voll: Seite laeuft trotzdem
}
function nachbWerte() {
  const w = {};
  for (const [k] of NACHB_FELDER) w[k] = $("#nachb-" + k).value;
  return w;
}
function nachbStatus(text, art) {
  if (nachb) nachb.status = { text, art };
  const el = $("#nachb-status");
  if (el) { el.textContent = text; el.className = "nachb-status " + (art || ""); }
}
function nachbFrueherHtml(liste) {
  if (!liste.length) return "";
  return liste.map((e) => {
    const teile = [
      e.gegner ? `<h4>Gegner</h4><p>${escape(e.gegner)}</p>` : "",
      e.gedanken ? `<h4>Meine Gedanken</h4><p>${escape(e.gedanken)}</p>` : "",
    ].join("");
    return `<details class="nachb-frueher" open>
      <summary>Beim letzten Mal${e.manuell ? " (von dir zugeordnet)" : ""}: ${escape(e.titel || e.gegner_name || "Spiel")}
        · ${escape(e.datum ? datumKurz(e.datum) : "")}</summary>${teile || '<p class="hinweis">Nur eine Ansprache notiert.</p>'}
    </details>`;
  }).join("");
}
function nachbKonfliktHtml(k) {
  const a = k.aktuell;
  return `<div class="nachb-konflikt" role="alert">
    <b>${escape(a.autor || "Ein anderer Trainer")} hat inzwischen gespeichert.</b>
    <p class="hinweis">Dein Entwurf ist noch da und nichts ist überschrieben. Die andere Fassung:</p>
    ${NACHB_FELDER.map(([key, name]) => a[key] ? `<h4>${escape(name)}</h4><p>${escape(a[key])}</p>` : "").join("")}
    <div class="nachb-knoepfe">
      <button type="button" data-nachb="meine">Meine Fassung speichern</button>
      <button type="button" data-nachb="andere">Andere Fassung übernehmen</button>
    </div></div>`;
}
function nachbZeichnen(werte) {
  const el = $("#td-nachb");
  const kand = nachb.kandidaten.map((c) =>
    `<option value="${c.id}"${c.id === nachb.vorspiel_id ? " selected" : ""}>${escape(c.datum ? datumKurz(c.datum) : "")} · ${escape(c.gegner || c.titel || "Spiel")}</option>`).join("");
  el.innerHTML =
    `<div class="td-plan-kopf">Nachbereitung <span class="nur-trainer">nur für Trainer</span></div>
     ${nachbFrueherHtml(nachb.frueher)}
     ${nachb.konflikt ? nachbKonfliktHtml(nachb.konflikt) : ""}
     ${NACHB_FELDER.map(([k, name, ph]) =>
       `<label class="nachb-feld"><span>${name}</span>
        <textarea id="nachb-${k}" rows="4" maxlength="10000" placeholder="${escape(ph)}"></textarea></label>`).join("")}
     <details class="nachb-vor"><summary>Früheres Spiel gegen diesen Gegner von Hand wählen</summary>
       <select id="nachb-vorspiel"><option value="">– keins –</option>${kand}</select>
       <small class="hinweis">Falls der Gegner anders geschrieben ist. Gilt nach dem Speichern.</small></details>
     <div class="nachb-knoepfe">
       <button type="button" class="primaer" data-nachb="speichern">Speichern</button>
       <span id="nachb-status" class="nachb-status"></span>
     </div>`;
  for (const [k] of NACHB_FELDER) $("#nachb-" + k).value = werte[k] || "";
  if (nachb.status) nachbStatus(nachb.status.text, nachb.status.art);
}
export async function renderNachbereitung(d) {
  const el = $("#td-nachb");
  nachb = null;
  if (aktRolle !== "trainer" || !istSpiel(d)) { el.innerHTML = ""; return; }
  const tid = d.id;
  const entwurf = nachbEntwurfLesen(tid);
  let server = null, ladefehler = false;
  try { server = await api(`/api/trainings/${tid}/nachbereitung`); } catch (_) { ladefehler = true; }
  if (!aktTraining || aktTraining.id !== tid) return;          // inzwischen ein anderes Spiel offen

  nachb = {
    tid,
    basis: entwurf ? entwurf.basis : (server ? server.geaendert_am : null),
    vorspiel_id: entwurf && "vorspiel_id" in entwurf ? entwurf.vorspiel_id : (server ? server.vorspiel_id : null),
    kandidaten: server ? server.kandidaten : [],
    frueher: server ? server.frueher : [],
    konflikt: null, status: null,
  };
  let werte = server || {};
  if (entwurf) {
    werte = entwurf;
    const veraltet = server && (server.geaendert_am || null) !== (entwurf.basis || null);
    if (veraltet) nachb.konflikt = { aktuell: server };
    nachb.status = { text: veraltet ? "Entwurf – die gespeicherte Fassung ist neuer, bitte oben entscheiden."
                                    : "Ungespeicherter Entwurf von diesem Gerät.", art: "warn" };
  } else if (ladefehler) {
    nachb.status = { text: "Kein Netz: Du kannst schon schreiben, der Text bleibt als Entwurf auf diesem Gerät. Gespeicherte Notizen und Hinweise aus früheren Spielen lädst du mit Netz.", art: "warn" };
  }
  nachbZeichnen(werte);
}
async function nachbSpeichern(trotzKonflikt) {
  if (!nachb) return;
  const tid = nachb.tid, w = nachbWerte();
  const vs = $("#nachb-vorspiel").value;
  const vorspiel_id = vs ? Number(vs) : null;
  const basis = trotzKonflikt && nachb.konflikt ? nachb.konflikt.aktuell.geaendert_am : nachb.basis;
  // Sicherheitsnetz zuerst: Entwurf mit dem Stand, auf dem er beruht.
  nachbEntwurfSchreiben(tid, { ...w, vorspiel_id, basis: nachb.basis, zeit: Date.now() });
  const knopf = document.querySelector('[data-nachb="speichern"]');
  if (knopf) knopf.disabled = true;
  nachbStatus("Speichert…", "");
  try {
    const res = await fetch(`/api/trainings/${tid}/nachbereitung`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...w, vorspiel_id, basis }),
    });
    if (res.status === 409) {
      const k = await res.json();
      nachb.konflikt = { aktuell: k.aktuell };
      nachb.vorspiel_id = vorspiel_id;
      nachbZeichnen(w);
      nachbStatus("Nicht gespeichert: Es gibt eine neuere Fassung. Dein Entwurf ist sicher.", "fehler");
      return;
    }
    if (!res.ok) throw new Error((await res.text()) || res.statusText);
    const d = await res.json();
    nachbEntwurfSchreiben(tid, null);
    if (!aktTraining || aktTraining.id !== tid) return;
    nachb = { ...nachb, basis: d.geaendert_am, vorspiel_id: d.vorspiel_id, kandidaten: d.kandidaten,
              frueher: d.frueher, konflikt: null, status: null };
    nachbZeichnen(d);
    nachbStatus("Gespeichert ✓", "ok");
    Sync.frischHolen("/api/trainings").catch(() => {});      // 📝 in der Terminliste
  } catch (e) {
    nachbStatus(navigator.onLine
      ? "Nicht gespeichert: " + e.message + " – Entwurf bleibt auf diesem Gerät."
      : "Nicht gespeichert: kein Netz. Entwurf bleibt auf diesem Gerät, tippe später erneut auf Speichern.", "fehler");
  } finally {
    const k2 = document.querySelector('[data-nachb="speichern"]');
    if (k2) k2.disabled = false;
  }
}
$("#td-nachb").addEventListener("input", (e) => {
  if (!nachb || !e.target.matches("textarea, select")) return;
  clearTimeout(nachbTimer);
  const tid = nachb.tid;
  nachbTimer = setTimeout(() => {
    if (!nachb || nachb.tid !== tid) return;
    const vs = $("#nachb-vorspiel").value;
    const ok = nachbEntwurfSchreiben(tid, { ...nachbWerte(), vorspiel_id: vs ? Number(vs) : null,
                                            basis: nachb.basis, zeit: Date.now() });
    nachbStatus(ok ? "Entwurf auf diesem Gerät gesichert – noch nicht gespeichert."
                   : "Achtung: Entwurf konnte nicht lokal gesichert werden. Bitte speichern.", "warn");
  }, 400);
});
$("#td-nachb").addEventListener("click", (e) => {
  const b = e.target.closest("[data-nachb]");
  if (!b || !nachb) return;
  if (b.dataset.nachb === "speichern") nachbSpeichern(false);
  else if (b.dataset.nachb === "meine") nachbSpeichern(true);
  else if (b.dataset.nachb === "andere") {
    const a = nachb.konflikt.aktuell;
    nachbEntwurfSchreiben(nachb.tid, null);
    nachb = { ...nachb, basis: a.geaendert_am, vorspiel_id: a.vorspiel_id, kandidaten: a.kandidaten,
              frueher: a.frueher, konflikt: null, status: null };
    nachbZeichnen(a);
    nachbStatus("Andere Fassung übernommen.", "ok");
  }
});
window.addEventListener("online", () => {
  if (nachb && nachbEntwurfLesen(nachb.tid)) toast("Wieder online – Nachbereitung jetzt speichern.");
});
