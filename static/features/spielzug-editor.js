import { api } from "../core/api.js";
import { toast } from "../core/ui.js";
import { baueFeld, zeigeStellung, setzePos, feldPunkt } from "./spielzug-feld.js";

// ---------------------------------------------------------- Spielzug-Editor --
//  Trainer legen einen Spielzug als Entscheidungsbaum an: Schritt für Schritt Spielerinnen und Abwehr
//  per Finger/Maus ziehen, Text schreiben, Abwehr-Reaktionen (Verzweigungen) anlegen, zu jeder Lösung
//  ein Video aus der Spielanalyse wählen. Der Baum wird nur im Speicher verändert; erst "Speichern"
//  schickt ihn als Ganzes an den Server (POST /api/seiten/{id}/ansicht), "Abbrechen" verwirft alles.
//  Alle Änderungen am Baum laufen über die getesteten Funktionen aus spielzug-logik.js.

const L = window.SpielzugLogik;
const AMPEL = { gruen: "grün", gelb: "gelb", rot: "rot" };

// Kleiner Baukasten für DOM-Elemente (Text immer als Textknoten, nie als HTML).
function el(tag, attrs = {}, ...kinder) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "value") e.value = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kinder.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}

// Der Server antwortet mit {"detail": "..."}; api() reicht das als Text durch.
function fehlertext(e) {
  try { return JSON.parse(e.message).detail || e.message; } catch (_) { return e.message; }
}

const kurz = (t, n = 38) => (t.length > n ? t.slice(0, n - 1) + "…" : t);
function datumKurz(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  return m ? m[3] + "." + m[2] + "." : iso || "";
}
const clipText = (c) => [c.gegner, datumKurz(c.datum), c.name, AMPEL[c.ampel] || c.ampel].filter(Boolean).join(" · ");

// vorhanden = gespeicherter Baum (oder null: neu anlegen). fertig() läuft nach Speichern/Abbrechen.
export async function starteEditor(host, seite, vorhanden, fertig) {
  if (!Sync.serverOnline) { toast("Bearbeiten geht nur online."); return; }
  let clips = [];
  try { clips = await api("/api/spielzug-clips"); } catch (_) { toast("Die Videoliste konnte nicht geladen werden."); }

  let baum = vorhanden ? JSON.parse(JSON.stringify(vorhanden)) : L.neuerBaum();
  const startJson = JSON.stringify(baum);
  let s = L.zustandFuer(baum, baum.id);
  let clipListe = false;

  const aktuell = () => L.aktuell(baum, s);
  const geaendert = () => JSON.stringify(baum) !== startJson;

  // ---------------------------------------------------------------- Aufbau
  host.innerHTML = "";
  const feld = baueFeld();
  const wurzel = el("div", { class: "sz sz-edit" });
  const links = el("div", { class: "sz-links" });
  const rechts = el("div", { class: "sz-rechts" });
  const steuerung = el("div", { class: "sz-steuerung" });
  const gliederungBox = el("div", { class: "sz-karte" });
  const panel = el("div", { class: "sz-karte" });
  const leiste = el("div", { class: "sz-leiste sz-speichern" });
  const hinweis = el("div", { class: "hinweis sz-hilfe" },
    "Spielerinnen und Abwehr mit dem Finger oder der Maus ziehen. Was du in einem Schritt nicht verschiebst, bleibt wie im Schritt davor.");
  // Reihenfolge so, dass sie auch einspaltig (Handy) passt: Feld, Schrittwahl, Bearbeiten, Speichern, Gliederung.
  links.append(feld.svg, steuerung, hinweis);
  rechts.append(panel, leiste, gliederungBox);
  wurzel.append(links, rechts);
  host.appendChild(wurzel);

  // ----------------------------------------------------------- Ziehen
  function macheZiehbar(seiteName, name, g) {
    g.classList.add("sz-ziehbar");
    let aktiv = false;
    let bewegt = false;
    g.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      aktiv = true; bewegt = false;
      g.setPointerCapture(e.pointerId);
      g.classList.add("ziehen");
    });
    g.addEventListener("pointermove", (e) => {
      if (!aktiv) return;
      bewegt = true;
      const q = L.begrenze(feldPunkt(feld.svg, e));
      setzePos(g, q);
      if (seiteName === "angriff" && L.stellungFuer(baum, aktuell().id).ball === name) {
        setzePos(feld.ball, [q[0] + 14, q[1] - 10]);
      }
    });
    const ende = (e, uebernehmen) => {
      if (!aktiv) return;
      aktiv = false;
      g.classList.remove("ziehen");
      if (uebernehmen && bewegt) {
        baum = L.setzePosition(baum, aktuell().id, seiteName, name, feldPunkt(feld.svg, e));
      }
      zeichne();
    };
    g.addEventListener("pointerup", (e) => ende(e, true));
    g.addEventListener("pointercancel", (e) => ende(e, false));
  }
  for (const k in feld.angriff) macheZiehbar("angriff", k, feld.angriff[k]);
  for (const k in feld.abwehr) macheZiehbar("abwehr", k, feld.abwehr[k]);

  // ------------------------------------------------------- Bearbeitungen
  function waehleKnoten(id) {
    const z = L.zustandFuer(baum, id);
    if (z) { s = z; zeichne(); }
  }
  function neuerSchritt() {
    const r = L.fuegeKindEin(baum, aktuell().id);
    if (r.neueId === null) {
      toast("Mehr geht nicht: höchstens " + L.MAX_AESTE + " Abwehr-Reaktionen je Verzweigung und " + L.MAX_TIEFE + " Schritte hintereinander.");
      return;
    }
    baum = r.baum;
    waehleKnoten(r.neueId);
  }
  function schrittLoeschen() {
    const n = aktuell();
    if (!confirm("Diesen Schritt" + (n.kinder.length ? " samt allem danach" : "") + " löschen?")) return;
    const pfad = L.pfadZu(baum, n.id);
    baum = L.loescheKnoten(baum, n.id);
    waehleKnoten(pfad[pfad.length - 2].id);
  }
  function eltern(n) {
    const pfad = L.pfadZu(baum, n.id);
    return pfad && pfad.length > 1 ? pfad[pfad.length - 2] : null;
  }

  async function speichern() {
    if (!Sync.serverOnline) { toast("Speichern geht nur online."); return; }
    try {
      await api("/api/seiten/" + seite.id + "/ansicht", "POST", { ansicht: baum });
      await Sync.frischHolen("/api/seiten/" + seite.id + "/ansicht");
      toast("Spielzug gespeichert ✓");
      fertig();
    } catch (e) { toast(fehlertext(e)); }
  }
  async function ansichtLoeschen() {
    if (!confirm("Die ganze Spielzug-Ansicht (alle Schritte, Abwehr-Reaktionen und Videoverknüpfungen) löschen? Der Text der Seite bleibt.")) return;
    try {
      await api("/api/seiten/" + seite.id + "/ansicht", "POST", { ansicht: null });
      await Sync.frischHolen("/api/seiten/" + seite.id + "/ansicht");
      toast("Ansicht gelöscht ✓");
      fertig();
    } catch (e) { toast(fehlertext(e)); }
  }
  function abbrechen() {
    if (geaendert() && !confirm("Änderungen verwerfen?")) return;
    fertig();
  }

  // ------------------------------------------------------------ Zeichnen
  function zeichneSteuerung() {
    const n = aktuell();
    const pfad = L.pfadZu(baum, n.id);
    const vater = eltern(n);
    steuerung.replaceChildren(
      el("button", { "aria-label": "Zum Schritt davor", disabled: !vater, onclick: () => waehleKnoten(vater.id) }, "‹"),
      el("div", { class: "sz-punkte" }, `Schritt ${pfad.length}`),
      el("button", { "aria-label": "Zum nächsten Schritt", disabled: !n.kinder.length, onclick: () => waehleKnoten(n.kinder[0].id) }, "›"));
  }

  function zeichneGliederung() {
    const n0 = aktuell();
    const zeilen = [];
    (function geh(n, einzug) {
      const marke = (n.reaktion ? "↳ " + n.reaktion + ": " : "") + kurz(n.text) + (n.video_clip_id != null ? " ▶" : "");
      zeilen.push(el("button", {
        class: "sz-gl" + (n.id === n0.id ? " aktiv" : ""),
        style: "padding-left:" + (10 + Math.min(einzug, 5) * 14) + "px",
        onclick: () => waehleKnoten(n.id),
      }, marke));
      n.kinder.forEach((k) => geh(k, einzug + (n.kinder.length > 1 ? 1 : 0)));
    })(baum, 0);
    gliederungBox.replaceChildren(el("div", { class: "sz-kopf" }, "Gliederung"), ...zeilen);
  }

  function zeichnePanel() {
    const n = aktuell();
    const vater = eltern(n);
    const verzweigt = vater && vater.kinder.length > 1;
    const stellung = L.stellungFuer(baum, n.id);
    const teile = [];

    teile.push(el("div", { class: "sz-kopf" }, verzweigt ? "Was macht die Abwehr?" : "Beschreibung dieses Schritts"));
    if (verzweigt) {
      teile.push(el("input", {
        type: "text", maxlength: "80", value: n.reaktion || "", placeholder: "z. B. D3 tritt raus",
        "aria-label": "Beschriftung der Abwehr-Reaktion",
        oninput: (e) => { baum = L.setze(baum, n.id, { reaktion: e.target.value }); },
        onchange: zeichneGliederung,
      }));
    }
    teile.push(el("textarea", {
      rows: "4", maxlength: "1000", value: n.text, placeholder: "Was passiert in diesem Schritt?",
      "aria-label": "Text zum Schritt",
      oninput: (e) => { baum = L.setze(baum, n.id, { text: e.target.value }); },
      onchange: zeichneGliederung,
    }));

    const ball = el("select", {
      "aria-label": "Ball bei",
      onchange: (e) => { baum = L.setzeBall(baum, n.id, e.target.value); zeichne(); },
    }, Object.keys(L.ANGRIFF_GRUND).map((k) => el("option", { value: k, selected: k === stellung.ball }, k)));
    teile.push(el("label", { class: "sz-zeile" }, "Ball bei ", ball));

    if (n.kinder.length > 1) {
      teile.push(el("div", { class: "hinweis" }, `Hier verzweigt sich der Spielzug: ${n.kinder.length} Abwehr-Reaktionen (unter „Gliederung“).`));
    }
    teile.push(el("button", { class: "sz-option", onclick: neuerSchritt },
      n.kinder.length ? "＋ Weitere Abwehr-Reaktion" : "＋ Schritt danach"));
    teile.push(el("button", {
      class: "sz-option",
      onclick: () => { baum = L.setzeZurueck(baum, n.id); zeichne(); },
    }, "Positionen dieses Schritts zurücksetzen"));
    if (vater) teile.push(el("button", { class: "sz-option sz-gefahr", onclick: schrittLoeschen }, "Schritt löschen"));

    // Video: gehört zu einer Lösung, also zum Ende eines Wegs.
    if (!n.kinder.length) {
      const gewaehlt = n.video_clip_id != null ? clips.find((c) => c.clip_id === n.video_clip_id) : null;
      teile.push(el("div", { class: "sz-kopf sz-frage" }, "Video zu dieser Lösung"));
      teile.push(el("div", { class: "sz-text" },
        n.video_clip_id == null ? "Noch keins verknüpft." : gewaehlt ? clipText(gewaehlt) : "Clip Nr. " + n.video_clip_id));
      teile.push(el("button", { class: "sz-option", onclick: () => { clipListe = !clipListe; zeichnePanel(); } },
        clipListe ? "Auswahl schließen" : n.video_clip_id == null ? "Video aus der Spielanalyse wählen" : "Anderes Video wählen"));
      if (clipListe) {
        if (!clips.length) teile.push(el("div", { class: "hinweis" }, "In der Spielanalyse gibt es noch keine Spielzug-Clips."));
        for (const c of clips) {
          teile.push(el("button", {
            class: "sz-option sz-clip" + (c.clip_id === n.video_clip_id ? " aktiv" : ""),
            onclick: () => { baum = L.setze(baum, n.id, { video_clip_id: c.clip_id }); clipListe = false; zeichne(); },
          }, clipText(c)));
        }
      }
      if (n.video_clip_id != null) {
        teile.push(el("button", {
          class: "sz-option",
          onclick: () => { baum = L.setze(baum, n.id, { video_clip_id: null }); zeichne(); },
        }, "Video entfernen"));
      }
    }
    panel.replaceChildren(...teile);
  }

  function zeichneLeiste() {
    leiste.replaceChildren(
      el("button", { class: "primaer", onclick: speichern }, "Speichern"),
      el("button", { onclick: abbrechen }, "Abbrechen"),
      vorhanden ? el("button", { class: "sz-gefahr", onclick: ansichtLoeschen }, "Ansicht löschen") : null);
  }

  // Alles, was von Baum und Auswahl abhängt. Beim Tippen NICHT aufgerufen (der Cursor bliebe sonst nicht).
  function zeichne() {
    zeigeStellung(feld, L.stellungFuer(baum, aktuell().id));
    zeichneSteuerung();
    zeichneGliederung();
    zeichnePanel();
  }

  zeichneLeiste();
  zeichne();
}
