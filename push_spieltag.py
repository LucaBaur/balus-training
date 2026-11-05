"""Spieltags-Erinnerung per Web-Push (Vortag und Spieltag).

Schickt allen, die fuer ein Test- oder Ligaspiel zugesagt oder "unsicher" gesagt haben, die
wichtigste Zeit: bei Auswaertsspielen die Abfahrt, sonst den Anwurf. Jede Nachricht geht je
Spiel und Zeitpunkt nur einmal raus (Tabelle push_gesendet), ein zweiter Cron-Lauf stoert nicht.

Als Cron (CRON_TZ=Europe/Berlin):
  0 18 * * *   /home/luca/anytype-sync/.venv/bin/python /home/luca/elo/push_spieltag.py --tage 1
  30 8 * * *   /home/luca/anytype-sync/.venv/bin/python /home/luca/elo/push_spieltag.py --tage 0

CLI:
  py push_spieltag.py --tage 1 --trocken      # nur zaehlen, nichts senden
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import benachrichtigung
import db
import push


def _text(t: dict) -> tuple[str, str]:
    """(Titel-Zusatz, Text) fuer ein Spiel."""
    gegner = t.get("gegner") or "Gegner"
    auswaerts = t.get("heim") == 0
    teile = [gegner]
    if auswaerts and t.get("abfahrt"):
        teile.append(f"Abfahrt {t['abfahrt']}")
    if t.get("uhrzeit"):
        teile.append(f"Anwurf {t['uhrzeit']}")
    if t.get("ort"):
        teile.append(t["ort"])
    zusatz = f"Spiel bei {gegner}" if auswaerts else f"Heimspiel gegen {gegner}"
    return zusatz, " · ".join(teile)


def erinnere(conn, heute: date, tage: int, trocken: bool = False) -> dict:
    ziel = (heute + timedelta(days=tage)).isoformat()
    wort = {0: "Heute", 1: "Morgen"}.get(tage, f"In {tage} Tagen")
    spiele = [t for t in db.trainings_liste(conn)
              if t["datum"] == ziel and t["art"] in db.SPIEL_ARTEN]
    gesendet = empfaenger = 0
    for t in spiele:
        detail = db.training_detail(conn, t["id"])
        sids = [x["id"] for x in detail["teilnahme"] if x["status"] in ("anwesend", "unsicher")]
        an = benachrichtigung.benutzer_von(conn, sids)
        if not an:
            continue
        if trocken:
            gesendet += 1
            empfaenger += len(an)
            continue
        if not db.push_einmalig(conn, f"spieltag:{t['id']}:{tage}"):
            continue
        zusatz, text = _text(t)
        push.sende(conn, an, f"{wort}: {zusatz}", text, art="termine")
        gesendet += 1
        empfaenger += len(an)
    return {"spiele": len(spiele), "gesendet_termine": gesendet, "empfaenger": empfaenger}


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tage", type=int, default=1, help="1 = Vortag, 0 = Spieltag")
    ap.add_argument("--db")
    ap.add_argument("--trocken", action="store_true")
    args = ap.parse_args()

    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)
    try:
        r = erinnere(conn, date.today(), args.tage, args.trocken)
        summary = (f"{r['spiele']} Spiel(e) in {args.tage}T, {r['gesendet_termine']} Nachricht(en) "
                   f"an {r['empfaenger']} Konten")
        print(summary + (" (TROCKEN)" if args.trocken else ""))
        try:
            import anytype_sync
            anytype_sync.schreibe_status("push_spieltag", True, summary, 0)
        except Exception:
            pass
    except Exception as e:
        print(f"Fehler: {e}")
        try:
            import anytype_sync
            anytype_sync.schreibe_status("push_spieltag", False, f"Fehler: {e}", 1)
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
