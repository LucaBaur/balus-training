"""Spielzug-Ansicht: ein Entscheidungsbaum je Playbook-Seite.

Aufbau: gemeinsame Schritte, dann eine Verzweigung "Was macht die Abwehr?" mit je einer Loesung.
Jeder Knoten hat Text, Stellung (Angriff, Abwehr, Ball) und optional einen Clip der Spielanalyse.
Gespeichert wird immer der GANZE Baum auf einmal (ersetzen statt einzeln aendern): das ist
idempotent (Outbox darf doppelt senden) und alles-oder-nichts (ungueltig -> nichts wird veraendert).

Mandantenfaehig: jede Funktion bekommt `team_id`; fremde Seiten und Clips sind unsichtbar.
"""

from __future__ import annotations

import json
import sqlite3

SPIELZUG_ANGRIFF = ("LA", "HL", "RM", "HR", "RA", "KR")
SPIELZUG_ABWEHR = ("D1", "D2", "D3", "D4", "D5", "D6")
SPIELZUG_FELD_B = 400            # Halbfeld in Zeichen-Einheiten (Tor oben, Mitte unten)
SPIELZUG_FELD_H = 300
SPIELZUG_MAX_TIEFE = 12          # Schritte entlang eines Weges
SPIELZUG_MAX_AESTE = 6           # Lösungen je Verzweigung
SPIELZUG_MAX_TEXT = 1000
SPIELZUG_MAX_REAKTION = 80


def _zahl(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pruefe_stellung(st, wo: str) -> dict:
    """Prueft eine (Teil-)Stellung und gibt die bereinigte Fassung zurueck. ValueError bei Fehlern."""
    if st is None:
        st = {}
    if not isinstance(st, dict):
        raise ValueError(f"{wo}: Stellung ist ungültig")
    sauber: dict = {}
    for seite, erlaubt in (("angriff", SPIELZUG_ANGRIFF), ("abwehr", SPIELZUG_ABWEHR)):
        pos = st.get(seite)
        if pos is None:
            continue
        if not isinstance(pos, dict):
            raise ValueError(f"{wo}: {seite} ist ungültig")
        sauber[seite] = {}
        for name, xy in pos.items():
            if name not in erlaubt:
                raise ValueError(f"{wo}: unbekannte Position {name!r}")
            if not (isinstance(xy, (list, tuple)) and len(xy) == 2 and all(_zahl(v) for v in xy)):
                raise ValueError(f"{wo}: {name} braucht zwei Zahlen [x, y]")
            x, y = xy
            if not (0 <= x <= SPIELZUG_FELD_B and 0 <= y <= SPIELZUG_FELD_H):
                raise ValueError(f"{wo}: {name} liegt außerhalb des Feldes")
            sauber[seite][name] = [x, y]
    ball = st.get("ball")
    if ball is not None:
        if ball not in SPIELZUG_ANGRIFF:
            raise ValueError(f"{wo}: Ball bei unbekannter Spielerin {ball!r}")
        sauber["ball"] = ball
    return sauber


def _clip_im_team(conn: sqlite3.Connection, team_id: int, clip_id) -> bool:
    return conn.execute(
        "SELECT 1 FROM spiel_szene_clip c JOIN spiel_analyse a ON a.id = c.analyse_id "
        "WHERE c.id = ? AND a.team_id = ?", (clip_id, team_id)).fetchone() is not None


def _pruefe_baum(conn: sqlite3.Connection, team_id: int, n, tiefe: int, pfad: str,
                 braucht_reaktion: bool) -> dict:
    """Prueft einen Knoten samt allem darunter und gibt die bereinigte Fassung zurueck."""
    if not isinstance(n, dict):
        raise ValueError(f"{pfad}: Knoten ist ungültig")
    if tiefe > SPIELZUG_MAX_TIEFE:
        raise ValueError(f"Ein Spielzug darf höchstens {SPIELZUG_MAX_TIEFE} Schritte hintereinander haben")
    text = n.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{pfad}: Der Text fehlt")
    if len(text) > SPIELZUG_MAX_TEXT:
        raise ValueError(f"{pfad}: Der Text ist länger als {SPIELZUG_MAX_TEXT} Zeichen")
    reaktion = n.get("reaktion")
    reaktion = reaktion.strip() if isinstance(reaktion, str) else None
    if braucht_reaktion and not reaktion:
        raise ValueError(f"{pfad}: Bei einer Verzweigung braucht jede Lösung eine Beschriftung (was macht die Abwehr?)")
    if reaktion and len(reaktion) > SPIELZUG_MAX_REAKTION:
        raise ValueError(f"{pfad}: Die Beschriftung ist länger als {SPIELZUG_MAX_REAKTION} Zeichen")
    clip = n.get("video_clip_id")
    if clip is not None and not _clip_im_team(conn, team_id, clip):
        raise ValueError(f"{pfad}: Das Video gibt es nicht (oder gehört zu einem anderen Team)")
    kinder = n.get("kinder") or []
    if not isinstance(kinder, list):
        raise ValueError(f"{pfad}: kinder ist ungültig")
    if len(kinder) > SPIELZUG_MAX_AESTE:
        raise ValueError(f"{pfad}: Mehr als {SPIELZUG_MAX_AESTE} Lösungen an einer Verzweigung")
    return {
        "text": text.strip(), "reaktion": reaktion or None,
        "stellung": _pruefe_stellung(n.get("stellung"), pfad),
        "video_clip_id": clip,
        "kinder": [_pruefe_baum(conn, team_id, k, tiefe + 1, f"{pfad} > {i + 1}", len(kinder) > 1)
                   for i, k in enumerate(kinder)],
    }


def _schreibe(conn: sqlite3.Connection, team_id: int, seite_id: int, n: dict,
              parent_id: int | None, sortierung: int) -> None:
    cur = conn.execute(
        "INSERT INTO spielzug_schritt (team_id, seite_id, parent_id, sortierung, reaktion, text, "
        "stellung, video_clip_id) VALUES (?,?,?,?,?,?,?,?)",
        (team_id, seite_id, parent_id, sortierung, n["reaktion"], n["text"],
         json.dumps(n["stellung"], separators=(",", ":")), n["video_clip_id"]))
    for i, k in enumerate(n["kinder"]):
        _schreibe(conn, team_id, seite_id, k, cur.lastrowid, i)


def ansicht_speichern(conn: sqlite3.Connection, team_id: int, seite_id: int, baum: dict) -> None:
    """Ersetzt die Ansicht der Seite durch `baum`. ValueError bei ungueltigen Daten - dann bleibt
    die bisherige Ansicht unveraendert."""
    seite = conn.execute("SELECT kategorie FROM seiten WHERE id = ? AND team_id = ?",
                         (seite_id, team_id)).fetchone()
    if seite is None:
        raise ValueError("Seite nicht gefunden")
    if seite["kategorie"] != "playbook":
        raise ValueError("Eine Spielzug-Ansicht gibt es nur im Playbook")
    sauber = _pruefe_baum(conn, team_id, baum, 1, "Schritt 1", False)
    try:
        conn.execute("DELETE FROM spielzug_schritt WHERE team_id = ? AND seite_id = ?", (team_id, seite_id))
        _schreibe(conn, team_id, seite_id, sauber, None, 0)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise


def ansicht_entfernen(conn: sqlite3.Connection, team_id: int, seite_id: int) -> None:
    conn.execute("DELETE FROM spielzug_schritt WHERE team_id = ? AND seite_id = ?", (team_id, seite_id))
    conn.commit()


def ansicht_laden(conn: sqlite3.Connection, team_id: int, seite_id: int) -> dict | None:
    """Der Baum der Seite oder None, wenn es keine Ansicht gibt."""
    zeilen = conn.execute(
        "SELECT id, parent_id, reaktion, text, stellung, video_clip_id FROM spielzug_schritt "
        "WHERE team_id = ? AND seite_id = ? ORDER BY parent_id IS NOT NULL, parent_id, sortierung, id",
        (team_id, seite_id)).fetchall()
    if not zeilen:
        return None
    knoten = {r["id"]: {"id": r["id"], "text": r["text"], "reaktion": r["reaktion"],
                        "stellung": json.loads(r["stellung"] or "{}"),
                        "video_clip_id": r["video_clip_id"], "kinder": []} for r in zeilen}
    wurzel = None
    for r in zeilen:
        if r["parent_id"] is None:
            wurzel = knoten[r["id"]]
        elif r["parent_id"] in knoten:
            knoten[r["parent_id"]]["kinder"].append(knoten[r["id"]])
    return wurzel


def spielzug_clips(conn: sqlite3.Connection, team_id: int) -> list[dict]:
    """Clips zur Auswahl beim Verknuepfen: Spielzuege aus Spielanalysen des Teams, neueste zuerst."""
    return [dict(r) for r in conn.execute(
        "SELECT c.id AS clip_id, a.gegner, a.datum, z.name, z.ampel, c.bis - c.von AS dauer_s "
        "FROM spiel_szene_clip c "
        "JOIN spiel_analyse a ON a.id = c.analyse_id "
        "JOIN spiel_zug z ON z.analyse_id = c.analyse_id AND z.szene_key = c.szene_key "
        "WHERE a.team_id = ? ORDER BY COALESCE(a.datum, '') DESC, c.id", (team_id,))]


def spielzug_schritt_clip(conn: sqlite3.Connection, team_id: int, schritt_id: int) -> dict | None:
    """Der Clip, der an einer Loesung haengt (Zeile aus spiel_szene_clip), sonst None."""
    r = conn.execute(
        "SELECT c.* FROM spielzug_schritt s JOIN spiel_szene_clip c ON c.id = s.video_clip_id "
        "WHERE s.id = ? AND s.team_id = ?", (schritt_id, team_id)).fetchone()
    return dict(r) if r else None
