"""Legt wiederkehrende Trainingstermine aus einem Wochenmuster an (Phase 4).

Muster (Wochentag -> Uhrzeit, Ort):
  Montag     20:00  Gerhausen
  Donnerstag 20:15  Blaubeuren

Das Muster ist die EIGENE Terminquelle der App - sie braucht dafuer weder
SpielerPlus noch Anytype.

Idempotent: existiert am Datum schon ein Training, werden nur LEERE Felder
(Uhrzeit/Ort/Titel) aufgefuellt. Was jemand von Hand geaendert hat, bleibt
stehen; Teilnahme und Plan bleiben erhalten. Es entsteht nie ein Duplikat.

CLI:
  py trainings_termine.py --tage 14                    # ab heute, 14 Tage voraus (Cron)
  py trainings_termine.py --ab 2026-07-17 --bis 2026-08-01
  py trainings_termine.py --bis 2026-08-01             # ab heute
  py trainings_termine.py --db pfad.db --trocken       # nur anzeigen
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

import db

# Wochentag (Mo=0 … So=6) -> (Uhrzeit, Ort)
REGELN = {
    0: ("20:00", "Gerhausen"),
    3: ("20:15", "Blaubeuren"),
}

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def anlegen(conn, ab: date, bis: date, trocken: bool = False) -> list[dict]:
    """Termine fuer ab..bis (inklusive) anlegen bzw. auffuellen.

    Liefert je Trainingstag {"datum", "aktion" ('neu'|'akt'), "uhrzeit", "ort"}.
    Commit macht der Aufrufer.
    """
    ergebnis = []
    d = ab
    while d <= bis:
        regel = REGELN.get(d.weekday())
        if regel:
            uhr, ort = regel
            iso = d.isoformat()
            titel = f"Training {ort}"
            row = conn.execute(
                "SELECT id FROM trainings WHERE datum=? AND art='training' ORDER BY id LIMIT 1",
                (iso,)
            ).fetchone()
            if row:
                if not trocken:
                    # Nur leere Felder fuellen - sonst wuerde der taegliche Lauf
                    # jede Handaenderung wieder ueberschreiben.
                    conn.execute(
                        "UPDATE trainings SET "
                        "  uhrzeit = COALESCE(NULLIF(uhrzeit, ''), ?), "
                        "  ort     = COALESCE(NULLIF(ort, ''), ?), "
                        "  titel   = COALESCE(NULLIF(titel, ''), ?) "
                        "WHERE id=?",
                        (uhr, ort, titel, row["id"]))
                aktion = "akt"
            else:
                if not trocken:
                    conn.execute(
                        "INSERT INTO trainings (datum, titel, uhrzeit, ort, art) "
                        "VALUES (?,?,?,?,'training')",
                        (iso, titel, uhr, ort))
                aktion = "neu"
            ergebnis.append({"datum": iso, "aktion": aktion, "uhrzeit": uhr, "ort": ort})
        d += timedelta(days=1)
    return ergebnis


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ab", help="Startdatum JJJJ-MM-TT (Default: heute)")
    ap.add_argument("--bis", help="Enddatum JJJJ-MM-TT (inklusive)")
    ap.add_argument("--tage", type=int, help="statt --bis: so viele Tage ab Start voraus")
    ap.add_argument("--db")
    ap.add_argument("--trocken", action="store_true", help="nur zeigen, nicht schreiben")
    args = ap.parse_args()

    if not args.bis and args.tage is None:
        ap.error("--bis oder --tage ist noetig")
    ab = _d(args.ab) if args.ab else date.today()
    bis = _d(args.bis) if args.bis else ab + timedelta(days=args.tage)
    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)

    ergebnis = anlegen(conn, ab, bis, trocken=args.trocken)
    for e in ergebnis:
        wt = WOCHENTAGE[_d(e["datum"]).weekday()]
        print(f"  {e['aktion']}  {wt} {e['datum']}  {e['uhrzeit']}  {e['ort']}")

    if not args.trocken:
        conn.commit()
    neu = sum(1 for e in ergebnis if e["aktion"] == "neu")
    akt = len(ergebnis) - neu
    print(f"\n{neu} neu, {akt} vorhanden" + (" (TROCKEN – nichts geschrieben)" if args.trocken else ""))
    conn.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
