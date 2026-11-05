import { api } from "../core/api.js";
import { pushAktivieren, pushDeaktivieren, pushStatus, pushTest } from "./push.js";
import { icon } from "../core/router.js";
import { $, escape, toast } from "../core/ui.js";

// ---- Profil -> Mitteilungen: Gerät ein/aus und welche Arten kommen ----
export async function ladeMitteilungen() { await renderMitteilungen(); }
export async function renderMitteilungen() {
  const el = $("#mitteilungen-inhalt");
  const st = await pushStatus();
  let kopf;
  if (st === "aktiv") {
    kopf = `<div class="mt-karte"><div class="mt-status an">${icon("check")} Auf diesem Gerät eingeschaltet</div>
      <div class="mt-knoepfe"><button type="button" data-push="test">Testnachricht</button><button type="button" data-push="aus">Ausschalten</button></div></div>`;
  } else if (st === "blockiert") {
    kopf = `<div class="mt-karte"><div class="mt-status aus">Im Browser blockiert</div>
      <p class="hinweis">Erlaube Mitteilungen für diese App in den Einstellungen deines Geräts oder Browsers und öffne diese Seite danach noch einmal.</p></div>`;
  } else if (st === "nicht_unterstuetzt") {
    kopf = `<div class="mt-karte"><div class="mt-status aus">Hier nicht möglich</div>
      <p class="hinweis">Auf dem iPhone klappt das nur, wenn die App auf dem Home-Bildschirm liegt: Teilen-Symbol antippen, „Zum Home-Bildschirm“ wählen und die App von dort öffnen.</p></div>`;
  } else {
    kopf = `<div class="mt-karte"><div class="mt-status aus">Auf diesem Gerät aus</div>
      <button type="button" class="primaer gross" data-push="an">Mitteilungen einschalten</button></div>`;
  }
  let arten = null;
  try { arten = (await api("/api/push/einstellungen")).arten; } catch (_) {}
  const liste = arten
    ? `<h3 class="mt-titel">Was du bekommst</h3>` + arten.map((a) => `<label class="mt-art">
        <span><b>${escape(a.label)}</b><small>${escape(a.text)}</small></span>
        <input type="checkbox" class="mt-schalter" role="switch" data-art="${escape(a.key)}"${a.an ? " checked" : ""}></label>`).join("")
    : '<p class="hinweis">Was du bekommst, lässt sich nur mit Verbindung einstellen.</p>';
  el.innerHTML = kopf + liste;
  const knopf = (k) => el.querySelector(`[data-push="${k}"]`);
  if (knopf("an")) knopf("an").addEventListener("click", pushAktivieren);
  if (knopf("test")) knopf("test").addEventListener("click", pushTest);
  if (knopf("aus")) knopf("aus").addEventListener("click", pushDeaktivieren);
}
$("#mitteilungen-inhalt").addEventListener("change", async (e) => {
  const c = e.target.closest("[data-art]");
  if (!c) return;
  try {
    await api("/api/push/einstellungen", "POST", { art: c.dataset.art, an: c.checked });
    toast(c.checked ? "Eingeschaltet ✓" : "Ausgeschaltet ✓");
  } catch (err) {
    c.checked = !c.checked;                         // Server hat es nicht angenommen: Schalter zurück
    toast("Nicht gespeichert – Verbindung prüfen.");
  }
});
