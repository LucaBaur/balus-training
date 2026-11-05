"""Szenen-Videos (Clips vom Schnittwerkzeug) und ihre Zuordnung zu Spielerinnen."""

from __future__ import annotations

import sqlite3

from .kommentare import _kommentar_zahlen


# ------------------------------------------------------------ Szenen-Videos ----
#  Fertige Clips (geschnitten am PC, siehe Projekt "Balu-Videoschnitt"). Die
#  MP4-Datei liegt unter media/clips/; hier steht nur der Dateiname. Ausgeliefert
#  wird sie ausschliesslich ueber /api/clips/{id}/video mit Rollen-/Zuordnungs-
#  Pruefung - nicht ueber den StaticFiles-Mount.

def _clip_spieler(conn: sqlite3.Connection, clip_ids: list[int]) -> dict[int, list[dict]]:
    """{clip_id: [{id, name}, ...]} fuer eine Menge Clips (eine Abfrage)."""
    if not clip_ids:
        return {}
    q = ("SELECT cs.clip_id, s.id, s.name FROM video_clip_spieler cs "
         "JOIN spieler s ON s.id = cs.spieler_id "
         f"WHERE cs.clip_id IN ({','.join('?' * len(clip_ids))}) "
         "ORDER BY s.name")
    aus: dict[int, list[dict]] = {cid: [] for cid in clip_ids}
    for r in conn.execute(q, clip_ids).fetchall():
        aus[r["clip_id"]].append({"id": r["id"], "name": r["name"]})
    return aus


def _clips_mit_spielern(conn: sqlite3.Connection, rows) -> list[dict]:
    clips = [dict(r) for r in rows]
    zuord = _clip_spieler(conn, [c["id"] for c in clips])
    for c in clips:
        c["spieler"] = zuord.get(c["id"], [])
    return clips


def clips_alle(conn: sqlite3.Connection) -> list[dict]:
    """Alle eigenen Clips (nur Trainer), je mit der Zahl der Hauptkommentare."""
    rows = conn.execute(
        "SELECT id, titel, notiz, datei, spiel_datum, dauer_s, erstellt_am "
        "FROM video_clip ORDER BY COALESCE(spiel_datum, '') DESC, id DESC"
    ).fetchall()
    zahlen = _kommentar_zahlen(conn)
    return [{**c, "kommentare": zahlen.get(f"clip:{c['id']}", 0)} for c in _clips_mit_spielern(conn, rows)]


def clips_fuer_spieler(conn: sqlite3.Connection, spieler_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT c.id, c.titel, c.notiz, c.datei, c.spiel_datum, c.dauer_s, c.erstellt_am "
        "FROM video_clip c JOIN video_clip_spieler cs ON cs.clip_id = c.id "
        "WHERE cs.spieler_id = ? "
        "ORDER BY COALESCE(c.spiel_datum, '') DESC, c.id DESC", (spieler_id,)
    ).fetchall()
    return _clips_mit_spielern(conn, rows)


def clip_nach_id(conn: sqlite3.Connection, clip_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM video_clip WHERE id = ?", (clip_id,)).fetchone()
    if not r:
        return None
    clip = dict(r)
    clip["spieler"] = _clip_spieler(conn, [clip_id]).get(clip_id, [])
    clip["spieler_ids"] = [s["id"] for s in clip["spieler"]]
    return clip


def clip_spieler_setzen(conn: sqlite3.Connection, clip_id: int,
                        spieler_ids: list[int]) -> None:
    conn.execute("DELETE FROM video_clip_spieler WHERE clip_id = ?", (clip_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO video_clip_spieler (clip_id, spieler_id) VALUES (?, ?)",
        [(clip_id, int(sid)) for sid in spieler_ids])
    conn.commit()


def clip_anlegen(conn: sqlite3.Connection, titel: str, notiz: str | None,
                 datei: str, spiel_datum: str | None, dauer_s: float | None,
                 erstellt_von: int | None, spieler_ids: list[int]) -> int:
    cur = conn.execute(
        "INSERT INTO video_clip (titel, notiz, datei, spiel_datum, dauer_s, erstellt_von) "
        "VALUES (?,?,?,?,?,?)",
        (titel, notiz, datei, spiel_datum, dauer_s, erstellt_von))
    clip_id = int(cur.lastrowid)
    conn.executemany(
        "INSERT OR IGNORE INTO video_clip_spieler (clip_id, spieler_id) VALUES (?, ?)",
        [(clip_id, int(sid)) for sid in spieler_ids])
    conn.commit()
    return clip_id


def clip_metadaten_setzen(conn: sqlite3.Connection, clip_id: int, *,
                          titel: str | None = None, notiz: str | None = None,
                          spiel_datum: str | None = None) -> bool:
    sets, params = [], []
    if titel is not None:
        sets.append("titel = ?"); params.append(titel)
    if notiz is not None:
        sets.append("notiz = ?"); params.append(notiz)
    if spiel_datum is not None:
        sets.append("spiel_datum = ?"); params.append(spiel_datum)
    if not sets:
        return False
    params.append(clip_id)
    cur = conn.execute(f"UPDATE video_clip SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    return cur.rowcount > 0


def clip_loeschen(conn: sqlite3.Connection, clip_id: int) -> str | None:
    """Loescht die Zeile (ON DELETE CASCADE raeumt die Zuordnung) und gibt den
    Dateinamen zurueck, damit der Aufrufer die Datei entfernen kann."""
    r = conn.execute("SELECT datei FROM video_clip WHERE id = ?", (clip_id,)).fetchone()
    if not r:
        return None
    conn.execute("DELETE FROM video_clip WHERE id = ?", (clip_id,))
    conn.commit()
    return r["datei"]
