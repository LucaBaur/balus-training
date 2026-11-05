import { zeigeView } from "../core/router.js";
import { $, escape, toast } from "../core/ui.js";

// -------------------------------------------------------------- Zustand ----
export let spielerAlle = [];          // alle aktiven Spielerinnen (vom Server)
export function setzeSpielerAlle(wert) { spielerAlle = wert; return wert; }
const anwesend = new Set();    // ausgewaehlte IDs
let teamListe = [];            // 2-4 Teams, je ein Array von Spieler-Objekten
let teamAnzahl = 2;            // gewuenschte Anzahl (bleibt zwischen Spielen)
let trainingsListe = [];       // Trainings (Team-Einteilung-Auswahl)
let spielToken = null;         // Idempotenz-Schluessel des aktuellen Spiels
let sendeLaeuft = false;       // verhindert paralleles Doppel-Absenden
// Eindeutiger Token je geplantem Spiel. Wird bei neuen/neu gemischten Teams und
// nach jedem erfolgreich gespeicherten Spiel erneuert, damit ein wackeliger
// Handy-Upload dasselbe Spiel nie doppelt zaehlen kann (Server dedupliziert).
function neuerSpielToken() {
  spielToken = (crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : "t-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}
// ----------------------------------------------------------- Anwesenheit ----
export async function ladeSpieler() {
  // erst gecachten Stand zeigen (auch offline sofort), dann online aktualisieren
  const cached = await Sync.spiegelRoh("/api/spieler");
  if (cached) { spielerAlle = cached; renderAnwesenheit(); }
  const frisch = await Sync.frischHolen("/api/spieler");
  if (frisch) { spielerAlle = frisch; renderAnwesenheit(); }
}
function renderAnwesenheit() {
  const el = $("#anwesenheit-liste");
  el.innerHTML = "";
  if (spielerAlle.length === 0) {
    el.innerHTML = '<p class="hinweis">Noch keine Spielerinnen. Lege sie im Tab „Kader" an.</p>';
    return;
  }
  for (const s of spielerAlle) {
    const zeile = document.createElement("label");
    zeile.className = "spieler-zeile" + (anwesend.has(s.id) ? " gewaehlt" : "");
    zeile.innerHTML = `
      <input type="checkbox" ${anwesend.has(s.id) ? "checked" : ""}>
      <span class="name">${escape(s.name)}</span>
      <span class="meta">${s.position === "Tor" ? "Tor · " : ""}ELO ${s.elo}</span>`;
    zeile.querySelector("input").addEventListener("change", (e) => {
      if (e.target.checked) anwesend.add(s.id); else anwesend.delete(s.id);
      zeile.classList.toggle("gewaehlt", e.target.checked);
    });
    el.appendChild(zeile);
  }
}
$("#btn-generieren").addEventListener("click", () => {
  // Team-Einteilung laeuft LOKAL (teams-local.js) -> funktioniert offline.
  const anwesendeSpieler = spielerAlle.filter((p) => anwesend.has(p.id));
  if (anwesendeSpieler.length < 2) { toast("Mindestens zwei Spielerinnen auswählen."); return; }
  teamsNeuBilden(anwesendeSpieler);
  renderTeams();
  zeigeView("view-teams");
});
export async function ladeTrainings() {
  const sel = $("#training-auswahl");
  sel.innerHTML = '<option value="">— manuell auswählen —</option>';
  try {
    trainingsListe = await Sync.apiOffline("/api/einteilung/trainings");
  } catch (e) {
    trainingsListe = [];          // Server/Cache nicht erreichbar -> nur manuell
    return;
  }
  for (const t of trainingsListe) {
    const o = document.createElement("option");
    o.value = t.id;
    o.textContent = `${t.label} · ${t.spieler_ids.length} zugesagt`;
    sel.appendChild(o);
  }
}
$("#training-auswahl").addEventListener("change", (e) => {
  const t = trainingsListe.find((x) => String(x.id) === e.target.value);
  if (!t) return;
  anwesend.clear();
  t.spieler_ids.forEach((id) => anwesend.add(id));
  renderAnwesenheit();
  const fehlend = t.anwesend_gesamt - t.spieler_ids.length;
  toast(fehlend > 0
    ? `${t.spieler_ids.length} übernommen · ${fehlend} nicht im Kader`
    : `${t.spieler_ids.length} Spielerinnen übernommen`);
});
// ------------------------------------------------------------------ Teams ----
//  Erwaermungsspiele laufen mal mit zwei, mal mit vier Teams. Die Teams heissen
//  nach ihren Leibchen - so ruft man sie in der Halle auch auf.

export const TEAM_FARBEN = [
  { k: "A", name: "Blau",  farbe: "var(--court)",   text: "#03212F" },
  { k: "B", name: "Ocker", farbe: "var(--ocker)",   text: "#231204" },
  { k: "C", name: "Weiß",  farbe: "#E7ECF2",        text: "#0E1C33" },
  { k: "D", name: "Grün",  farbe: "#7FC5A8",        text: "#08281C" },
];
function teamAnzahlSetzen(n) {
  teamAnzahl = Math.max(2, Math.min(Number(n) || 2, 4));
  try { localStorage.setItem("team-anzahl", String(teamAnzahl)); } catch (_) {}
}
function teamAnzahlLaden() {
  try { teamAnzahlSetzen(localStorage.getItem("team-anzahl")); } catch (_) {}
}
function teamsNeuBilden(spieler) {
  teamListe = TeamsLokal.generiereN(spieler, teamAnzahl);
  neuerSpielToken();
}
function renderTeams() {
  const wrap = $("#teams-wrap");
  wrap.innerHTML = "";
  wrap.className = "teams" + (teamListe.length > 2 ? " viele" : "");
  teamListe.forEach((team, i) => {
    const f = TEAM_FARBEN[i];
    const sp = document.createElement("div");
    sp.className = "team";
    sp.innerHTML =
      `<h2 style="color:${f.farbe === "#E7ECF2" ? "var(--grau)" : f.farbe}">Team ${f.k}
         <span class="team-leibchen">${f.name}</span>
         <span class="schnitt">${schnitt(team)}</span></h2>`;
    const chips = document.createElement("div");
    chips.className = "chips";
    team.forEach((p) => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.style.borderLeft = "5px solid " + f.farbe;
      chip.innerHTML = `${escape(p.name)}` +
        `${p.position === "Tor" ? '<span class="tor">TW</span>' : ""}` +
        `<span class="elo">${p.elo}</span>`;
      // Antippen schiebt ins naechste Team (bei zweien: auf die andere Seite).
      chip.addEventListener("click", () => {
        const ziel = (i + 1) % teamListe.length;
        teamListe[i].splice(teamListe[i].indexOf(p), 1);
        teamListe[ziel].push(p);
        renderTeams();
        if (teamListe.length > 2) toast(p.name.split(" ")[0] + " → Team " + TEAM_FARBEN[ziel].k);
      });
      chips.appendChild(chip);
    });
    if (!team.length) chips.innerHTML = '<p class="hinweis">noch leer</p>';
    sp.appendChild(chips);
    wrap.appendChild(sp);
  });
  renderTeamAnzahl();
  renderSiegchance();
  renderErgebnisKnoepfe();
}
function renderTeamAnzahl() {
  const el = $("#team-anzahl");
  if (!el) return;
  const anwesende = teamListe.flat().length;
  el.innerHTML = '<span class="ta-lab">Teams</span>';
  const gr = document.createElement("div");
  gr.className = "ta-gruppe";
  [2, 3, 4].forEach((n) => {
    const b = document.createElement("button");
    b.textContent = n;
    b.setAttribute("aria-pressed", teamListe.length === n ? "true" : "false");
    b.disabled = anwesende < n * 2;
    b.addEventListener("click", () => {
      teamAnzahlSetzen(n);
      teamsNeuBilden(teamListe.flat());
      renderTeams();
    });
    gr.appendChild(b);
  });
  el.appendChild(gr);
}
function schnitt(team) {
  if (!team.length) return "";
  return "Ø " + Math.round(team.reduce((a, p) => a + p.elo, 0) / team.length);
}
function mittel(team) {
  return team.length ? team.reduce((a, p) => a + p.elo, 0) / team.length : 0;
}
// Bei zwei Teams die Siegchance, sonst ein Staerkevergleich (eine Chance
// zwischen vier Teams waere Zahlenspielerei).
function renderSiegchance() {
  const el = $("#siegchance");
  if (teamListe.length !== 2) {
    if (teamListe.some((t) => !t.length)) { el.innerHTML = ""; return; }
    const schnitte = teamListe.map(mittel);
    const mx = Math.max(...schnitte), mn = Math.min(...schnitte);
    el.innerHTML = '<div class="staerke">' + teamListe.map((t, i) => {
      const breite = 45 + (mx === mn ? 55 : ((mittel(t) - mn) / (mx - mn)) * 55);
      return `<div class="st-zeile"><span class="st-k" style="color:${TEAM_FARBEN[i].farbe}">Team ${TEAM_FARBEN[i].k}</span>` +
             `<span class="st-bar"><i style="width:${breite}%;background:${TEAM_FARBEN[i].farbe}"></i></span>` +
             `<span class="st-w">Ø ${Math.round(mittel(t))}</span></div>`;
    }).join("") + "</div>";
    return;
  }
  const [a, b] = teamListe;
  if (!a.length || !b.length) { el.innerHTML = ""; return; }
  const pA = 1 / (1 + Math.pow(10, (mittel(b) - mittel(a)) / 400));
  const p = Math.round(pA * 100);
  el.innerHTML =
    `<span class="ch-a">Team A ${p}%</span>` +
    `<span class="ch-bar"><span style="width:${p}%"></span></span>` +
    `<span class="ch-b">${100 - p}% Team B</span>`;
}
// Ergebnis-Knoepfe: je Team einer, mit den Namen darunter - beim Eintragen
// zwischen zwei Spielen will man sehen, wen man da gerade wertet.
function renderErgebnisKnoepfe() {
  const el = $("#ergebnis-knoepfe");
  el.innerHTML = "";
  teamListe.forEach((team, i) => {
    const f = TEAM_FARBEN[i];
    const b = document.createElement("button");
    b.className = "erg";
    b.style.background = f.farbe;
    b.style.color = f.text;
    b.innerHTML =
      `<span class="erg-txt"><span class="erg-titel">Team ${f.k} gewinnt` +
      `<span class="erg-oe">${schnitt(team)} · ${team.length}</span></span>` +
      `<span class="erg-namen">${escape(team.map((p) => p.name.split(" ")[0]).join(" · "))}</span></span>` +
      `<span class="erg-pfeil">›</span>`;
    b.addEventListener("click", () => eintragen(f.k));
    el.appendChild(b);
  });
  const u = document.createElement("button");
  u.className = "erg unent";
  u.innerHTML =
    `<span class="erg-txt"><span class="erg-titel">Unentschieden</span>` +
    `<span class="erg-namen">Alle bekommen die Hälfte</span></span><span class="erg-pfeil">›</span>`;
  u.addEventListener("click", () => eintragen("U"));
  el.appendChild(u);
}
function ergebnisKnoepfeSperren(sperren) {
  document.querySelectorAll("#ergebnis-knoepfe button").forEach((b) => {
    b.disabled = sperren;
  });
}
async function eintragen(ergebnis) {
  if (teamListe.length < 2 || teamListe.some((t) => !t.length)) {
    toast("Jedes Team braucht Spielerinnen."); return;
  }
  if (sendeLaeuft) return;              // schon ein Absenden unterwegs
  if (!spielToken) neuerSpielToken();   // Sicherheitsnetz, falls kein Token gesetzt
  sendeLaeuft = true;
  ergebnisKnoepfeSperren(true);
  try {
    // Geht immer erst in die Outbox; online sofort gesendet, offline gepuffert.
    // Der Token verhindert Doppelzaehlung, egal wann der Sync passiert.
    const r = await Sync.senden("/api/spiel", {
      teams: teamListe.map((t) => t.map((p) => p.id)),
      ergebnis,
      token: spielToken,
    });
    if (r.gesendet) {
      // Online: Teams mit frischen ELOs aus der Rangliste auffrischen.
      const rl = await Sync.frischHolen("/api/rangliste");
      if (Array.isArray(rl)) {
        const nachId = Object.fromEntries(rl.map((p) => [p.id, p]));
        teamListe = teamListe.map((t) => t.map((p) => nachId[p.id] || p));
      }
      toast((ergebnis === "U" ? "Unentschieden gespeichert"
        : "Sieg Team " + ergebnis + " gespeichert") + " — nächstes Spiel?");
    } else {
      toast("Offline gespeichert – wird im WLAN automatisch synchronisiert.");
    }
    neuerSpielToken(); // Outbox haelt den alten Token; naechstes Spiel neu
    renderTeams();
  } catch (e) {
    toast("Fehler: " + e.message);
  } finally {
    sendeLaeuft = false;
    ergebnisKnoepfeSperren(false);
  }
}
$("#btn-neu-mischen").addEventListener("click", () => {
  teamsNeuBilden(teamListe.flat());
  renderTeams();
});
$("#btn-zurueck").addEventListener("click", () => {
  ladeSpieler().then(() => zeigeView("view-anwesenheit"));
});
