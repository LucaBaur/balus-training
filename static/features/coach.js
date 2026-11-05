import { api } from "../core/api.js";
import { $, escape, toast } from "../core/ui.js";

// ---------------------------------------------------------------- Coach ----
let llmVerlauf = [];          // {role, content} fuer das Modell
let coachGestartet = false;
let chatDatumCursor = null;   // lokales Datum des zuletzt gerenderten Bubbles
let mediaRecorder = null;
let audioChunks = [];
const GRUSS = "Hi! Beschreib dein Training (tippen oder 🎤) – zum Beispiel: 90 Minuten, 14 Spielerinnen, Schwerpunkt Tempospiel. Ich frage nach, wenn etwas fehlt, und hänge den Plan auf Wunsch direkt ans Training.";
export async function starteCoach() {
  if (coachGestartet) return;
  coachGestartet = true;
  chatEl().innerHTML = "";
  chatDatumCursor = null;
  llmVerlauf = [];
  let hist = [];
  try { hist = await api("/api/chat"); } catch (e) {}
  if (!hist.length) { botBubble(GRUSS); return; }
  for (const m of hist) {
    if (m.rolle === "plan") zeigePlan(m.titel, m.text, m.ts);
    else bubble(m.rolle, m.text, { ts: m.ts, zeit: m.rolle !== "info" });
    if (m.rolle === "user") llmVerlauf.push({ role: "user", content: m.text });
    if (m.roh) llmVerlauf.push({ role: "assistant", content: m.roh });
  }
}
function chatEl() { return $("#chat-verlauf"); }
// Nachricht best-effort serverseitig speichern (blockiert den Chat nie).
function persist(rolle, text, extra) {
  api("/api/chat", "POST", Object.assign({ rolle, text }, extra || {})).catch(() => {});
}
function lokalesDatum(ts) {
  const d = ts ? new Date(ts) : new Date();
  return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate();
}
function datumsLabel(ts) {
  const d = new Date(ts), heute = new Date();
  const gestern = new Date(); gestern.setDate(heute.getDate() - 1);
  const gleich = (a, b) => a.toDateString() === b.toDateString();
  if (gleich(d, heute)) return "Heute";
  if (gleich(d, gestern)) return "Gestern";
  if ((heute - d) / 86400000 < 7) return d.toLocaleDateString("de-DE", { weekday: "long" });
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}
// Bei Datumswechsel einen WhatsApp-artigen Trenner einfuegen.
function ensureDivider(ts) {
  const tag = lokalesDatum(ts);
  if (tag === chatDatumCursor) return;
  chatDatumCursor = tag;
  const div = document.createElement("div");
  div.className = "chat-tag";
  div.innerHTML = `<span>${escape(datumsLabel(ts))}</span>`;
  chatEl().appendChild(div);
}
function bubble(rolle, text, opt) {
  opt = opt || {};
  const ts = opt.ts || new Date().toISOString();
  ensureDivider(ts);
  const div = document.createElement("div");
  div.className = "bubble " + rolle;
  if (text) {
    const t = document.createElement("span");
    t.className = "b-text";
    t.textContent = text;
    div.appendChild(t);
  }
  if (opt.zeit !== false) {
    const z = document.createElement("span");
    z.className = "b-zeit";
    z.textContent = new Date(ts).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    div.appendChild(z);
  }
  chatEl().appendChild(div);
  chatEl().scrollTop = chatEl().scrollHeight;
  return div;
}
function userBubble(t, opt) { return bubble("user", t, opt); }
function botBubble(t, opt) { return bubble("bot", t, opt); }
function infoBubble(t) { return bubble("info", t, { zeit: false }); }
async function coachSenden(text) {
  text = (text || "").trim();
  if (!text) return;
  userBubble(text);
  persist("user", text);
  llmVerlauf.push({ role: "user", content: text });
  $("#chat-text").value = "";
  const tip = botBubble("…", { zeit: false });
  try {
    const r = await api("/api/trainer/chat", "POST", { verlauf: llmVerlauf });
    tip.remove();
    if (r.roh) llmVerlauf.push({ role: "assistant", content: r.roh });
    if (r.typ === "rueckfrage") {
      const t = "Dazu brauche ich noch:\n" + (r.fragen || []).map((f) => "• " + f).join("\n");
      botBubble(t);
      persist("bot", t, { roh: r.roh });
    } else if (r.typ === "plan") {
      if (r.warnung) { infoBubble(r.warnung); persist("info", r.warnung); }
      zeigePlan(r.titel, r.markdown);
      persist("plan", r.markdown, { titel: r.titel, roh: r.roh });
    } else {
      const t = r.text || "(keine Antwort)";
      botBubble(t);
      persist("bot", t, { roh: r.roh });
    }
  } catch (e) {
    tip.remove();
    infoBubble("Fehler: " + e.message);
  }
}
function zeigePlan(titel, markdown, ts) {
  const div = bubble("bot", "", { ts, zeit: false });
  const pre = document.createElement("div");
  pre.className = "plan";
  pre.textContent = markdown;
  div.appendChild(pre);
  const btn = document.createElement("button");
  btn.className = "primaer plan-btn";
  btn.textContent = "✅ Passt – ans Training";
  btn.addEventListener("click", () => zeigeAnlageOptionen(div, btn, titel, markdown));
  div.appendChild(btn);
  const z = document.createElement("span");
  z.className = "b-zeit";
  z.textContent = new Date(ts || Date.now()).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  div.appendChild(z);
  chatEl().scrollTop = chatEl().scrollHeight;
}
async function zeigeAnlageOptionen(div, btn, titel, markdown) {
  btn.disabled = true;
  btn.textContent = "…";
  let trainings = [];
  try { trainings = await api("/api/trainings"); } catch (e) {}
  const heute = new Date().toISOString().slice(0, 10);
  const kommend = (trainings || [])
    .filter((t) => t.datum && t.datum >= heute)
    .sort((a, b) => a.datum.localeCompare(b.datum));
  btn.remove();
  const box = document.createElement("div");
  box.className = "anlage-optionen";
  const frage = document.createElement("div");
  frage.className = "anlage-frage";
  frage.textContent = kommend.length
    ? "An welches Training anhängen?"
    : "Kein anstehendes Training – neu anlegen?";
  box.appendChild(frage);
  kommend.forEach((t) => {
    const b = document.createElement("button");
    b.className = "opt-btn";
    const zusatz = t.hat_plan ? " · ersetzt Plan" : "";
    b.textContent = "→ " + (t.label || t.datum) + " (" + (t.anwesend || 0) + " Zusagen)" + zusatz;
    b.addEventListener("click", () =>
      planSpeichern({ markdown, training_id: t.id }, box,
        "an " + (t.label || t.datum) + " angehängt"));
    box.appendChild(b);
  });
  const neu = document.createElement("button");
  neu.className = "opt-btn";
  neu.textContent = "→ Neues Training (Datum)";
  neu.addEventListener("click", () => {
    const datum = prompt("Datum des neuen Trainings (JJJJ-MM-TT)", heute);
    if (datum) planSpeichern({ markdown, titel, datum }, box,
      "als neues Training (" + datum + ") angelegt");
  });
  box.appendChild(neu);
  div.appendChild(box);
  chatEl().scrollTop = chatEl().scrollHeight;
}
// Plan nativ ans Training hängen: bestehendes -> /plan, sonst Training anlegen.
async function planSpeichern(payload, box, erfolg) {
  box.querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    if (payload.training_id != null) {
      await api("/api/trainings/" + payload.training_id + "/plan", "POST",
        { markdown: payload.markdown });
    } else {
      await api("/api/trainings", "POST",
        { datum: payload.datum, titel: payload.titel || "", markdown: payload.markdown });
    }
    infoBubble("✅ Plan " + erfolg + ".");
    box.remove();
    Sync.prefetchAlles(true).catch(() => {});   // Trainings-Cache auffrischen
  } catch (e) {
    box.querySelectorAll("button").forEach((b) => (b.disabled = false));
    infoBubble("Speichern fehlgeschlagen: " + e.message);
  }
}
$("#btn-senden").addEventListener("click", () => coachSenden($("#chat-text").value));
$("#chat-text").addEventListener("keydown", (e) => {
  if (e.key === "Enter") coachSenden($("#chat-text").value);
});
$("#btn-chat-loeschen").addEventListener("click", async () => {
  if (!confirm("Gesamten Chat-Verlauf löschen?")) return;
  try {
    await api("/api/chat/loeschen", "POST");
    coachGestartet = false;
    starteCoach();
    toast("Verlauf gelöscht");
  } catch (e) { toast("Fehler: " + e.message); }
});
$("#btn-mic").addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    infoBubble("Mikrofon nicht verfügbar (nur über HTTPS).");
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => { if (e.data.size) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      $("#btn-mic").classList.remove("aufnahme");
      const typ = mediaRecorder.mimeType || "audio/webm";
      const ext = typ.includes("mp4") ? "mp4" : typ.includes("ogg") ? "ogg" : "webm";
      const blob = new Blob(audioChunks, { type: typ });
      const fd = new FormData();
      fd.append("datei", blob, "audio." + ext);
      const tip = botBubble("🎧 transkribiere…");
      try {
        const res = await fetch("/api/trainer/audio", { method: "POST", body: fd });
        tip.remove();
        if (!res.ok) throw new Error(await res.text());
        const { text } = await res.json();
        $("#chat-text").value = text;
        $("#chat-text").focus();
      } catch (e) {
        tip.remove();
        infoBubble("Transkription fehlgeschlagen: " + e.message);
      }
    };
    mediaRecorder.start();
    $("#btn-mic").classList.add("aufnahme");
    infoBubble("🎤 Aufnahme läuft – zum Stoppen nochmal 🎤 tippen.");
  } catch (e) {
    infoBubble("Mikrofon-Zugriff verweigert: " + e.message);
  }
});
