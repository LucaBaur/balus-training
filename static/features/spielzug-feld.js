import { escape } from "../core/ui.js";

// ------------------------------------------------------------ Spielzug: das Feld --
//  Das Halbfeld mit Spielerinnen und Ball als SVG. Gemeinsam genutzt vom Viewer (spielzug.js) und vom
//  Editor (spielzug-editor.js). Die Maße kommen aus der getesteten Geometrie in spielzug-logik.js.

const L = window.SpielzugLogik;
const SVG_NS = "http://www.w3.org/2000/svg";

const punkte = (p) => p.map((q) => q[0].toFixed(1) + "," + q[1].toFixed(1)).join(" ");

// Halbes Handballfeld in Metern gedacht (1 m = 20 Einheiten): Torraum mit gerader Mitte, gestrichelte
// Freiwurflinie, Siebenmetermarke, Torwartlinie, Seitenaus.
function feldSvg() {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "-8 -22 416 330");
  svg.setAttribute("class", "sz-feld");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Halbes Handballfeld mit Angriff und Abwehr");
  const sechs = L.linienPunkte(L.SECHS_METER);
  const neun = L.linienPunkte(L.NEUN_METER);
  const m7 = L.SIEBEN_METER;
  svg.innerHTML =
    '<polygon points="' + punkte(sechs) + '" class="sz-torraum"/>' +
    '<polyline points="' + punkte(neun) + '" class="sz-9m"/>' +
    '<polyline points="' + punkte(sechs) + '" class="sz-6m"/>' +
    '<path d="M 0 300 V 0 H 400 V 300" class="sz-linie"/>' +
    '<rect x="' + L.PFOSTEN_L + '" y="-12" width="' + (L.PFOSTEN_R - L.PFOSTEN_L) + '" height="12" class="sz-tor"/>' +
    '<line x1="' + m7.x1 + '" y1="' + m7.y + '" x2="' + m7.x2 + '" y2="' + m7.y + '" class="sz-7m"/>' +
    '<line x1="196" y1="80" x2="204" y2="80" class="sz-7m"/>';
  return svg;
}

function spielerin(svg, name, klasse) {
  const g = document.createElementNS(SVG_NS, "g");
  g.setAttribute("class", "sz-sp " + klasse);
  // Der unsichtbare grosse Kreis macht die Spielerin am Handy leichter zu treffen (Zielgroesse).
  g.innerHTML = '<circle r="20" class="sz-treffer"></circle><circle r="13" class="sz-kreis"></circle>' +
    '<text text-anchor="middle" dy="4">' + escape(name) + "</text>";
  svg.appendChild(g);
  return g;
}

export function setzePos(g, xy) {
  g.style.transform = "translate(" + xy[0] + "px," + xy[1] + "px)";
}

// {svg, angriff:{LA:<g>..}, abwehr:{D1:<g>..}, ball:<circle>}
export function baueFeld() {
  const svg = feldSvg();
  const angriff = {};
  const abwehr = {};
  for (const k of Object.keys(L.ABWEHR_GRUND)) abwehr[k] = spielerin(svg, k, "abwehr");
  for (const k of Object.keys(L.ANGRIFF_GRUND)) angriff[k] = spielerin(svg, k, "angriff");
  const ball = document.createElementNS(SVG_NS, "circle");
  ball.setAttribute("r", "6");
  ball.setAttribute("class", "sz-ball");
  svg.appendChild(ball);
  return { svg, angriff, abwehr, ball };
}

// Alle Spielerinnen und den Ball auf eine (vollständige) Aufstellung setzen.
export function zeigeStellung(feld, st) {
  for (const k in feld.angriff) setzePos(feld.angriff[k], st.angriff[k]);
  for (const k in feld.abwehr) setzePos(feld.abwehr[k], st.abwehr[k]);
  setzeBall(feld, st);
}

export function setzeBall(feld, st) {
  const bp = st.angriff[st.ball] || L.ANGRIFF_GRUND.RM;
  setzePos(feld.ball, [bp[0] + 14, bp[1] - 10]);
}

// Mausposition/Finger -> Koordinaten im Feld (berücksichtigt Skalierung und viewBox).
export function feldPunkt(svg, e) {
  const pt = svg.createSVGPoint();
  pt.x = e.clientX;
  pt.y = e.clientY;
  const q = pt.matrixTransform(svg.getScreenCTM().inverse());
  return [q.x, q.y];
}
