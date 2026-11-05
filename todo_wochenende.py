"""Wochenend-Benachrichtigung fuer die Wochen-To-Dos.

Meldet den Trainern per Web-Push, welche Spielerinnen sich fuer die Woche ein To-Do
gewaehlt haben und noch auf Feedback warten. Ohne wartende To-Dos wird nichts gesendet.

Als Cron (CRON_TZ=Europe/Berlin), z. B. sonntags 18:00:
  0 18 * * 0  /home/you/anytype-sync/.venv/bin/python /home/you/elo/todo_wochenende.py

CLI:
  py todo_wochenende.py            # senden
  py todo_wochenende.py --trocken  # nur zaehlen
"""

from __future__ import annotations

import argparse
import sys

import db
import push


def melde(conn, trocken: bool) -> dict:
    wartend = db.todos_wartend(conn)
    gesendet = 0
    if wartend and not trocken:
        namen = sorted({w["spieler"] for w in wartend})
        zeige = ", ".join(namen[:4]) + (f" +{len(namen) - 4}" if len(namen) > 4 else "")
        text = f"{len(wartend)} To-Do(s) warten auf dein Feedback: {zeige}"
        res = push.sende(conn, db.trainer_benutzer_ids(conn),
                         "Wochen-To-Dos: Feedback fällig", text, url="/", art="rueckmeldungen")
        gesendet = res.get("gesendet", 0)
    return {"wartend": len(wartend), "gesendet": gesendet}


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db")
    ap.add_argument("--trocken", action="store_true")
    args = ap.parse_args()

    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)
    try:
        r = melde(conn, args.trocken)
        summary = f"{r['wartend']} To-Do(s) ohne Feedback, {r['gesendet']} Push gesendet"
        print(summary + (" (TROCKEN)" if args.trocken else ""))
        try:
            import anytype_sync
            anytype_sync.schreibe_status("todo_wochenende", True, summary, 0)
        except Exception:
            pass
    except Exception as e:
        print(f"Fehler: {e}")
        try:
            import anytype_sync
            anytype_sync.schreibe_status("todo_wochenende", False, f"Fehler: {e}", 1)
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
