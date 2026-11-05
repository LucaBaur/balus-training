import { ladeSpieler, spielerAlle } from "./einteilung.js";
import { $, escape } from "../core/ui.js";

// ================================================= Statistik Spiele (Saison) ==
//  Auswertung einer hochgeladenen Spielanalyse (Balu-Spielanalyse) fuer den
//  Trainer. Wurf = Tor + Fehlwurf; Angriff = Wurf + Ballverlust.
//  Positionen: aus position_angriff, pro Spieler/Spiel ueberschreibbar.
const STAT_POS_UEBER = [   // [Namensanfang, Gruppe] – gilt fuer alle Spiele dieser Saison-Statistik
  ["helen", "Rückraum"], ["franzi o", "Außen"],
];
const STAT_POS_GRUPPEN = ["Rückraum", "Außen", "Kreis", "Tor"];
let statSpiele = [];
let statAktId = null;
function statPosition(s) {
  const n = (s.name || "").toLowerCase();
  const u = STAT_POS_UEBER.find(([p]) => n.startsWith(p));
  if (u) return u[1];
  const p = (s.position_angriff || "").toLowerCase();
  if (s.position === "Tor" || p.includes("tor")) return "Tor";
  if (p.includes("kreis")) return "Kreis";
  if (p.includes("außen") || p.includes("aussen")) return "Außen";
  if (p) return "Rückraum";   // Halblinks / Mitte / Halbrechts / Rückraum
  return "Ohne Position";
}
const statQuote = (z, n) => (n > 0 ? Math.round((z / n) * 100) + " %" : "–");
function berechneSpielStatistik(a, spieler) {
  const proId = new Map();
  const zeile = (id) => {
    if (!proId.has(id)) {
      const s = spieler.find((x) => x.id === id) || { id, name: "Spielerin " + id };
      proId.set(id, { id, name: s.name, pos: statPosition(s), tore: 0, fehl: 0, bv: 0, paraden: 0 });
    }
    return proId.get(id);
  };
  const ges = { tore: 0, fehl: 0, bv: 0 };
  for (const e of a.events) {
    if (e.spieler_id == null) continue;
    if (e.typ === "tor") { zeile(e.spieler_id).tore++; ges.tore++; }
    else if (e.typ === "fehlwurf") { zeile(e.spieler_id).fehl++; ges.fehl++; }
    else if (e.typ === "ballverlust") { zeile(e.spieler_id).bv++; ges.bv++; }
    else if (e.typ === "parade") zeile(e.spieler_id).paraden++;
  }
  const spielzuege = new Map();
  for (const z of a.zuege) {
    const r = spielzuege.get(z.name) || { name: z.name, gruen: 0, orange: 0, rot: 0 };
    r[z.ampel]++;
    spielzuege.set(z.name, r);
  }
  const spielerListe = [...proId.values()].sort((x, y) => (y.tore + y.fehl) - (x.tore + x.fehl) || x.name.localeCompare(y.name));
  const pos = STAT_POS_GRUPPEN.concat(["Ohne Position"]).map((g) => {
    const m = spielerListe.filter((s) => s.pos === g);
    const sum = (k) => m.reduce((n, s) => n + s[k], 0);
    return { name: g, tore: sum("tore"), fehl: sum("fehl"), bv: sum("bv"), paraden: sum("paraden"), n: m.length };
  }).filter((p) => p.n > 0);
  return { ges, spielzuege: [...spielzuege.values()].sort((x, y) => (y.gruen + y.orange + y.rot) - (x.gruen + x.orange + x.rot)),
           spieler: spielerListe, pos };
}
function statTabelle(kopf, zeilen) {
  return `<div class="stat-scroll"><table class="stat-tab"><thead><tr>${kopf.map((k, i) => `<th${i ? ' class="r"' : ""}>${k}</th>`).join("")}</tr></thead>
    <tbody>${zeilen.map((z) => `<tr>${z.map((c, i) => `<td${i ? ' class="r"' : ""}>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function statWurfZeilen(liste, mitParaden) {
  return liste.map((s) => {
    const w = s.tore + s.fehl;
    const z = [escape(s.name), w, s.tore, s.fehl, statQuote(s.tore, w), s.bv];
    if (mitParaden) z.push(s.paraden);
    return z;
  });
}
function renderStatistikSpiel(a, spieler) {
  const st = berechneSpielStatistik(a, spieler);
  const wuerfe = st.ges.tore + st.ges.fehl;
  const angriffe = wuerfe + st.ges.bv;
  const zg = st.spielzuege.reduce((n, r) => (n.g += r.gruen, n.o += r.orange, n.r += r.rot, n), { g: 0, o: 0, r: 0 });
  const zn = zg.g + zg.o + zg.r;
  const kachel = (zahl, text) => `<span class="an-kachel"><b>${zahl}</b>${text}</span>`;
  const feld = st.spieler.filter((s) => s.pos !== "Tor");
  const tor = st.spieler.filter((s) => s.pos === "Tor");
  const kopf = ["", "Würfe", "Tore", "Fehlwürfe", "Wurfeff.", "Ballverl."];
  const ampelZellen = (g, o, r, n) => [`<span class="an-p gruen">${statQuote(g, n)}</span>`,
    `<span class="an-p orange">${statQuote(o, n)}</span>`, `<span class="an-p rot">${statQuote(r, n)}</span>`];
  return `
    <h3>Gesamt</h3>
    <div class="an-kacheln">
      ${kachel(statQuote(st.ges.tore, angriffe), "Angriffseffektivität")}
      ${kachel(statQuote(st.ges.tore, wuerfe), "Wurfeffektivität")}
      ${kachel(angriffe, "Angriffe")}${kachel(wuerfe, "Würfe")}${kachel(st.ges.tore, "Tore")}${kachel(st.ges.bv, "Ballverluste")}
    </div>
    <p class="hinweis">Angriffseffektivität = Tore ÷ (Würfe + Ballverluste). Wurfeffektivität = Tore ÷ Würfe.</p>
    <h3>Spielzüge</h3>
    ${zn ? statTabelle(["Spielzug", "Anz.", "Gut", "Mittel", "Schlecht"],
      [["<b>Alle</b>", zn, ...ampelZellen(zg.g, zg.o, zg.r, zn)],
       ...st.spielzuege.map((r) => { const n = r.gruen + r.orange + r.rot;
         return [escape(r.name), n, ...ampelZellen(r.gruen, r.orange, r.rot, n)]; })])
      : '<p class="hinweis">Keine Spielzüge erfasst.</p>'}
    <p class="hinweis">Gut = Tor (grün), Mittel = okay (orange), Schlecht = Fehler (rot).</p>
    <h3>Spielerinnen</h3>
    ${statTabelle(kopf, statWurfZeilen(feld))}
    ${tor.length ? `<h3>Torhüterinnen</h3>${statTabelle(["", "Paraden", "Ballverl."], tor.map((s) => [escape(s.name), s.paraden, s.bv]))}` : ""}
    <h3>Nach Positionen</h3>
    ${statTabelle(kopf, statWurfZeilen(st.pos.filter((p) => p.name !== "Tor").map((p) => ({ ...p, name: p.name + " (" + p.n + ")" }))))}
    <p class="hinweis">Helen = Rückraum, Franzi O. = Außen. Alle anderen nach ihrer Angriffsposition im Kader (Halblinks/Mitte/Halbrechts = Rückraum).</p>`;
}
export async function ladeStatistikSpiele() {
  const el = $("#statspiele-inhalt");
  el.innerHTML = '<p class="hinweis">Lädt …</p>';
  try {
    statSpiele = await Sync.apiOffline("/api/analysen");
    if (!spielerAlle.length) await ladeSpieler();
  } catch (_) {
    el.innerHTML = '<p class="hinweis">Spiele konnten nicht geladen werden.</p>';
    return;
  }
  if (!statSpiele.length) { el.innerHTML = '<p class="hinweis">Noch kein Spiel hochgeladen.</p>'; return; }
  if (!statSpiele.some((s) => s.id === statAktId)) {
    statAktId = (statSpiele.find((s) => /oberkochen/i.test(s.gegner)) || statSpiele[0]).id;
  }
  await zeigeStatistikSpiel();
}
async function zeigeStatistikSpiel() {
  const el = $("#statspiele-inhalt");
  const chips = statSpiele.map((s) => `<button class="chip-btn${s.id === statAktId ? " aktiv" : ""}" data-sid="${s.id}">${escape(s.gegner)}</button>`).join("");
  let a;
  try { a = await Sync.apiOffline("/api/analysen/" + statAktId); }
  catch (_) { el.innerHTML = '<p class="hinweis">Spiel konnte nicht geladen werden.</p>'; return; }
  const meta = [a.datum ? a.datum.split("-").reverse().join(".") : "", a.art].filter(Boolean).join(" · ");
  el.innerHTML = `<div class="stat-chips">${chips}</div><p class="hinweis">${escape(a.gegner)}${meta ? " · " + escape(meta) : ""}</p>`
    + renderStatistikSpiel(a, spielerAlle);
  el.querySelectorAll("[data-sid]").forEach((b) => b.addEventListener("click", () => {
    statAktId = Number(b.dataset.sid); zeigeStatistikSpiel();
  }));
}
