"""Web-Push: Abos, Praeferenzen und Einmal-Sperren."""

from __future__ import annotations

import sqlite3


# ============================================================= Web-Push =====

def push_abo_speichern(conn: sqlite3.Connection, benutzer_id: int, endpoint: str,
                       p256dh: str, auth: str) -> None:
    conn.execute(
        "INSERT INTO push_abo (benutzer_id, endpoint, p256dh, auth) VALUES (?,?,?,?) "
        "ON CONFLICT(endpoint) DO UPDATE SET benutzer_id=excluded.benutzer_id, "
        "  p256dh=excluded.p256dh, auth=excluded.auth",
        (benutzer_id, endpoint, p256dh, auth))
    conn.commit()


def push_abo_loeschen(conn: sqlite3.Connection, endpoint: str) -> None:
    conn.execute("DELETE FROM push_abo WHERE endpoint = ?", (endpoint,))
    conn.commit()


def push_abo_loeschen_id(conn: sqlite3.Connection, abo_id: int) -> None:
    conn.execute("DELETE FROM push_abo WHERE id = ?", (abo_id,))
    conn.commit()


def push_abos_fuer(conn: sqlite3.Connection, benutzer_ids: list[int]) -> list[dict]:
    if not benutzer_ids:
        return []
    ph = ",".join("?" for _ in benutzer_ids)
    rows = conn.execute(
        f"SELECT id, endpoint, p256dh, auth FROM push_abo WHERE benutzer_id IN ({ph})",
        benutzer_ids).fetchall()
    return [dict(r) for r in rows]


def push_praeferenz_setzen(conn: sqlite3.Connection, benutzer_id: int, art: str, an: bool) -> None:
    conn.execute(
        "INSERT INTO push_praeferenz (benutzer_id, art, an) VALUES (?,?,?) "
        "ON CONFLICT(benutzer_id, art) DO UPDATE SET an = excluded.an",
        (benutzer_id, art, 1 if an else 0))
    conn.commit()


def push_praeferenzen(conn: sqlite3.Connection, benutzer_id: int) -> dict[str, bool]:
    """Nur die gespeicherten Einstellungen; was fehlt, gilt als eingeschaltet."""
    return {r["art"]: bool(r["an"]) for r in conn.execute(
        "SELECT art, an FROM push_praeferenz WHERE benutzer_id = ?", (benutzer_id,))}


def push_filtern(conn: sqlite3.Connection, benutzer_ids: list[int], art: str | None) -> list[int]:
    """Benutzer, die diese Art von Mitteilung nicht abgeschaltet haben. Ohne Art bleibt alles."""
    ids = list(benutzer_ids)
    if art is None or not ids:
        return ids
    ph = ",".join("?" for _ in ids)
    aus = {r["benutzer_id"] for r in conn.execute(
        f"SELECT benutzer_id FROM push_praeferenz WHERE art = ? AND an = 0 AND benutzer_id IN ({ph})",
        [art, *ids])}
    return [i for i in ids if i not in aus]


def push_einmalig(conn: sqlite3.Connection, schluessel: str) -> bool:
    """True genau beim ersten Aufruf je Schluessel (Idempotenz fuer Cron und Wiederholungen)."""
    cur = conn.execute("INSERT OR IGNORE INTO push_gesendet (schluessel) VALUES (?)", (schluessel,))
    conn.commit()
    return cur.rowcount == 1
