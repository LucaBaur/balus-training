"""Konten: Name, PIN-Hash, Fehlversuche, Zuordnung zu Spielerinnen."""

from __future__ import annotations

import sqlite3


# =============================================================== Benutzer =====
#  Phase 4: Login + Rollen. PINs werden NUR als Hash gespeichert (siehe auth.py).

def benutzer_nach_name(conn: sqlite3.Connection, name: str) -> dict | None:
    r = conn.execute(
        "SELECT * FROM benutzer WHERE name = ? AND aktiv = 1", (name.strip(),)
    ).fetchone()
    return dict(r) if r else None


def benutzer_nach_id(conn: sqlite3.Connection, bid: int) -> dict | None:
    r = conn.execute(
        "SELECT * FROM benutzer WHERE id = ? AND aktiv = 1", (bid,)
    ).fetchone()
    return dict(r) if r else None


def benutzer_anlegen(conn: sqlite3.Connection, name: str, rolle: str = "spieler",
                     pin_hash: str | None = None,
                     spieler_id: int | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO benutzer (name, rolle, pin_hash, spieler_id) VALUES (?,?,?,?)",
        (name.strip(), rolle, pin_hash, spieler_id),
    )
    conn.commit()
    return int(cur.lastrowid)


def benutzer_pin_setzen(conn: sqlite3.Connection, bid: int, pin_hash: str) -> None:
    # Neue PIN beendet zugleich alle bisherigen Sitzungen: wer die alte PIN kannte (oder ein Handy
    # verloren hat), kommt mit dem alten Cookie nicht mehr hinein.
    conn.execute("UPDATE benutzer SET pin_hash = ?, fehlversuche = 0, sitzung_version = sitzung_version + 1 "
                 "WHERE id = ?", (pin_hash, bid))
    conn.commit()


def benutzer_sitzungen_beenden(conn: sqlite3.Connection, bid: int) -> int:
    """Alle Anmelde-Cookies dieses Kontos ungueltig machen ("Auf allen Geraeten abmelden").
    Gibt die neue Sitzungs-Version zurueck."""
    conn.execute("UPDATE benutzer SET sitzung_version = sitzung_version + 1 WHERE id = ?", (bid,))
    conn.commit()
    r = conn.execute("SELECT sitzung_version FROM benutzer WHERE id = ?", (bid,)).fetchone()
    return int(r["sitzung_version"]) if r else 0


# Fehlversuche werden seit v0.77.3 nicht mehr am Konto gezaehlt und die PIN nie mehr geloescht:
# siehe daten/login.py (Wartezeit statt Sperre). Die Spalte benutzer.fehlversuche bleibt ungenutzt stehen.


def benutzer_liste(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT b.id, b.name, b.rolle, b.spieler_id, b.aktiv, "
        "       (b.pin_hash IS NOT NULL) AS pin_gesetzt "
        "FROM benutzer b ORDER BY b.rolle DESC, b.name"
    ).fetchall()
    return [dict(r) for r in rows]


def trainer_benutzer_ids(conn: sqlite3.Connection) -> list[int]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM benutzer WHERE rolle = 'trainer' AND aktiv = 1")]


def benutzer_ids_fuer_spieler(conn: sqlite3.Connection, spieler_id: int) -> list[int]:
    return [r["id"] for r in conn.execute(
        "SELECT id FROM benutzer WHERE spieler_id = ? AND aktiv = 1", (spieler_id,))]
