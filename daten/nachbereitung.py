"""Nachbereitung von Spielen (Gedanken, Gegner-Notizen, Ansprache)."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from .termine import SPIEL_ARTEN


# ================================================== Spiel-Nachbereitung ==
#  Siehe Tabelle 'spiel_nachbereitung'. Nur Trainer (routen/termine.py: require_trainer); nichts
#  davon darf in training_detail() / trainings_liste() auftauchen - ausser dem
#  Merker 'hat_nachbereitung', den routen/termine.py nur fuer Trainer anfuegt.

NACHB_MAX_TEXT = 10000


def gegner_schluessel(name: str | None) -> str:
    """Vergleichsform eines Gegnernamens: klein, ohne Satzzeichen, Leerzeichen zusammengezogen
    ('TV Gross-Umstadt ' und 'tv gross umstadt' sind derselbe Gegner)."""
    n = re.sub(r"[.,;:/\\-]+", " ", (name or "").casefold())
    return " ".join(n.split())


def _spiel(conn: sqlite3.Connection, tid: int):
    return conn.execute(
        f"SELECT * FROM trainings WHERE id = ? AND art IN ({','.join('?' * len(SPIEL_ARTEN))})",
        (tid, *SPIEL_ARTEN)).fetchone()


def nachbereitung_ids(conn: sqlite3.Connection) -> set[int]:
    """Spiele, zu denen schon etwas notiert wurde (fuer das Zeichen in der Terminliste)."""
    return {r["training_id"] for r in conn.execute(
        "SELECT training_id FROM spiel_nachbereitung "
        "WHERE gedanken <> '' OR gegner <> '' OR ansprache <> ''")}


def nachbereitung_holen(conn: sqlite3.Connection, tid: int) -> dict | None:
    """Notizen + Rueckspiel-Hinweise zu einem Spiel; None, wenn es kein Spiel ist."""
    t = _spiel(conn, tid)
    if t is None:
        return None
    r = conn.execute("SELECT * FROM spiel_nachbereitung WHERE training_id = ?", (tid,)).fetchone()
    eigene = ({k: r[k] for k in ("gedanken", "gegner", "ansprache", "vorspiel_id", "geaendert_am", "autor")}
              if r else {"gedanken": "", "gegner": "", "ansprache": "",
                         "vorspiel_id": None, "geaendert_am": None, "autor": None})
    return {"training_id": tid, "gegner_name": t["gegner"], **eigene,
            "frueher": _frueher(conn, t, eigene["vorspiel_id"]),
            "kandidaten": _kandidaten(conn, t)}


def _mit_notizen(conn: sqlite3.Connection, t, manuell: bool) -> dict | None:
    r = conn.execute("SELECT * FROM spiel_nachbereitung WHERE training_id = ?", (t["id"],)).fetchone()
    if r is None or not (r["gedanken"] or r["gegner"] or r["ansprache"]):
        return None
    return {"training_id": t["id"], "datum": t["datum"], "gegner_name": t["gegner"],
            "titel": t["titel"], "manuell": manuell,
            "gedanken": r["gedanken"], "gegner": r["gegner"], "ansprache": r["ansprache"]}


def _frueher(conn: sqlite3.Connection, t, vorspiel_id: int | None) -> list[dict]:
    """Notizen aus frueheren Spielen gegen denselben Gegner (automatisch ueber den
    normalisierten Namen) plus das manuell gewaehlte Vorspiel. Neuestes zuerst."""
    treffer: dict[int, dict] = {}
    schluessel = gegner_schluessel(t["gegner"])
    if schluessel:
        for o in conn.execute(
                f"SELECT * FROM trainings WHERE id <> ? AND art IN ({','.join('?' * len(SPIEL_ARTEN))}) "
                "AND gegner IS NOT NULL AND (datum < ? OR (datum = ? AND id < ?)) "
                "ORDER BY datum DESC, id DESC",
                (t["id"], *SPIEL_ARTEN, t["datum"], t["datum"], t["id"])):
            if gegner_schluessel(o["gegner"]) == schluessel:
                e = _mit_notizen(conn, o, False)
                if e:
                    treffer[o["id"]] = e
    if vorspiel_id and vorspiel_id not in treffer:
        o = _spiel(conn, vorspiel_id)
        if o is not None:
            e = _mit_notizen(conn, o, True)
            if e:
                treffer[o["id"]] = e
    if vorspiel_id in treffer:
        treffer[vorspiel_id]["manuell"] = True
    return sorted(treffer.values(), key=lambda e: (e["datum"] or "", e["training_id"]), reverse=True)


def _kandidaten(conn: sqlite3.Connection, t) -> list[dict]:
    """Andere Spiele zur Auswahl fuers manuelle Vorspiel (falls die Schreibweise abweicht)."""
    return [{"id": o["id"], "datum": o["datum"], "gegner": o["gegner"], "titel": o["titel"]}
            for o in conn.execute(
                f"SELECT id, datum, gegner, titel FROM trainings WHERE id <> ? "
                f"AND art IN ({','.join('?' * len(SPIEL_ARTEN))}) ORDER BY datum DESC, id DESC LIMIT 60",
                (t["id"], *SPIEL_ARTEN))]


class NachbereitungKonflikt(Exception):
    """Ein anderer Trainer hat inzwischen gespeichert (Stand des Clients ist veraltet)."""

    def __init__(self, aktuell: dict):
        self.aktuell = aktuell


def nachbereitung_speichern(conn: sqlite3.Connection, tid: int, autor: str, gedanken: str,
                            gegner: str, ansprache: str, vorspiel_id: int | None,
                            basis: str | None) -> dict | None:
    """Speichert die drei Texte. `basis` = 'geaendert_am', das der Client geladen hat:
    weicht es vom Stand in der Datenbank ab, wird NICHT ueberschrieben (Konflikt) -
    sonst ginge die Notiz des anderen Trainers still verloren."""
    if _spiel(conn, tid) is None:
        return None
    for name, text in (("Gedanken", gedanken), ("Gegner", gegner), ("Ansprache", ansprache)):
        if len(text or "") > NACHB_MAX_TEXT:
            raise ValueError(f"{name}: zu lang (höchstens {NACHB_MAX_TEXT} Zeichen).")
    if vorspiel_id is not None and (vorspiel_id == tid or _spiel(conn, vorspiel_id) is None):
        raise ValueError("Das gewählte Vorspiel ist ungültig.")
    alt = conn.execute("SELECT geaendert_am FROM spiel_nachbereitung WHERE training_id = ?",
                       (tid,)).fetchone()
    if alt is not None and basis != alt["geaendert_am"]:
        raise NachbereitungKonflikt(nachbereitung_holen(conn, tid))
    # Zeitstempel mit Mikrosekunden: zwei Speichern in derselben Sekunde bleiben unterscheidbar.
    jetzt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    conn.execute(
        "INSERT INTO spiel_nachbereitung (training_id, gedanken, gegner, ansprache, vorspiel_id, "
        "geaendert_am, autor) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(training_id) DO UPDATE SET gedanken = excluded.gedanken, "
        "gegner = excluded.gegner, ansprache = excluded.ansprache, vorspiel_id = excluded.vorspiel_id, "
        "geaendert_am = excluded.geaendert_am, autor = excluded.autor",
        (tid, gedanken or "", gegner or "", ansprache or "", vorspiel_id, jetzt, autor))
    conn.commit()
    return nachbereitung_holen(conn, tid)
