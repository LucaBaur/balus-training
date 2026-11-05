import { initialen } from "../features/aufstellung.js";
import { escape } from "./ui.js";

// ------------------------------------------------------------ Portraits ----
// Die Fotos liegen unter /portraits/<slug>.jpg, die Zuordnung Name -> Datei in
// /portraits/index.json (gebaut von portraits.py). Zugeordnet wird ueber den
// Namen, nicht ueber die ID - so bleibt eine neue Datenbank-ID folgenlos.
// Der Index wird gespiegelt, damit die Fotos auch offline gleich da sind.
let portraitIndex = {};
const nameSlug = (name) =>
  (name || "").toLowerCase()
    .replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss")
    .normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
const portraitBild = (name) => portraitIndex[nameSlug(name)] || null;
export async function ladePortraitIndex() {
  try { portraitIndex = JSON.parse(localStorage.getItem("portraits") || "{}"); } catch (_) {}
  try {
    const r = await fetch("/portraits/index.json", { cache: "no-cache" });
    if (!r.ok) return;
    const daten = await r.json();
    portraitIndex = (daten && daten.spieler) || {};
    localStorage.setItem("portraits", JSON.stringify(portraitIndex));
  } catch (_) { /* offline: der gespiegelte Index reicht */ }
}
// Die Spielerinnen waehlen ihr Portrait selbst (eigenes Foto oder nur der
// Anfangsbuchstabe). Das steht je Spielerin in der Datenbank, nach ID:
//   { id, name, v: Version des eigenen Fotos (0 = keins), modus: "foto"|"initial" }
// Entscheidung in wappen(): modus "initial" -> Buchstabe; eigenes Foto -> das;
// sonst das Standardfoto aus index.json; sonst Buchstabe.
export let portraitInfo = {};
function portraitInfoSetzen(liste) {
  portraitInfo = {};
  (liste || []).forEach((p) => { portraitInfo[p.id] = p; });
}
export async function ladePortraitInfo() {
  try { portraitInfoSetzen(JSON.parse(localStorage.getItem("portraits-info") || "[]")); } catch (_) {}
  try {
    const r = await fetch("/api/portraits", { cache: "no-store" });
    if (!r.ok) return false;                         // nicht angemeldet: Spiegel genuegt
    const liste = await r.json();
    const neu = JSON.stringify(liste);
    const geaendert = neu !== localStorage.getItem("portraits-info");
    localStorage.setItem("portraits-info", neu);
    portraitInfoSetzen(liste);
    return geaendert;
  } catch (_) { return false; }                      // offline: Spiegel genuegt
}
function portraitUrl(sp) {
  const i = portraitInfo[sp.id];
  if (i && i.modus === "initial") return null;
  if (i && i.v) return `/api/portrait/${i.id}?v=${i.v}`;
  const datei = portraitBild(sp.name);
  return datei ? "/portraits/" + encodeURIComponent(datei) : null;
}
// Portrait im Wappen: Foto, wenn eins da ist - sonst die Initialen.
// Die Initialen bleiben im Markup und werden sichtbar, falls das Bild fehlt.
export function wappen(sp, groesse) {
  const t = [["#3467C9", "#16376F"], ["#2F62BD", "#122F5E"], ["#4A7BD4", "#1B3F7E"]][sp.id % 3];
  const url = portraitUrl(sp);
  const foto = url
    ? `<img class="pf" src="${url}" alt=""` +
      ` loading="lazy" decoding="async" onerror="this.remove()" />`
    : "";
  return `<span class="wappen" style="--w:${groesse}px;--c1:${t[0]};--c2:${t[1]}">` +
         `<span class="ini">${escape(initialen(sp.name))}</span>${foto}</span>`;
}
