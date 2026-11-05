import { api } from "../core/api.js";
import { POSITIONEN, positionenVon } from "./aufstellung.js";
import { setzeSpielerAlle, spielerAlle } from "./einteilung.js";
import { oeffneSpielerDetail } from "./spieler.js";
import { $, escape, toast } from "../core/ui.js";

// ------------------------------------------------------------------ Kader ----
function stufeVonElo(elo) {
  if (elo >= 1150) return "stark";
  if (elo <= 850) return "schwach";
  return "mittel";
}
export async function ladeKader() {
  setzeSpielerAlle(await api("/api/spieler"));
  const el = $("#kader-liste");
  el.innerHTML = "";
  for (const s of spielerAlle) {
    const zeile = document.createElement("div");
    zeile.className = "kader-zeile";
    const gespielt = s.spiele_gesamt > 0;
    zeile.innerHTML = `
      <div class="kopf klickbar" role="button" tabindex="0">
        <span class="name">${escape(s.name)}</span>
        <span class="meta">ELO ${s.elo} · ${s.spiele_gesamt} Sp. <span class="kopf-pfeil">›</span></span>
      </div>
      <div class="steuer">
        <label>Stufe
          <select class="f-stufe" ${gespielt ? "disabled title='nach Spielen gesperrt'" : ""}>
            <option value="stark" ${stufeVonElo(s.elo) === "stark" ? "selected" : ""}>stark</option>
            <option value="mittel" ${stufeVonElo(s.elo) === "mittel" ? "selected" : ""}>mittel</option>
            <option value="schwach" ${stufeVonElo(s.elo) === "schwach" ? "selected" : ""}>schwach</option>
          </select>
        </label>
        <label class="aktiv-label">aktiv
          <input type="checkbox" class="f-aktiv" ${s.aktiv ? "checked" : ""}>
        </label>
      </div>
      <div class="pos-wahl">
        <div class="pos-kopf">Position auf dem Feld <span>mehrere möglich</span></div>
        <div class="pos-chips"></div>
      </div>`;
    zeile.querySelector(".kopf").addEventListener("click", () => oeffneSpielerDetail(s, "kader"));
    const speichern = (feld) =>
      api("/api/spieler/" + s.id, "POST", feld).then(() => ladeKader());
    zeile.querySelector(".f-stufe").addEventListener("change", (e) =>
      speichern({ stufe: e.target.value }));
    zeile.querySelector(".f-aktiv").addEventListener("change", (e) =>
      speichern({ aktiv: e.target.checked }));

    // Angriffsposition als Mehrfachauswahl. Sie steuert die Feld-Ansicht und
    // (ueber "Tor") auch, wen die Team-Aufteilung als Torhueterin behandelt.
    const wahl = new Set(positionenVon(s));
    const chips = zeile.querySelector(".pos-chips");
    POSITIONEN.forEach((pos) => {
      const c = document.createElement("button");
      c.className = "pchip" + (wahl.has(pos.k) ? " aktiv" : "");
      c.innerHTML = `<b>${pos.k}</b><span>${pos.lang}</span>`;
      c.title = pos.lang;
      c.setAttribute("aria-pressed", wahl.has(pos.k) ? "true" : "false");
      c.addEventListener("click", () => {
        if (wahl.has(pos.k)) wahl.delete(pos.k); else wahl.add(pos.k);
        c.classList.toggle("aktiv", wahl.has(pos.k));
        c.setAttribute("aria-pressed", wahl.has(pos.k) ? "true" : "false");
        const text = POSITIONEN.filter((x) => wahl.has(x.k)).map((x) => x.lang).join("/");
        s.position_angriff = text;
        s.position = wahl.has("TW") ? "Tor" : "Feld";
        api("/api/spieler/" + s.id, "POST", { position_angriff: text })
          .then(() => toast(s.name.split(" ")[0] + ": " + (text || "Position offen")))
          .catch((e) => toast("Nicht gespeichert: " + e.message));
      });
      chips.appendChild(c);
    });
    el.appendChild(zeile);
  }
}
function anytypeStatus(text, ok) {
  const el = $("#anytype-status");
  if (!el) return;
  const zeit = new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  el.textContent = `${zeit} — ${text}`;
  el.classList.toggle("ok", ok === true);
  el.classList.toggle("fehler", ok === false);
  try { localStorage.setItem("anytypeStatus", JSON.stringify({ zeit, text, ok })); } catch (_) {}
}
export function restoreAnytypeStatus() {
  try {
    const raw = localStorage.getItem("anytypeStatus");
    if (!raw) return;
    const { zeit, text, ok } = JSON.parse(raw);
    const el = $("#anytype-status");
    el.textContent = `zuletzt ${zeit} — ${text}`;
    el.classList.toggle("ok", ok === true);
    el.classList.toggle("fehler", ok === false);
  } catch (_) {}
}
$("#btn-import").addEventListener("click", async () => {
  const btn = $("#btn-import");
  btn.disabled = true; anytypeStatus("Import läuft…", null);
  try {
    const r = await api("/api/anytype/import", "POST");
    anytypeStatus(`Import ok: ${r.neu} neu, ${r.aktualisiert} aktualisiert`, true);
    ladeKader();
  } catch (e) { anytypeStatus("Import fehlgeschlagen: " + e.message, false); }
  finally { btn.disabled = false; }
});
$("#btn-sync").addEventListener("click", async () => {
  const btn = $("#btn-sync");
  btn.disabled = true; anytypeStatus("Sync läuft…", null);
  try {
    const r = await api("/api/anytype/sync", "POST");
    anytypeStatus(`Sync ok: ${r.geschrieben} ELOs nach Anytype geschrieben`, true);
  } catch (e) { anytypeStatus("Sync fehlgeschlagen: " + e.message, false); }
  finally { btn.disabled = false; }
});
$("#form-spieler").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("#neu-name").value.trim();
  if (!name) return;
  try {
    await api("/api/spieler", "POST", {
      name,
      stufe: $("#neu-stufe").value,
      position: $("#neu-position").value,
    });
    $("#neu-name").value = "";
    ladeKader();
    toast(name + " hinzugefügt");
  } catch (err) { toast("Fehler: " + err.message); }
});
