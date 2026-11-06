"""Versionierte Schema-Migrationen.

Die Datenbank merkt sich ihren Stand in `PRAGMA user_version`. Jede Migration hat eine
fortlaufende Nummer und laeuft genau einmal, in einer eigenen Transaktion: klappt sie
nicht, bleibt die Datenbank auf dem alten Stand und der Fehler wird laut (der Dienst startet
nicht, `deploy.sh` spielt zurueck).

So kommt eine Aenderung dazu:
  1. Funktion `mNNN_kurzer_name(conn)` schreiben (naechste freie Nummer).
  2. Sie unten in MIGRATIONEN eintragen.
  3. Nichts weiter - weder `user_version` von Hand setzen noch eine Aenderung in `_spalte_ergaenzen`
     verstecken. Neue Tabellen duerfen weiter in schema.py stehen (CREATE TABLE IF NOT EXISTS);
     alles, was bestehende Tabellen oder Daten aendert, gehoert hierher.

Migrationen duerfen kein `executescript` benutzen (das beendet die Transaktion) und kein
`commit()` aufrufen.
"""

from __future__ import annotations

import sqlite3
from typing import Callable


def _spalte_ergaenzen(conn: sqlite3.Connection, tabelle: str, spalte: str,
                      definition: str) -> None:
    """Fuegt eine Spalte hinzu, falls sie fehlt (SQLite kennt kein
    ADD COLUMN IF NOT EXISTS)."""
    vorhanden = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabelle})")}
    if spalte not in vorhanden:
        conn.execute(f"ALTER TABLE {tabelle} ADD COLUMN {spalte} {definition}")


def m001_bestand(conn: sqlite3.Connection) -> None:
    """Alles, was bis v0.70 als `_migriere` bei jedem Start lief (idempotent). Alte Datenbanken
    stehen auf user_version 0 und holen es einmal nach; frische Datenbanken laufen hier ebenfalls durch."""
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


KASSENWART_TEXT_ALT = "Führt die Mannschaftskasse. Die Kasse selbst ist noch nicht in der App."
KASSENWART_TEXT_NEU = "Führt die Mannschaftskasse: bucht Strafen, Einzahlungen, Ausgaben und Einnahmen und zeigt den Kassenstand."


def m002_kassenwart_text(conn: sqlite3.Connection) -> None:
    """Die Kasse ist jetzt in der App: der Standardtext des Amts Kassenwart stimmt nicht mehr.
    Nur ersetzen, wenn der Trainer ihn nicht selbst geaendert hat. Die Tabelle `amt` legt erst
    `aemter.starte` an, die nach den Migrationen laeuft - auf einer frischen Datenbank gibt es sie hier
    noch nicht (dort setzt AEMTER_START den neuen Text gleich)."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'amt'").fetchone() is None:
        return
    conn.execute("UPDATE amt SET beschreibung = ? WHERE schluessel = 'kassenwart' AND beschreibung = ?",
                 (KASSENWART_TEXT_NEU, KASSENWART_TEXT_ALT))


# (Nummer, Name, Funktion) - Nummern fortlaufend ab 1, neue Eintraege nur ans Ende.
MIGRATIONEN: list[tuple[int, str, Callable[[sqlite3.Connection], None]]] = [
    (1, "bestand", m001_bestand),
    (2, "kassenwart_text", m002_kassenwart_text),
]


def letzte_version() -> int:
    return max((nr for nr, _, _ in MIGRATIONEN), default=0)


def aktuelle_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migriere(conn: sqlite3.Connection) -> list[int]:
    """Wendet alle noch offenen Migrationen an und gibt ihre Nummern zurueck."""
    if aktuelle_version(conn) >= letzte_version():
        return []                       # Normalfall bei jedem Start: nichts zu tun, kein Schreibzugriff
    conn.commit()
    angewendet: list[int] = []
    for nr, name, fn in sorted(MIGRATIONEN, key=lambda m: m[0]):
        conn.execute("BEGIN IMMEDIATE")  # sperrt gegen einen zweiten Prozess (Cron + Dienst)
        try:
            if aktuelle_version(conn) >= nr:   # inzwischen von jemand anderem erledigt
                conn.rollback()
                continue
            fn(conn)
            conn.execute(f"PRAGMA user_version = {int(nr)}")
            conn.commit()
        except BaseException as e:
            conn.rollback()
            raise RuntimeError(f"Migration {nr:03d} ({name}) fehlgeschlagen: {e}") from e
        angewendet.append(nr)
    return angewendet
