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


def _liste(worte: list[str]) -> str:
    return worte[0] if len(worte) == 1 else ", ".join(worte[:-1]) + " und " + worte[-1]


def amt_uebergabe(conn, training_id: int, spieler_id: int) -> dict:
    """Wer absagt, aber für diesen Termin noch etwas mitbringen oder tun soll (Tape, Getränke, Fahrt ...),
    wird gebeten, es weiterzugeben. Die Erinnerung vor dem Termin überspringt Absagende bewusst, sonst
    fehlt am Ende das Tape. Je Termin und Person nur einmal, auch wenn jemand hin- und herschaltet."""
    import aemter
    t = conn.execute("SELECT datum, titel, uhrzeit FROM trainings WHERE id = ?", (training_id,)).fetchone()
    if t is None or _ist_vergangen(t["datum"]):
        return {"gesendet": 0}
    if conn.execute("SELECT 1 FROM training_teilnahme WHERE training_id = ? AND spieler_id = ? "
                    "AND status = 'abgesagt'", (training_id, spieler_id)).fetchone() is None:
        return {"gesendet": 0}                     # inzwischen wieder zugesagt oder gelöscht
    dinge = aemter.erinnerungen(conn, training_id).get(spieler_id)
    an = benutzer_von(conn, [spieler_id])
    if not dinge or not an or not db.push_einmalig(conn, f"uebergabe:{training_id}:{spieler_id}"):
        return {"gesendet": 0}
    wann = f"{t['titel'] or 'Termin'} am {_datum_de(t['datum'])}" + (f" um {t['uhrzeit']}" if t["uhrzeit"] else "")
    return push.sende(conn, an, "Du hast abgesagt – wer übernimmt?",
                      f"{wann}: Du bist noch eingetragen für {_liste(dinge)}. Bitte gib es weiter.", art="aemter")


def termin_zeit_geaendert(conn, tid: int, vorher: dict, nachher: dict) -> dict:
    """Zeit, Ort oder Abfahrt eines einzelnen Termins wurden geändert: wer nicht abgesagt hat, erfährt es.
    Vergangene Termine bleiben still, ebenso Änderungen an Titel oder Gegner."""
    t = conn.execute("SELECT datum, titel, uhrzeit FROM trainings WHERE id = ?", (tid,)).fetchone()
    if t is None or _ist_vergangen(t["datum"]):
        return {"gesendet": 0}
    teile = []
    for feld, wort in (("uhrzeit", "Beginn"), ("abfahrt", "Abfahrt"), ("ort", "Ort")):
        if feld in nachher and nachher[feld] != vorher.get(feld):
            alt = f" (vorher {vorher[feld]})" if vorher.get(feld) else ""
            teile.append(f"{wort} jetzt {nachher[feld]}{alt}")
    if not teile:
        return {"gesendet": 0}
    sids = [r["spieler_id"] for r in conn.execute(
        "SELECT spieler_id FROM training_teilnahme WHERE training_id = ? AND status IN ('anwesend', 'unsicher')", (tid,))]
    an = benutzer_von(conn, sids)
    if not an:
        return {"gesendet": 0}
    return push.sende(conn, an, "Termin geändert",
                      f"{t['titel'] or 'Termin'} am {_datum_de(t['datum'])}: " + ", ".join(teile) + ".", art="termine")


def serie_geaendert(conn, wochentag: int, ab_datum: str, vorher: tuple, nachher: tuple) -> dict:
    """Das Wochenmuster hat sich geändert (ab einem Datum für alle Trainings eines Wochentags): eine einzige
    Nachricht an alle aus dem Kader, nicht eine je Termin."""
    teile = []
    if nachher[0] != vorher[0]:
        teile.append(f"Beginn {nachher[0]} statt {vorher[0]}")
    if nachher[1] != vorher[1]:
        teile.append(f"Ort jetzt {nachher[1]}")
    an = benutzer_von(conn, [s["id"] for s in db.aktive_spieler(conn)])
    if not teile or not an:
        return {"gesendet": 0}
    return push.sende(conn, an, f"{db.WOCHENTAGE_NAMEN[wochentag]}straining geändert",
                      f"Ab {_datum_de(ab_datum)}: " + ", ".join(teile) + ".", art="termine")


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
