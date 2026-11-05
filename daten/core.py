"""Verbindung, Schema anlegen und Migrationen."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import aemter

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
    conn.executescript(SCHEMA)
    _migriere(conn)
    conn.commit()


def _spalte_ergaenzen(conn: sqlite3.Connection, tabelle: str, spalte: str,
                      definition: str) -> None:
    """Fuegt eine Spalte hinzu, falls sie fehlt (SQLite kennt kein
    ADD COLUMN IF NOT EXISTS)."""
    vorhanden = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabelle})")}
    if spalte not in vorhanden:
        conn.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {definition}")


def _migriere(conn: sqlite3.Connection) -> None:
    """Schema-Anpassungen fuer bestehende Datenbanken (idempotent)."""
    _spalte_ergaenzen(conn, "nutzung", "dauer_s", "INTEGER")
    spalten = {r["name"] for r in conn.execute("PRAGMA table_info(spiele)")}
    if "token" not in spalten:
        conn.execute("ALTER TABLE spiele ADD COLUMN token TEXT")

    # Erwaermungsspiele laufen manchmal mit drei oder vier Teams. 'teams' haelt
    # ALLE Teams als JSON-Liste von Listen; 'team_a'/'team_b' werden weiter
    # gefuellt (die ersten beiden), damit alte Zeilen und Abfragen gueltig
    # bleiben. Beim Lesen gewinnt 'teams', wenn es gesetzt ist.
    _spalte_ergaenzen(conn, "spiele", "teams", "TEXT")
    _spalte_ergaenzen(conn, "spiel_event", "szene_key", "TEXT")
    _spalte_ergaenzen(conn, "spiel_zug", "szene_key", "TEXT")
    # Partieller Unique-Index: derselbe Token kann nur EIN Spiel erzeugen,
    # aber alte Zeilen ohne Token (NULL) kollidieren nicht miteinander.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_spiele_token "
        "ON spiele(token) WHERE token IS NOT NULL"
    )

    # Phase 3: Spieler-Profil um die Anytype-Felder erweitern (alles optional).
    # 'position' bleibt grob (Tor/Feld, von Team-/ELO-Logik genutzt);
    # 'position_angriff' haelt zusaetzlich das Detail (Tor/Mitte/Aussen/Kreis).
    for spalte in ("position_angriff", "position_abwehr", "staerken", "schwaechen",
                   "absprache", "urlaub", "trainingsbeteiligung", "notizen"):
        _spalte_ergaenzen(conn, "spieler", spalte, "TEXT")

    # Portrait: die Spielerin waehlt selbst. 'portrait_v' = Zeitstempel des
    # hochgeladenen Fotos (0 = keins; dient auch als Cache-Schluessel in der URL),
    # 'portrait_modus' = 'foto' (Standard) oder 'initial' (nur Anfangsbuchstabe).
    _spalte_ergaenzen(conn, "spieler", "portrait_v", "INTEGER NOT NULL DEFAULT 0")
    _spalte_ergaenzen(conn, "spieler", "portrait_modus", "TEXT NOT NULL DEFAULT 'foto'")

    # Dedupe-/Zuordnungs-Indexe fuer den Anytype-Import (partiell: NULL kollidiert
    # nicht). anytype_id ist je Objekt eindeutig; spielerplus_event_id ordnet ein
    # Training seiner SpielerPlus-Quelle zu.
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_trainings_anytype "
                 "ON trainings(anytype_id) WHERE anytype_id IS NOT NULL")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_trainings_spevent "
                 "ON trainings(spielerplus_event_id) WHERE spielerplus_event_id IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_trainings_datum ON trainings(datum)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_uebungen_anytype "
                 "ON uebungen(anytype_id) WHERE anytype_id IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_uebungen_kategorie ON uebungen(kategorie)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_seiten_anytype "
                 "ON seiten(anytype_id) WHERE anytype_id IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_seiten_kategorie ON seiten(kategorie)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_teilnahme_spieler "
                 "ON training_teilnahme(spieler_id)")

    # Phase 4: Fehlversuch-Zaehler am Benutzer (bestehende DBs nachziehen).
    _spalte_ergaenzen(conn, "benutzer", "fehlversuche", "INTEGER NOT NULL DEFAULT 0")
    # Zu-/Absage-Grund an der Teilnahme (Pflicht bei Absage).
    _spalte_ergaenzen(conn, "training_teilnahme", "grund", "TEXT")

    # Termine sind nicht nur Trainings: Test- und Ligaspiele stehen in derselben
    # Tabelle (gleiche Teilnahme, gleiche Erinnerungen) und unterscheiden sich
    # ueber 'art'. Bestand bleibt 'training' - darum der Default.
    #   gegner  : Name des Gegners (nur Spiele)
    #   heim    : 1 = Heimspiel, 0 = Auswaertsspiel (NULL bei Trainings)
    #   abfahrt : 'HH:MM' Abfahrt/Treffpunkt - bei Auswaertsspielen das Wichtigste
    _spalte_ergaenzen(conn, "trainings", "art", "TEXT NOT NULL DEFAULT 'training'")
    _spalte_ergaenzen(conn, "trainings", "gegner", "TEXT")
    _spalte_ergaenzen(conn, "trainings", "heim", "INTEGER")
    _spalte_ergaenzen(conn, "trainings", "abfahrt", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_trainings_art ON trainings(art, datum)")

    # Szenen-Videos: schneller Zugriff auf die Clips einer Spielerin.
    conn.execute("CREATE INDEX IF NOT EXISTS ix_clip_spieler "
                 "ON video_clip_spieler(spieler_id)")

    # Ämter der Mannschaft (Tabellen und Standard-Ämter, siehe aemter.py).
    aemter.starte(conn)
