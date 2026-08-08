"""Taeglicher Push-Erinnerungs-Job (Phase 4, Stufe B).

Erinnert per Web-Push alle Spielerinnen, die fuer ein bald anstehendes Training
noch NICHT in der App geantwortet haben. Standard: Trainings, die in `--tage`
Tagen (Default 2) stattfinden.

Als Cron (CRON_TZ=Europe/Berlin), z. B. taeglich 18:00:
  0 18 * * *  /home/luca/anytype-sync/.venv/bin/python /home/luca/elo/push_erinnerung.py

CLI:
  py push_erinnerung.py                # 2 Tage vorher
  py push_erinnerung.py --tage 1
  py push_erinnerung.py --trocken      # nur zaehlen, nichts senden
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

import db
import push


def _datum_de(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.")
    except ValueError:
        return iso


def erinnere(conn, tage: int, trocken: bool) -> dict:
    ziel = (date.today() + timedelta(days=tage)).isoformat()
    trainings = [t for t in db.trainings_liste(conn) if t.get("datum") == ziel]
    offen_gesamt = gesendet = 0
    for t in trainings:
        offen = db.offene_spieler_benutzer(conn, t["id"])
        if not offen:
            continue
        offen_gesamt += len(offen)
        label = t.get("titel") or "Training"
        ort = f" in {t['ort']}" if t.get("ort") else ""
        wann = _datum_de(ziel) + (f" {t['uhrzeit']}" if t.get("uhrzeit") else "")
        text = f"{label}{ort} am {wann}: Bitte in der App zu- oder absagen."
        if not trocken:
            res = push.sende(conn, offen, "Training – bitte zu-/absagen", text, url="/")
            gesendet += res.get("gesendet", 0)
    return {"trainings": len(trainings), "offen": offen_gesamt, "gesendet": gesendet}


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tage", type=int, default=2, help="Vorlauf in Tagen (Default 2)")
    ap.add_argument("--db")
    ap.add_argument("--trocken", action="store_true")
    args = ap.parse_args()

    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)
    try:
        r = erinnere(conn, args.tage, args.trocken)
        summary = (f"{r['trainings']} Training(s) in {args.tage}T, "
                   f"{r['offen']} offen, {r['gesendet']} Push gesendet")
        print(summary + (" (TROCKEN)" if args.trocken else ""))
        try:
            import anytype_sync
            anytype_sync.schreibe_status("push_erinnerung", True, summary, 0)
        except Exception:
            pass
    except Exception as e:
        print(f"Fehler: {e}")
        try:
            import anytype_sync
            anytype_sync.schreibe_status("push_erinnerung", False, f"Fehler: {e}", 1)
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
