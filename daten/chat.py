"""Verlauf des Coach-Chats."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


# -------------------------------------------------------------- Coach-Chat ----

def chat_verlauf(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, ts, rolle, text, roh, titel FROM chat ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def chat_anhaengen(conn: sqlite3.Connection, rolle: str, text: str,
                   roh: str | None = None, titel: str | None = None) -> dict:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO chat (ts, rolle, text, roh, titel) VALUES (?, ?, ?, ?, ?)",
        (ts, rolle, text, roh, titel),
    )
    conn.commit()
    return {"id": int(cur.lastrowid), "ts": ts}


def chat_leeren(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM chat")
    conn.commit()
