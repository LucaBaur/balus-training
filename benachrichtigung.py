"""Wer bekommt wann welche Push-Nachricht?

Dieses Modul kennt die Ausloeser (neuer Clip, abgesagter Termin, zu wenige Zusagen,
neue Videoanalyse) und baut daraus Empfaengerliste und Text. Verschickt wird ueber
`push.sende`, das die Einstellungen der Personen beachtet (Art der Nachricht).

Aufgerufen werden die Funktionen aus app.py im Hintergrund, nachdem die eigentliche
Aktion (Clip speichern, Termin loeschen) schon gelaufen ist: Push ist Zugabe.
"""

from __future__ import annotations

from datetime import date, datetime

import db
import push

# Unter dieser Zahl an Zusagen warnt die App (im Frontend: Stufe "kritisch" = 5 oder weniger).
ZUSAGEN_MINIMUM = 6


def _datum_de(iso: str | None) -> str:
    try:
        return datetime.strptime(iso or "", "%Y-%m-%d").strftime("%d.%m.")
    except ValueError:
        return iso or ""


def benutzer_von(conn, spieler_ids) -> list[int]:
    """Konten (Benutzer-IDs) zu Spielerinnen-IDs, ohne Doppelte."""
    an: list[int] = []
    for sid in spieler_ids:
        for b in db.benutzer_ids_fuer_spieler(conn, int(sid)):
            if b not in an:
                an.append(b)
    return an


def _ist_vergangen(datum: str | None) -> bool:
    return bool(datum) and datum < date.today().isoformat()


def clip_neu(conn, titel: str, spieler_ids) -> dict:
    """Neuer Szenen-Clip: nur die zugeordneten Spielerinnen erfahren davon."""
    an = benutzer_von(conn, spieler_ids)
    if not an:
        return {"gesendet": 0}
    return push.sende(conn, an, "Neuer Clip für dich", titel, art="videos")


def analyse_video_neu(conn, aid: int) -> dict:
    """Das Spielvideo ist da: alle Beteiligten, aber je Analyse und Person nur einmal
    (das Video darf neu hochgeladen werden, ohne dass es noch einmal klingelt)."""
    a = db.analyse_nach_id(conn, aid)
    if a is None:
        return {"gesendet": 0}
    neu = [sid for sid in db.analyse_beteiligte(conn, aid)
           if db.push_einmalig(conn, f"analyse:{aid}:{sid}")]
    an = benutzer_von(conn, neu)
    if not an:
        return {"gesendet": 0}
    return push.sende(conn, an, "Neue Videoanalyse für dich",
                      f"Spiel gegen {a['gegner']}: deine Szenen sind da.", art="videos")


def amt_zugeteilt(conn, amt_id: int, training_id: int, spieler_id: int) -> dict:
    """Die Inhaberin einer Liste hat jemanden eingeteilt (Trikots, Leibchen, Getränke, Fahrt):
    die Eingeteilte erfährt es. Vergangene Termine bleiben still."""
    amt = conn.execute("SELECT name, typ FROM amt WHERE id = ?", (amt_id,)).fetchone()
    t = conn.execute("SELECT datum, titel, uhrzeit FROM trainings WHERE id = ?", (training_id,)).fetchone()
    an = benutzer_von(conn, [spieler_id])
    if amt is None or t is None or not an or _ist_vergangen(t["datum"]):
        return {"gesendet": 0}
    wann = f"{t['titel'] or 'Termin'} am {_datum_de(t['datum'])}" + (f" um {t['uhrzeit']}" if t["uhrzeit"] else "")
    if amt["typ"] == "fahrten":
        return push.sende(conn, an, "Du fährst selbst mit dem Auto", f"{wann}. Eingetragen beim {amt['name']}.", art="aemter")
    return push.sende(conn, an, f"Du bist dran: {amt['name']}", wann, art="aemter")


def termin_abgesagt(conn, termin: dict) -> dict:
    """`termin` ist der Stand VOR dem Loeschen (training_detail). Wer zugesagt oder
    'unsicher' gesagt hat, erfaehrt es; vergangene Termine werden still aufgeraeumt."""
    if _ist_vergangen(termin.get("datum")):
        return {"gesendet": 0}
    sids = [t["id"] for t in termin.get("teilnahme", []) if t.get("status") in ("anwesend", "unsicher")]
    an = benutzer_von(conn, sids)
    if not an:
        return {"gesendet": 0}
    titel = termin.get("titel") or "Termin"
    wann = _datum_de(termin.get("datum")) + (f" {termin['uhrzeit']}" if termin.get("uhrzeit") else "")
    return push.sende(conn, an, "Termin abgesagt", f"{titel} am {wann} fällt aus.", art="termine")


def zusagen_pruefen(conn, training_id: int, vorher: int) -> dict:
    """Warnt die Trainer genau dann, wenn die Zahl der Zusagen UNTER die Grenze faellt
    (und nicht bei jeder weiteren Absage). Nur fuer Termine, die noch bevorstehen."""
    t = conn.execute("SELECT datum, titel, art FROM trainings WHERE id = ?", (training_id,)).fetchone()
    if t is None or _ist_vergangen(t["datum"]) or db.ist_freiwillig(t["datum"], t["art"]):
        return {"gesendet": 0}
    jetzt = db.zusagen_anzahl(conn, training_id)
    if not (vorher >= ZUSAGEN_MINIMUM and jetzt < ZUSAGEN_MINIMUM):
        return {"gesendet": 0}
    an = db.trainer_benutzer_ids(conn)
    titel = t["titel"] or "Training"
    return push.sende(conn, an, "Zu wenige Zusagen",
                      f"{titel} am {_datum_de(t['datum'])}: nur noch {jetzt} Zusagen.", art="warnungen")
