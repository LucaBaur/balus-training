"""Verbindung, Schema anlegen und Migrationen."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aemter

from .migrationen import migriere
from .schema import SCHEMA


DB_PFAD = Path(__file__).resolve().parent.parent / "elo.db"


def verbinde(pfad: Path | str = DB_PFAD) -> sqlite3.Connection:
    # check_same_thread=False ist hier PFLICHT, nicht Bequemlichkeit: FastAPI
    # legt die Verbindung in der Dependency (hole_conn) in einem Worker-Thread
    # an, ruft den Endpunkt in einem ZWEITEN und schliesst sie in einem DRITTEN.
    # Mit der Standard-Pruefung wirft SQLite dabei sporadisch
    # "SQLite objects created in a thread can only be used in that same thread"
    # -> HTTP 500. Gefaehrlich waere das nur bei echt gleichzeitigem Zugriff;
    # jede Anfrage bekommt aber ihre EIGENE Verbindung und nutzt sie nacheinander.
    conn = sqlite3.connect(pfad, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn



def init_db(conn: sqlite3.Connection) -> None:
    """Schema anlegen, offene Migrationen anwenden, Standard-Aemter sicherstellen.
    Laeuft bei jedem Start (Dienst und Cron-Skripte) und ist dann ein billiger No-op."""
    conn.executescript(SCHEMA)
    migriere(conn)
    aemter.starte(conn)      # Aemter-Tabellen und Standard-Aemter, siehe aemter.py
    conn.commit()
