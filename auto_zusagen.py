"""Trägt alle aktiven Spielerinnen bei kommenden normalen Trainings als zugesagt ein.

Hintergrund: Seit db.AUTO_ZUSAGE_AB sind bei Trainings (nicht freiwillig, keine Spiele) alle automatisch
dabei und sagen nur ab, wenn sie nicht kommen (bis 24 Stunden vorher). Die Zeilen (quelle 'auto') entstehen
normalerweise von selbst. Dieses Skript ist der Handabgleich, nötig einmal beim Umschalten für schon
bestehende Trainings. Vorhandenes (auch Absagen) bleibt unberührt, ein weiterer Lauf stört nicht.

Läuft nicht per Cron: Die Zeilen entstehen beim Anlegen von Training oder Spielerin (db.auto_zusagen).

CLI:
  py auto_zusagen.py --trocken      # nur zählen, nichts schreiben
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import db


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db")
    ap.add_argument("--trocken", action="store_true")
    args = ap.parse_args()

    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)
    try:
        n = db.auto_zusagen(conn, date.today(), trocken=args.trocken)
        summary = f"{n} automatische Zusage(n) " + ("würden eingetragen" if args.trocken else "eingetragen")
        print(summary + (" (TROCKEN)" if args.trocken else ""))
        try:
            import anytype_sync
            anytype_sync.schreibe_status("auto_zusagen", True, summary, 0)
        except Exception:
            pass
    except Exception as e:
        print(f"Fehler: {e}")
        try:
            import anytype_sync
            anytype_sync.schreibe_status("auto_zusagen", False, f"Fehler: {e}", 1)
        except Exception:
            pass
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
