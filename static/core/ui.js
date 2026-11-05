// ui.js ist ein Blattmodul: es importiert nichts. Fast jedes Modul ruft beim Laden `$` auf;
// haette ui.js selbst Importe (und damit moegliche Zyklen), koennte `$` dann noch fehlen.
export const $ = (sel) => document.querySelector(sel);
const WOCHENTAG_KURZ = ["SO", "MO", "DI", "MI", "DO", "FR", "SA"];
const MONAT_KURZ = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                    "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
// Heutiges Datum als YYYY-MM-DD in Ortszeit (toISOString() rechnet in UTC und
// kippt kurz nach Mitternacht auf den Vortag).
export const heuteIso = () => new Date().toLocaleDateString("sv-SE");
export function datumTeile(iso) {
  const d = new Date((iso || "") + "T12:00:00");
  if (!iso || isNaN(d)) return { wt: "", tag: iso || "" };
  return { wt: WOCHENTAG_KURZ[d.getDay()], tag: d.getDate() + ". " + MONAT_KURZ[d.getMonth()] };
}
export function anhaengen(ziel, el) { if (el) ziel.appendChild(el); }
// Leichtgewichtiges Markdown -> HTML (kein externes Lib, CSP-/offline-sicher).
// Deckt Überschriften, Listen, GFM-Tabellen, fett/kursiv/Code ab. Anytype-
// interne Bild-URLs (127.0.0.1) werden entfernt, weil sie ohne Anytype brechen.
export function mdLite(md) {
  if (!md) return "";
  md = md.replace(/!\[[^\]]*\]\((?:https?:\/\/127\.0\.0\.1:\d+|blob:)[^)]*\)/g, "");
  md = md.replace(/<br\s*\/?>/gi, " ");   // Anytype-Artefakt in Tabellenzellen
  const inline = (t) => escape(t)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  // Zellen einer Tabellenzeile: führendes/abschließendes | weg, an | trennen.
  const zellen = (zeile) => zeile.replace(/^\s*\|/, "").replace(/\|\s*$/, "")
    .split("|").map((c) => c.trim());
  const istTrenner = (z) => /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(z) && z.includes("-");

  const zeilen = md.split(/\r?\n/);
  let html = "", liste = null;
  const schliesse = () => { if (liste) { html += "</" + liste + ">"; liste = null; } };
  for (let i = 0; i < zeilen.length; i++) {
    const t = zeilen[i].trim();
    if (!t) { schliesse(); continue; }

    // GFM-Tabelle: Kopfzeile mit | und darunter eine Trennerzeile.
    if (t.startsWith("|") && i + 1 < zeilen.length && istTrenner(zeilen[i + 1])) {
      schliesse();
      const kopf = zellen(t);
      let tab = "<table><thead><tr>" +
        kopf.map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
      i += 2; // Kopf + Trenner überspringen
      while (i < zeilen.length && zeilen[i].trim().startsWith("|")) {
        const zs = zellen(zeilen[i].trim());
        tab += "<tr>" + zs.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
        i++;
      }
      i--; // die for-Schleife erhöht gleich wieder
      html += tab + "</tbody></table>";
      continue;
    }

    let m;
    if ((m = t.match(/^(#{1,4})\s+(.*)$/))) {
      schliesse(); const n = Math.min(m[1].length + 2, 6);
      html += `<h${n}>${inline(m[2])}</h${n}>`;
    } else if ((m = t.match(/^[-*]\s+(.*)$/))) {
      if (liste !== "ul") { schliesse(); html += "<ul>"; liste = "ul"; }
      html += `<li>${inline(m[1])}</li>`;
    } else if ((m = t.match(/^\d+\.\s+(.*)$/))) {
      if (liste !== "ol") { schliesse(); html += "<ol>"; liste = "ol"; }
      html += `<li>${inline(m[1])}</li>`;
    } else {
      schliesse(); html += `<p>${inline(t)}</p>`;
    }
  }
  schliesse();
  return html;
}
export function datumKurz(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "2-digit" });
}
// -------------------------------------------------------------- Hilfsmittel ----
let toastTimer = null;
export function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2600);
}
export function escape(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}
