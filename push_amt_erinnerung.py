"""Erinnerung "heute nicht vergessen" eine Stunde vor Training oder Treffpunkt per Web-Push.

Wer ein Mitbring-Amt hat (Duschgel, Tape, Harz/Öl, Eiskoffer, Musik) oder für diesen Termin bei
Getränken, Leibchen, Trikots oder einer Fahrt eingeteilt ist, bekommt eine Stunde vorher eine
Nachricht mit den Dingen. Bezugszeit ist bei Auswärtsspielen die Abfahrt, sonst Beginn bzw. Anwurf
(siehe aemter.treffzeit). Wer für den Termin abgesagt hat, bekommt nichts.

Läuft alle zehn Minuten; gesendet wird, sobald bis zur Bezugszeit höchstens 60 Minuten bleiben.
Jede Nachricht geht je Termin und Person nur einmal raus (Tabelle push_gesendet), ein weiterer
Lauf stört nicht. Die Zeiten sind Berliner Zeit, der Server läuft auf UTC.

Als Cron (CRON_TZ=Europe/Berlin):
  */10 5-21 * * *   cd /home/luca/elo && /home/luca/anytype-sync/.venv/bin/python push_amt_erinnerung.py

CLI:
  py push_amt_erinnerung.py --trocken                       # nur zählen, nichts senden
  py push_amt_erinnerung.py --jetzt "2026-11-05 18:05"      # so tun, als wäre es dann
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, time

import aemter
import benachrichtigung
import db
import push

VORLAUF_MIN = 60


def _liste(worte: list[str]) -> str:
    return worte[0] if len(worte) == 1 else ", ".join(worte[:-1]) + " und " + worte[-1]


def erinnere(conn, jetzt: datetime, vorlauf: int = VORLAUF_MIN, trocken: bool = False) -> dict:
    """`jetzt` mit Zeitzone (Berlin). Gibt zurück, wie viele Termine anstanden und was ging."""
    heute = jetzt.date().isoformat()
    termine = conn.execute(
        "SELECT id, titel, uhrzeit, art, gegner, heim, abfahrt FROM trainings WHERE datum = ?", (heute,)).fetchall()
    faellig = gesendet = empfaenger = ohne_zeit = 0
    for t in termine:
        zeit = aemter.treffzeit(t)
        if zeit is None:
            ohne_zeit += 1
            continue
        wort, uhr = zeit
        try:
            beginn = datetime.combine(jetzt.date(), time.fromisoformat(uhr), tzinfo=jetzt.tzinfo)
        except ValueError:
            ohne_zeit += 1
            continue
        minuten = (beginn - jetzt).total_seconds() / 60
        if not 0 < minuten <= vorlauf:
            continue
        faellig += 1
        abgesagt = {r["spieler_id"] for r in conn.execute(
            "SELECT spieler_id FROM training_teilnahme WHERE training_id = ? AND status = 'abgesagt'", (t["id"],))}
        wann = f"{wort} {uhr} Uhr"
        if t["art"] != "training" and t["gegner"]:
            wann += f" · Spiel {'gegen' if t['heim'] else 'bei'} {t['gegner']}"
        for sid, dinge in aemter.erinnerungen(conn, t["id"]).items():
            an = benachrichtigung.benutzer_von(conn, [sid])
            if sid in abgesagt or not an:
                continue
            if trocken:
                gesendet += 1
                empfaenger += len(an)
                continue
            if not db.push_einmalig(conn, f"amt:{t['id']}:{sid}"):
                continue
            push.sende(conn, an, "Heute nicht vergessen", f"{_liste(dinge)} · {wann}", art="aemter")
            gesendet += 1
            empfaenger += len(an)
    return {"termine": len(termine), "faellig": faellig, "ohne_zeit": ohne_zeit,
            "gesendet": gesendet, "empfaenger": empfaenger}


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jetzt", help='Zeitpunkt statt der Uhr, Berliner Zeit, z. B. "2026-11-05 18:05"')
    ap.add_argument("--db")
    ap.add_argument("--trocken", action="store_true")
    args = ap.parse_args()

    tz = db._berlin()
    jetzt = datetime.fromisoformat(args.jetzt).replace(tzinfo=tz) if args.jetzt else datetime.now(tz)
    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)
    try:
        r = erinnere(conn, jetzt, trocken=args.trocken)
        summary = (f"{r['faellig']} Termin(e) in der Stunde, {r['gesendet']} Nachricht(en) an {r['empfaenger']} Konten"
                   + (f", {r['ohne_zeit']} ohne Uhrzeit" if r["ohne_zeit"] else ""))
        print(summary + (" (TROCKEN)" if args.trocken else ""))
        try:
            import anytype_sync
            anytype_sync.schreibe_status("push_amt_erinnerung", True, summary, 0)
        except Exception:
            pass
    except Exception as e:
        print(f"Fehler: {e}")
        try:
            import anytype_sync
            anytype_sync.schreibe_status("push_amt_erinnerung", False, f"Fehler: {e}", 1)
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
