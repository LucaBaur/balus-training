import { api } from "../core/api.js";
import { $, escape, toast } from "../core/ui.js";

// ============================================================ Wochen-To-Dos ==
//  Spielerin (Ich -> To Do): wählt aus den Zielen, die der Trainer für sie angelegt
//  hat, eins für die Woche. Trainer (Team -> To-Dos): legt Ziele an, sieht die Wahl
//  und gibt am Wochenende Feedback: „bleibt“ (weiter daran arbeiten) oder „erledigt“.
//  Nur online – Schreiben ohne Netz meldet einen Fehler statt still zu verschwinden.
let todoDaten = null;          // Antwort von /api/todos
let todoTeam = null;           // Antwort von /api/todos/team
const todoAufgeklappt = new Set();   // spieler_id der geöffneten Blöcke (überlebt Neuzeichnen)
function todoDatum(iso) {
  const d = new Date(iso + "T00:00:00");
  return isNaN(d) ? iso : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
}
function todoFehler(e) {
  try { const j = JSON.parse(e.message); if (j && j.detail) return j.detail; } catch (_) {}
  return "Keine Verbindung – bitte später nochmal.";
}
// Jüngstes Feedback eines To-Dos (die Wochenliste ist neueste-zuerst sortiert)
export const todoLetztesFeedback = (t) => t.wochen.find((w) => w.ergebnis);
export async function ladeTodo() {
  const el = $("#todo-inhalt");
  if (!todoDaten) el.innerHTML = '<p class="hinweis">Lädt…</p>';
  try {
    todoDaten = await api("/api/todos");
    renderTodo();
  } catch (_) {
    if (!todoDaten) el.innerHTML = '<p class="hinweis">Deine To-Dos konnten nicht geladen werden – dafür brauchst du eine Verbindung.</p>';
  }
}
function renderTodo() {
  const el = $("#todo-inhalt");
  const { todos, woche, max_wahl: maxWahl } = todoDaten;
  if (!todos.length) {
    el.innerHTML = '<p class="hinweis">Dein Trainer hat noch keine To-Dos für dich angelegt.</p>';
    return;
  }
  const feedback = (t) => {
    const f = todoLetztesFeedback(t);
    return f && f.feedback
      ? `<div class="todo-feedback"><b>Trainer</b> (Woche ab ${todoDatum(f.woche)}): ${escape(f.feedback)}</div>` : "";
  };
  const gewaehlt = todos.filter((t) => t.gewaehlt);
  const voll = gewaehlt.length >= maxWahl;
  const wahl = gewaehlt.filter((t) => t.status === "offen").map((t) => `<div class="todo-zeile todo-gewaehlt">
      <span class="todo-haken">☐</span>
      <div class="todo-text">${escape(t.text)}${feedback(t)}</div>
      ${t.wochen.some((w) => w.woche === woche && w.ergebnis) ? "" :
        `<button type="button" class="todo-knopf" data-todo-waehlen="${t.id}" data-an="0">Zurücknehmen</button>`}
    </div>`).join("");
  const offen = todos.filter((t) => t.status === "offen" && !t.gewaehlt).map((t) => `<div class="todo-zeile">
      <span class="todo-haken">☐</span>
      <div class="todo-text">${escape(t.text)}${feedback(t)}</div>
      <button type="button" class="todo-knopf primaer" data-todo-waehlen="${t.id}" data-an="1" ${voll ? "disabled" : ""}>Wählen</button>
    </div>`).join("");
  const fertig = todos.filter((t) => t.status === "erledigt").map((t) => `<div class="todo-zeile todo-fertig">
      <span class="todo-haken">☑</span>
      <div class="todo-text">${escape(t.text)}${feedback(t)}</div>
    </div>`).join("");
  el.innerHTML = `<p class="hinweis">Wähle für die Woche ab ${todoDatum(woche)} ${maxWahl === 1 ? "ein To-Do" : "bis zu " + maxWahl + " To-Dos"}. Im Training schaut dein Trainer, wie es lief.</p>`
    + `<h3 class="todo-titel">Diese Woche</h3>`
    + (wahl || '<p class="hinweis">Noch nichts gewählt.</p>')
    + (offen ? `<h3 class="todo-titel">Zur Auswahl</h3>${offen}` : "")
    + (fertig ? `<h3 class="todo-titel">Geschafft</h3>${fertig}` : "");
}
$("#todo-inhalt").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-todo-waehlen]");
  if (!b || b.disabled) return;
  b.disabled = true;
  try {
    todoDaten = await api(`/api/todos/${b.dataset.todoWaehlen}/waehlen`, "POST", { gewaehlt: b.dataset.an === "1" });
    renderTodo();
  } catch (err) { toast(todoFehler(err)); b.disabled = false; }
});
export async function ladeTodoTeam() {
  const el = $("#todo-team-inhalt");
  if (!todoTeam) el.innerHTML = '<p class="hinweis">Lädt…</p>';
  try {
    todoTeam = await api("/api/todos/team");
    renderTodoTeam();
  } catch (_) {
    if (!todoTeam) el.innerHTML = '<p class="hinweis">To-Dos konnten nicht geladen werden – dafür brauchst du eine Verbindung.</p>';
  }
}
function todoTeamZeile(t, woche) {
  const w = t.wochen.find((x) => x.woche === t.offene_woche);
  let status = "";
  if (t.status === "erledigt") status = '<span class="todo-chip fertig">✓ erledigt</span>';
  else if (t.gewaehlt) status = '<span class="todo-chip gewaehlt">diese Woche gewählt</span>';
  const fb = !w ? "" : `<div class="todo-fbbox" data-todo="${t.id}" data-woche="${w.woche}">
      <small>Gewählt für die Woche ab ${todoDatum(w.woche)}${w.woche === woche ? " (läuft noch)" : ""}</small>
      <textarea rows="2" maxlength="1000" placeholder="Kurzes Feedback: Wie lief es?"></textarea>
      <div class="todo-fbknoepfe">
        <button type="button" data-todo-fb="bleibt">Bleibt noch</button>
        <button type="button" class="primaer" data-todo-fb="erledigt">Erledigt ✓</button>
      </div></div>`;
  const letztes = todoLetztesFeedback(t);
  const alt = letztes && letztes.feedback
    ? `<div class="todo-feedback">Dein Feedback (${todoDatum(letztes.woche)}, ${letztes.ergebnis === "erledigt" ? "erledigt" : "bleibt"}): ${escape(letztes.feedback)}</div>` : "";
  return `<div class="todo-zeile ${t.status === "erledigt" ? "todo-fertig" : ""}">
      <span class="todo-haken">${t.status === "erledigt" ? "☑" : "☐"}</span>
      <div class="todo-text">${escape(t.text)} ${status}${alt}${fb}</div>
      <div class="todo-aktionen">
        ${t.status === "erledigt" ? `<button type="button" data-todo-offen="${t.id}" title="Wieder öffnen">↺</button>` : ""}
        <button type="button" data-todo-edit="${t.id}" title="Text ändern">✎</button>
        <button type="button" data-todo-del="${t.id}" title="Löschen">🗑</button>
      </div></div>`;
}
function renderTodoTeam() {
  const el = $("#todo-team-inhalt");
  const { spielerinnen, woche, warten } = todoTeam;
  const kopf = `<p class="hinweis">Woche ab ${todoDatum(woche)} · ${warten ? `<b>${warten} warten auf Feedback</b>` : "kein Feedback offen"}</p>`;
  el.innerHTML = kopf + spielerinnen.map((s) => {
    const offeneFb = s.todos.filter((t) => t.offene_woche).length;
    const offen = todoAufgeklappt.has(s.spieler_id) || offeneFb > 0;
    const gewaehlt = s.todos.filter((t) => t.gewaehlt).map((t) => t.text);
    return `<details class="todo-block" data-sid="${s.spieler_id}" ${offen ? "open" : ""}>
      <summary><b>${escape(s.name)}</b>
        <small>${s.todos.length ? `${s.todos.filter((t) => t.status === "offen").length} offen` : "keine To-Dos"}${gewaehlt.length ? " · gewählt: " + escape(gewaehlt.join(", ")) : ""}</small>
        ${offeneFb ? `<span class="todo-chip warte">${offeneFb} Feedback</span>` : ""}</summary>
      ${s.todos.map((t) => todoTeamZeile(t, woche)).join("")}
      <form class="todo-neu" data-sid="${s.spieler_id}">
        <input type="text" maxlength="200" placeholder="Neues To-Do, z. B. Fangen mit zwei Händen" required />
        <button type="submit" class="primaer">+</button>
      </form></details>`;
  }).join("");
}
async function todoTeamSenden(pfad, body) {
  try {
    todoTeam = await api(pfad, "POST", body || {});
    renderTodoTeam();
    return true;
  } catch (err) { toast(todoFehler(err)); return false; }
}
$("#todo-team-inhalt").addEventListener("toggle", (e) => {
  const d = e.target;
  if (!d.classList || !d.classList.contains("todo-block")) return;
  const sid = +d.dataset.sid;
  if (d.open) todoAufgeklappt.add(sid); else todoAufgeklappt.delete(sid);
}, true);
$("#todo-team-inhalt").addEventListener("submit", async (e) => {
  const f = e.target.closest(".todo-neu");
  if (!f) return;
  e.preventDefault();
  const feld = f.querySelector("input");
  todoAufgeklappt.add(+f.dataset.sid);
  if (await todoTeamSenden("/api/todos", { spieler_id: +f.dataset.sid, text: feld.value })) toast("To-Do angelegt");
});
$("#todo-team-inhalt").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  const find = (name) => todoTeam.spielerinnen.flatMap((s) => s.todos).find((t) => t.id === +b.dataset[name]);
  if (b.dataset.todoFb) {
    const box = b.closest(".todo-fbbox");
    const ok = await todoTeamSenden(`/api/todos/${box.dataset.todo}/feedback`, {
      woche: box.dataset.woche, text: box.querySelector("textarea").value, ergebnis: b.dataset.todoFb });
    if (ok) toast(b.dataset.todoFb === "erledigt" ? "Abgehakt – die Spielerin sieht es ✓" : "Bleibt offen");
  } else if (b.dataset.todoDel) {
    const t = find("todoDel");
    if (t && confirm(`„${t.text}“ löschen? Auch der Verlauf dazu geht verloren.`)) {
      await todoTeamSenden(`/api/todos/${t.id}/loeschen`);
    }
  } else if (b.dataset.todoEdit) {
    const t = find("todoEdit");
    const neu = t && prompt("To-Do ändern:", t.text);
    if (neu && neu.trim() && neu !== t.text) await todoTeamSenden(`/api/todos/${t.id}/aendern`, { text: neu });
  } else if (b.dataset.todoOffen) {
    await todoTeamSenden(`/api/todos/${b.dataset.todoOffen}/aendern`, { status: "offen" });
  }
});
