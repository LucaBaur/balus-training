"""Legt wiederkehrende Trainingstermine aus einem Wochenmuster an (Phase 4).

Muster (Wochentag -> Uhrzeit, Ort):
  Montag    20:00  Gerhausen
  Donnerstag 20:15 Blaubeuren
  Freitag   19:00  Gerhausen

Idempotent: existiert am Datum schon ein Training, werden nur Uhrzeit/Ort/Titel
gesetzt (kein Duplikat, Teilnahme bleibt erhalten).

CLI:
  py trainings_termine.py --ab 2026-07-17 --bis 2026-08-01
  py trainings_termine.py --bis 2026-08-01            # ab heute
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
    4: ("19:00", "Gerhausen"),
}


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ab", help="Startdatum JJJJ-MM-TT (Default: heute)")
    ap.add_argument("--bis", required=True, help="Enddatum JJJJ-MM-TT (inklusive)")
    ap.add_argument("--db")
    ap.add_argument("--trocken", action="store_true", help="nur zeigen, nicht schreiben")
    args = ap.parse_args()

    ab = _d(args.ab) if args.ab else date.today()
    bis = _d(args.bis)
    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)

    d = ab
    neu = akt = 0
    while d <= bis:
        regel = REGELN.get(d.weekday())
        if regel:
            uhr, ort = regel
            iso = d.isoformat()
            titel = f"Training {ort}"
            row = conn.execute(
                "SELECT id FROM trainings WHERE datum=? ORDER BY id LIMIT 1", (iso,)
            ).fetchone()
            if row:
                if not args.trocken:
                    conn.execute(
                        "UPDATE trainings SET uhrzeit=?, ort=?, titel=? WHERE id=?",
                        (uhr, ort, titel, row["id"]))
                akt += 1
                marke = "akt"
            else:
                if not args.trocken:
                    conn.execute(
                        "INSERT INTO trainings (datum, titel, uhrzeit, ort) VALUES (?,?,?,?)",
                        (iso, titel, uhr, ort))
                neu += 1
                marke = "neu"
            wt = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][d.weekday()]
            print(f"  {marke}  {wt} {iso}  {uhr}  {ort}")
        d += timedelta(days=1)

    if not args.trocken:
        conn.commit()
    print(f"\n{neu} neu, {akt} aktualisiert" + (" (TROCKEN – nichts geschrieben)" if args.trocken else ""))
    conn.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
