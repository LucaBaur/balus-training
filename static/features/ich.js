import { ladeAnalysen, oeffneAnalyseDetail, statistikBlockHtml } from "./analysen.js";
import { videosOber } from "./home.js";
import { aktBenutzer, eigeneSpielerId, kopfPortraitZeichnen } from "../core/konto.js";
import { portraitInfo, wappen } from "../core/portraits.js";
import { gehe } from "../core/router.js";
import { positionsBadges } from "./spieler.js";
import { $, escape, toast } from "../core/ui.js";

// ------------------------------------------------------------------ Ich ----
// Die eigene Seite. Sie zeigt genau das, was einen selbst betrifft: Portrait,
// Positionen, Trainingsbeteiligung, Laufchallenge. Die Daten kommen aus
// demselben Endpunkt wie das Spieler-Detail - der Server laesst Spielerinnen
// dort ausdruecklich das EIGENE Profil sehen (und nur das).
export let ichDaten = null;
let ichAnalyse = [];
export async function ladeIch() {
  const el = $("#ich-inhalt");
  const sid = eigeneSpielerId();
  if (!sid) {
    el.innerHTML = '<p class="hinweis">Zu diesem Zugang gehört keine Spielerin – ' +
                   'darum gibt es hier nichts zu zeigen.</p>';
    return;
  }
  if (!ichDaten) el.innerHTML = '<p class="hinweis">Lädt…</p>';
  try {
    ichDaten = await Sync.apiOffline("/api/spieler/" + sid + "/spiele");
    ichAnalyse = await ladeAnalysen(sid);
    renderIch();
  } catch (_) {
    if (!ichDaten) {
      el.innerHTML = '<p class="hinweis">Offline – dein Profil wurde noch nicht ' +
                     'geladen. Einmal mit Netz öffnen, danach ist es auch offline da.</p>';
    }
  }
}
function renderIch() {
  const el = $("#ich-inhalt");
  const sp = ichDaten.spieler;
  const tr = ichDaten.training;
  const lc = ichDaten.laufchallenge;

  // Kopf: grosses Portrait, Name, Positionen.
  let html = `<div class="ich-kopf">${wappen(sp, 116)}
    <div class="ich-kopf-text">
      <h2>${escape(sp.name)}</h2>
      ${positionsBadges(sp) || '<span class="pk-leer">Für dich ist noch keine Position hinterlegt – sag deinem Trainer Bescheid.</span>'}
    </div></div>`;
  html += portraitKarteHtml(sp);

  // Trainingsbeteiligung: Quote gross, darunter der Balken und die Zahlen.
  if (tr && tr.erfasst) {
    const quote = tr.quote != null ? tr.quote : 0;
    const gezaehlt = tr.anwesend + tr.abgesagt;
    html += `<section class="ich-karte">
      <div class="ik-kopf">Trainingsbeteiligung</div>
      <div class="ik-quote"><span class="iq-zahl">${tr.quote != null ? quote + "%" : "–"}</span>
        <span class="iq-sub">${tr.anwesend} von ${gezaehlt} Trainings da</span></div>
      <div class="ik-balken"><span style="width:${quote}%"></span></div>
      <div class="ik-zahlen">
        <span><b>${tr.anwesend}</b> zugesagt</span>
        <span><b>${tr.abgesagt}</b> abgesagt</span>
        ${tr.unsicher ? `<span><b>${tr.unsicher}</b> unsicher</span>` : ""}
      </div></section>`;
  } else {
    html += `<section class="ich-karte"><div class="ik-kopf">Trainingsbeteiligung</div>
      <p class="hinweis">Noch keine Trainings erfasst.</p></section>`;
  }

  // Laufchallenge.
  if (lc) {
    const platz = lc.rang ? `Platz ${lc.rang}${lc.teilnehmer ? " von " + lc.teilnehmer : ""}` : "–";
    html += `<section class="ich-karte">
      <div class="ik-kopf">🏃 ${escape(lc.challenge || "Laufchallenge")}</div>
      <div class="ik-kacheln">
        <div class="ik-kachel"><span class="ikw">${lc.km}</span><span class="ikt">km gelaufen</span></div>
        <div class="ik-kachel"><span class="ikw">${lc.laeufe}</span><span class="ikt">Läufe</span></div>
        <div class="ik-kachel"><span class="ikw">${lc.rang || "–"}</span><span class="ikt">${platz}</span></div>
      </div></section>`;
  } else {
    html += `<section class="ich-karte"><div class="ik-kopf">🏃 Laufchallenge</div>
      <p class="hinweis">Für dich ist noch kein Ergebnis eingetragen.</p></section>`;
  }

  html += statistikBlockHtml(ichAnalyse);
  el.innerHTML = html;
  el.querySelectorAll("[data-spiel]").forEach((b) => b.addEventListener("click", () => {
    gehe(videosOber(), "videos");
    oeffneAnalyseDetail(+b.dataset.spiel);
  }));
  portraitKarteBinden(el, sp);
}
// ------------------------------------------------------ Mein Portrait ----
//  Die Spielerin waehlt selbst: eigenes Foto (zugeschnitten im Wappen-Format),
//  Anfangsbuchstabe statt Foto, oder zurueck zum Standardfoto. Der Zuschnitt
//  passiert hier im Browser (Canvas) - der Server bekommt ein fertiges, kleines
//  JPEG und braucht keine Bildbibliothek.
const PORTRAIT_B = 460, PORTRAIT_H = 552;               // 5:6 wie das Wappen
function portraitKarteHtml(sp) {
  if (aktBenutzer && aktBenutzer.ansicht_als) return "";   // Trainer-Ansicht ist nur lesend
  const i = portraitInfo[sp.id] || {};
  const initial = i.modus === "initial";
  return `<section class="ich-karte" id="portrait-karte">
    <div class="ik-kopf">Mein Portrait</div>
    <div class="pk-zeile">
      <div class="modus" role="group" aria-label="Darstellung">
        <button type="button" data-pmodus="foto" aria-pressed="${!initial}">Foto</button>
        <button type="button" data-pmodus="initial" aria-pressed="${initial}">Buchstabe</button>
      </div>
    </div>
    <div class="pk-zeile">
      <button type="button" class="sekundaer" id="portrait-neu">${i.v ? "Anderes Foto wählen" : "Eigenes Foto wählen"}</button>
      ${i.v ? '<button type="button" class="sekundaer" id="portrait-weg">Eigenes Foto entfernen</button>' : ""}
    </div>
    <p class="hinweis">${initial
      ? "Alle sehen von dir nur den Anfangsbuchstaben."
      : i.v ? "Alle sehen dein eigenes Foto – auch in der Aufstellung."
            : "Du hast kein eigenes Foto gewählt – es gilt das vom Trainer."}</p>
    <input type="file" id="portrait-datei" accept="image/*" hidden />
  </section>`;
}
function portraitKarteBinden(el, sp) {
  const karte = el.querySelector("#portrait-karte");
  if (!karte) return;
  const aktualisieren = () => { kopfPortraitZeichnen(); renderIch(); };
  const sende = async (pfad, opts) => {
    try {
      const r = await fetch(pfad, opts);
      if (!r.ok) throw new Error();
      return await r.json();
    } catch (_) { toast("Ging nicht – Verbindung prüfen und nochmal versuchen."); return null; }
  };
  const merke = (felder) => {
    portraitInfo[sp.id] = { ...(portraitInfo[sp.id] || { id: sp.id, name: sp.name, v: 0, modus: "foto" }), ...felder };
    try { localStorage.setItem("portraits-info", JSON.stringify(Object.values(portraitInfo))); } catch (_) {}
    aktualisieren();
  };

  karte.querySelectorAll("[data-pmodus]").forEach((b) => b.addEventListener("click", async () => {
    const modus = b.dataset.pmodus;
    const r = await sende("/api/ich/portrait-modus", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ modus }) });
    if (r) merke({ modus: r.modus });
  }));

  const datei = karte.querySelector("#portrait-datei");
  karte.querySelector("#portrait-neu").addEventListener("click", () => datei.click());
  datei.addEventListener("change", () => {
    const f = datei.files && datei.files[0];
    datei.value = "";
    if (f) portraitZuschneiden(f, async (blob) => {
      const fd = new FormData();
      fd.append("bild", blob, "portrait.jpg");
      const r = await sende("/api/ich/portrait", { method: "POST", body: fd });
      if (r) { merke({ v: r.v, modus: r.modus }); toast("Portrait gespeichert ✓"); }
    });
  });

  const weg = karte.querySelector("#portrait-weg");
  if (weg) weg.addEventListener("click", async () => {
    if (!confirm("Eigenes Foto entfernen?")) return;
    const r = await sende("/api/ich/portrait/loeschen", { method: "POST" });
    if (r) merke({ v: 0 });
  });
}
// Zuschnitt-Dialog: Bild mit dem Finger verschieben, per Regler zoomen. Die
// Vorschau steckt in der Wappenform - so sieht man genau, was uebrig bleibt.
async function portraitZuschneiden(datei, fertig) {
  let bild;
  try { bild = await createImageBitmap(datei, { imageOrientation: "from-image" }); }
  catch (_) { toast("Das Bild konnte nicht gelesen werden."); return; }

  const dlg = document.createElement("div");
  dlg.className = "pz-dialog";
  dlg.innerHTML = `<div class="pz-box" role="dialog" aria-label="Portrait zuschneiden">
      <div class="pz-vorschau"><canvas width="${PORTRAIT_B}" height="${PORTRAIT_H}"></canvas></div>
      <label class="pz-zoom">Ausschnitt
        <input type="range" min="1" max="3" step="0.01" value="1" aria-label="Zoom" /></label>
      <p class="hinweis">Mit dem Finger verschieben, mit dem Regler vergrößern.</p>
      <div class="pz-knoepfe">
        <button type="button" class="sekundaer" data-abbrechen>Abbrechen</button>
        <button type="button" class="primaer" data-ok>Übernehmen</button>
      </div></div>`;
  document.body.appendChild(dlg);
  const cv = dlg.querySelector("canvas"), g = cv.getContext("2d");
  const regler = dlg.querySelector("input");
  const basis = Math.max(PORTRAIT_B / bild.width, PORTRAIT_H / bild.height);   // "cover"
  let zoom = 1, ox = 0, oy = 0;          // Versatz des Bildmittelpunkts in Canvas-Pixeln

  const zeichnen = () => {
    const s = basis * zoom, w = bild.width * s, h = bild.height * s;
    // Bild muss die ganze Flaeche decken -> Versatz begrenzen
    const mx = (w - PORTRAIT_B) / 2, my = (h - PORTRAIT_H) / 2;
    ox = Math.max(-mx, Math.min(mx, ox));
    oy = Math.max(-my, Math.min(my, oy));
    g.fillStyle = "#fff"; g.fillRect(0, 0, PORTRAIT_B, PORTRAIT_H);
    g.drawImage(bild, (PORTRAIT_B - w) / 2 + ox, (PORTRAIT_H - h) / 2 + oy, w, h);
  };
  zeichnen();

  regler.addEventListener("input", () => { zoom = +regler.value; zeichnen(); });
  let griff = null;
  cv.addEventListener("pointerdown", (e) => { griff = { x: e.clientX, y: e.clientY }; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener("pointermove", (e) => {
    if (!griff) return;
    const f = PORTRAIT_B / cv.getBoundingClientRect().width;       // Bildschirm- -> Canvas-Pixel
    ox += (e.clientX - griff.x) * f; oy += (e.clientY - griff.y) * f;
    griff = { x: e.clientX, y: e.clientY };
    zeichnen();
  });
  const los = () => { griff = null; };
  cv.addEventListener("pointerup", los); cv.addEventListener("pointercancel", los);

  const zu = () => { bild.close && bild.close(); dlg.remove(); };
  dlg.querySelector("[data-abbrechen]").addEventListener("click", zu);
  dlg.addEventListener("click", (e) => { if (e.target === dlg) zu(); });
  dlg.querySelector("[data-ok]").addEventListener("click", () => {
    cv.toBlob((blob) => { zu(); if (blob) fertig(blob); }, "image/jpeg", 0.85);
  });
}
