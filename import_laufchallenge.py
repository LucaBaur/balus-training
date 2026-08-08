"""Import der Laufchallenge-Ergebnisse (aus dem separaten Laufchallenge-Projekt)
in die App-DB (Tabelle `laufchallenge`).

Wertung wie im Original (script.js): pro Spielerin zaehlt nur die Distanz der
LAUF-Aktivitaeten; andere Aktivitaeten (Radfahren o. Ae.) werden separat gezaehlt.
Rang = Platz nach km unter ALLEN Challenge-Teilnehmerinnen.

Der heikle Teil ist das **Namens-Mapping**: die Laufchallenge nutzt Kurznamen
('Marie', 'Anni', 'Franzi P'), der Kader Vollnamen. `--dry-run` zeigt die
automatische Zuordnung samt Unklarheiten zum Gegenpruefen. Manuelle Korrekturen
kommen in MANUELL (unten) — Kurzname -> Kader-Name (oder None zum Ignorieren).

CLI:
  py import_laufchallenge.py --dry-run       # Zuordnung + Ergebnisse zeigen
  py import_laufchallenge.py                  # in elo.db schreiben
  py import_laufchallenge.py --db pfad.db --daten pfad/data.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import db

BASIS = Path(__file__).parent
# data.json liegt im Laufchallenge-Projekt (lokal) bzw. am Server neben der App.
DATEN_KANDIDATEN = [
    BASIS / "laufchallenge_data.json",
    BASIS.parent / "Laufchallenge" / "data.json",
]

# Manuelle Korrekturen fuer Faelle, die die Automatik nicht sicher trifft.
# Kurzname (wie in data.json) -> exakter Kader-Name, oder None = nicht zuordnen.
MANUELL: dict[str, str | None] = {
    "Recci": "Rebecca Scott",   # Laufchallenge-Kurzname -> echter Kader-Name
    # "Pim": None,
}

LAUF_WORTE = {"lauf", "laufen", "run", "running", "jog", "jogging", "lauftraining"}


def ist_lauf(run: dict) -> bool:
    akt = str(run.get("activity") or run.get("type") or run.get("sport") or "").strip().lower()
    return not akt or akt in LAUF_WORTE


def finde_daten(explizit: str | None) -> Path:
    if explizit:
        return Path(explizit)
    for p in DATEN_KANDIDATEN:
        if p.exists():
            return p
    return DATEN_KANDIDATEN[0]


def _norm(s: str) -> str:
    return re.sub(r"[^a-zäöüß ]", "", (s or "").lower().strip())


def mappe_namen(lc_namen: list[str], kader: list[dict]) -> dict[str, dict | None]:
    """Ordnet Laufchallenge-Kurznamen den Kader-Spielerinnen zu (Best-Effort).
    Liefert {lc_name: kader_row|None} plus setzt row['_wie'] = Matchgrund."""
    zuordnung: dict[str, dict | None] = {}
    kader_norm = [(k, _norm(k["name"])) for k in kader]
    for lc in lc_namen:
        if lc in MANUELL:
            ziel = MANUELL[lc]
            treffer = next((k for k, kn in kader_norm if k["name"] == ziel), None)
            zuordnung[lc] = dict(treffer, _wie="manuell") if treffer else None
            continue
        n = _norm(lc).rstrip(".").strip()
        toks = n.split()
        # 1) exakt
        exakt = [k for k, kn in kader_norm if kn == n]
        if len(exakt) == 1:
            zuordnung[lc] = dict(exakt[0], _wie="exakt"); continue
        # 2) Vorname (erstes Token) eindeutig, ggf. mit Initial disambiguiert
        cands = [k for k, kn in kader_norm if kn.split() and kn.split()[0] == toks[0]]
        if len(cands) > 1 and len(toks) >= 2:
            eng = [k for k in cands
                   if len(_norm(k["name"]).split()) > 1
                   and _norm(k["name"]).split()[1].startswith(toks[1])]
            if eng:
                cands = eng
        if len(cands) == 1:
            zuordnung[lc] = dict(cands[0], _wie="vorname"); continue
        if len(cands) > 1:
            zuordnung[lc] = None
            zuordnung[lc] = {"_wie": "mehrdeutig",
                             "_cands": [c["name"] for c in cands], "id": None}
            continue
        zuordnung[lc] = None
    return zuordnung


def aggregiere(daten: dict) -> tuple[dict, str, int]:
    """Pro LC-Player: {km, laeufe, andere}. Liefert (stats_by_pid, challenge, n)."""
    stats = {p["id"]: {"name": p["name"], "km": 0.0, "laeufe": 0, "andere": 0}
             for p in daten["players"]}
    for r in daten["runs"]:
        s = stats.get(r["player"])
        if not s:
            continue
        if ist_lauf(r):
            s["laeufe"] += 1
            s["km"] += r.get("distance", 0) or 0
        else:
            s["andere"] += 1
    for s in stats.values():
        s["km"] = round(s["km"], 1)
    challenge = (daten.get("challenge") or {}).get("name", "Laufchallenge")
    return stats, challenge, len(daten["players"])


def raenge(stats: dict) -> dict[str, int]:
    """Platz nach km (absteigend) unter allen LC-Playern."""
    sortiert = sorted(stats.items(), key=lambda kv: kv[1]["km"], reverse=True)
    return {pid: i + 1 for i, (pid, _) in enumerate(sortiert)}


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db")
    ap.add_argument("--daten")
    args = ap.parse_args()

    daten_pfad = finde_daten(args.daten)
    daten = json.loads(daten_pfad.read_text(encoding="utf-8"))
    stats, challenge, n_teiln = aggregiere(daten)
    rang = raenge(stats)
    players = {p["id"]: p for p in daten["players"]}

    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)
    kader = [dict(r) for r in conn.execute("SELECT id, name FROM spieler")]

    lc_namen = [players[pid]["name"] for pid in stats]
    zu = mappe_namen(lc_namen, kader)

    print(f"Daten: {daten_pfad}")
    print(f"Challenge: {challenge!r} · {n_teiln} Teilnehmerinnen\n")
    print(f"{'Laufchallenge':16} {'km':>6} {'Läufe':>6} {'Rang':>5}  →  Kader (Grund)")
    print("-" * 64)
    geschrieben = 0
    unklar = []
    # nach Rang sortiert ausgeben
    for pid in sorted(stats, key=lambda p: rang[p]):
        s = stats[pid]; lc = players[pid]["name"]; z = zu.get(lc)
        if z and z.get("id"):
            ziel = f"{z['name']} ({z['_wie']})"
        elif z and z.get("_wie") == "mehrdeutig":
            ziel = "❓ mehrdeutig: " + ", ".join(z["_cands"]); unklar.append(lc)
        else:
            ziel = "— (kein Kader-Treffer)"; unklar.append(lc)
        print(f"{lc:16} {s['km']:>6.1f} {s['laeufe']:>6} {rang[pid]:>5}  →  {ziel}")

        if not args.dry_run and z and z.get("id"):
            conn.execute(
                "INSERT OR REPLACE INTO laufchallenge "
                "(spieler_id, challenge, km, laeufe, andere, rang, teilnehmer) "
                "VALUES (?,?,?,?,?,?,?)",
                (z["id"], challenge, s["km"], s["laeufe"], s["andere"], rang[pid], n_teiln))
            geschrieben += 1

    if not args.dry_run:
        conn.commit()
        print(f"\n{geschrieben} Ergebnisse in die DB geschrieben.")
    else:
        print("\nDry-Run – nichts geschrieben.")
    if unklar:
        print(f"\n⚠️ {len(unklar)} nicht sicher zugeordnet: {', '.join(unklar)}")
        print("   → in MANUELL (Kopf der Datei) ergänzen (Kurzname -> Kader-Name).")
    conn.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
