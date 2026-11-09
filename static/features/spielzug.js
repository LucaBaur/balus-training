import { aktRolle } from "../core/konto.js";
import { escape } from "../core/ui.js";
import { baueFeld, zeigeStellung } from "./spielzug-feld.js";
import { starteEditor } from "./spielzug-editor.js";

// ----------------------------------------------------------- Spielzug-Ansicht --
//  Zeigt den Entscheidungsbaum eines Playbook-Spielzugs: Halbfeld mit Angriff (blau) und Abwehr
//  (rot), Schritt für Schritt durchklickbar. An einer Verzweigung wählt man, was die Abwehr macht;
//  jede Lösung kann ein Video aus der Spielanalyse haben. Die Logik (welcher Schritt, welche
//  Aufstellung) steht als reine Funktionen in spielzug-logik.js und ist dort getestet.
//  Trainer können die Ansicht hier anlegen und bearbeiten (spielzug-editor.js).

const L = window.SpielzugLogik;

function knopf(text, beiKlick) {
  const b = document.createElement("button");
  b.className = "sz-option";
  b.textContent = text;
  b.addEventListener("click", beiKlick);
  return b;
}

// Baut die Ansicht in `host`. Gibt false zurück, wenn die Seite keine Ansicht hat.
export async function zeigeSpielzug(host, seite, istNochAktuell) {
  host.innerHTML = "";
  let antwort = null;
  try { antwort = await Sync.apiOffline("/api/seiten/" + seite.id + "/ansicht"); } catch (_) { /* offline ohne Cache */ }
  if (istNochAktuell && !istNochAktuell()) return false;     // in der Zwischenzeit andere Seite geöffnet
  const baum = antwort && antwort.ansicht;
  const trainer = aktRolle === "trainer";
  const neuLaden = () => zeigeSpielzug(host, seite, istNochAktuell);

  if (!baum) {
    if (trainer) {
      const leiste = document.createElement("div");
      leiste.className = "sz-leiste";
      leiste.appendChild(knopf("＋ Spielzug-Ansicht anlegen", () => starteEditor(host, seite, null, neuLaden)));
      host.appendChild(leiste);
    }
    return false;
  }

  if (trainer) {
    const leiste = document.createElement("div");
    leiste.className = "sz-leiste";
    leiste.appendChild(knopf("✏️ Ansicht bearbeiten", () => starteEditor(host, seite, baum, neuLaden)));
    host.appendChild(leiste);
  }

  const wurzel = document.createElement("div");
  wurzel.className = "sz";
  const feldSpalte = document.createElement("div");
  feldSpalte.className = "sz-links";
  const info = document.createElement("div");
  info.className = "sz-rechts";
  wurzel.appendChild(feldSpalte);
  wurzel.appendChild(info);

  const feld = baueFeld();
  feldSpalte.appendChild(feld.svg);

  const steuerung = document.createElement("div");
  steuerung.className = "sz-steuerung";
  const zur = document.createElement("button");
  zur.textContent = "‹";
  zur.setAttribute("aria-label", "Vorheriger Schritt");
  const punkte = document.createElement("div");
  punkte.className = "sz-punkte";
  const vor = document.createElement("button");
  vor.textContent = "›";
  vor.setAttribute("aria-label", "Nächster Schritt");
  steuerung.appendChild(zur); steuerung.appendChild(punkte); steuerung.appendChild(vor);
  feldSpalte.appendChild(steuerung);

  const textKarte = document.createElement("div");
  textKarte.className = "sz-karte";
  const videoKarte = document.createElement("div");
  videoKarte.className = "sz-karte";
  info.appendChild(textKarte); info.appendChild(videoKarte);
  host.appendChild(wurzel);

  let s = L.start();

  function zeichne() {
    const { knoten, offen } = L.lauf(baum, s.wahl);
    const aufst = L.stellungen(knoten);
    const hier = Math.min(s.i, knoten.length - 1);
    zeigeStellung(feld, aufst[hier]);

    const node = knoten[hier];
    const opts = L.optionen(baum, s);
    const letzter = hier === knoten.length - 1 && !offen;
    textKarte.innerHTML =
      '<div class="sz-kopf">Schritt ' + (hier + 1) + " von " + knoten.length + (offen ? "+" : "") +
      (node.reaktion ? " · " + escape(node.reaktion) : "") + "</div>" +
      '<div class="sz-text">' + escape(node.text) + "</div>";
    if (opts.length) {
      const frage = document.createElement("div");
      frage.className = "sz-kopf sz-frage";
      frage.textContent = "Was macht die Abwehr?";
      textKarte.appendChild(frage);
      for (const o of opts) {
        const b = document.createElement("button");
        b.className = "sz-option";
        b.innerHTML = escape(o.reaktion || "Weiter") + (o.hatVideo ? ' <span class="sz-hatvideo" title="Video vorhanden">▶</span>' : "");
        b.addEventListener("click", () => { s = L.waehle(baum, s, o.n); zeichne(); });
        textKarte.appendChild(b);
      }
    }

    punkte.innerHTML = "";
    knoten.forEach((_, i) => {
      const p = document.createElement("button");
      p.className = "sz-punkt" + (i === hier ? " aktiv" : "");
      p.setAttribute("aria-label", "Schritt " + (i + 1));
      p.addEventListener("click", () => { s = { wahl: s.wahl, i }; zeichne(); });
      punkte.appendChild(p);
    });
    if (offen) {
      const mehr = document.createElement("span");
      mehr.className = "sz-offen";
      mehr.textContent = "⋯";
      punkte.appendChild(mehr);
    }
    zur.disabled = s.i === 0;
    vor.disabled = hier >= knoten.length - 1;

    videoKarte.innerHTML = "";
    if (node.video_clip_id != null) {
      videoKarte.innerHTML = '<div class="sz-kopf">So haben wir es im Spiel gelöst</div>';
      const v = document.createElement("video");
      v.controls = true; v.playsInline = true; v.preload = "metadata";
      v.src = "/api/spielzug-schritte/" + node.id + "/video";
      videoKarte.appendChild(v);
      videoKarte.hidden = false;
    } else if (letzter && aktRolle === "trainer") {
      videoKarte.innerHTML = '<div class="sz-kopf">Video</div><div class="hinweis">Noch kein Video zu dieser Lösung verknüpft. Unter „Ansicht bearbeiten“ eins auswählen.</div>';
      videoKarte.hidden = false;
    } else {
      videoKarte.hidden = true;
    }
  }

  zur.addEventListener("click", () => { s = L.zurueck(baum, s); zeichne(); });
  vor.addEventListener("click", () => { s = L.weiter(baum, s); zeichne(); });
  zeichne();
  return true;
}
