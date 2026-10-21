"""SQLite-Datenhaltung fuer das ELO-System.

Quelle der Wahrheit sind hier gespeicherten Werte; Anytype bekommt spaeter nur
die aktuelle ELO zurueckgeschrieben. Der ``elo_verlauf`` erlaubt Undo und
Neuberechnung.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import elo

DB_PFAD = Path(__file__).with_name("elo.db")

# Termin-Arten. 'training' ist der Normalfall (und der Default in der DB),
# 'testspiel'/'ligaspiel' sind Spiele: sie haben einen Gegner, sind Heim- oder
# Auswaertsspiel und tragen bei Auswaerts eine Abfahrtszeit.
ARTEN = ("training", "testspiel", "ligaspiel")
SPIEL_ARTEN = ("testspiel", "ligaspiel")

SCHEMA = """
CREATE TABLE IF NOT EXISTS spieler (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    anytype_id     TEXT,
    spielerplus_id TEXT,
    position       TEXT    NOT NULL DEFAULT 'Feld',   -- 'Tor' oder 'Feld'
    elo            INTEGER NOT NULL,
    spiele_gesamt  INTEGER NOT NULL DEFAULT 0,
    aktiv          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS spiele (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    datum      TEXT    NOT NULL,
    team_a     TEXT    NOT NULL,   -- JSON-Liste von spieler.id
    team_b     TEXT    NOT NULL,
    ergebnis   TEXT    NOT NULL,   -- 'A' / 'U' / 'B'
    token      TEXT,               -- Idempotenz-Schluessel des Clients (einmalig je Spiel)
    erstellt_am TEXT   NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS elo_verlauf (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    spiel_id    INTEGER NOT NULL REFERENCES spiele(id) ON DELETE CASCADE,
    spieler_id  INTEGER NOT NULL REFERENCES spieler(id),
    elo_vorher  INTEGER NOT NULL,
    delta       INTEGER NOT NULL,
    elo_nachher INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chat (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT NOT NULL,                  -- ISO mit Zeitzone (UTC)
    rolle TEXT NOT NULL,                  -- 'user' / 'bot' / 'info' / 'plan'
    text  TEXT NOT NULL,                  -- angezeigter Text (bei 'plan': Markdown)
    roh   TEXT,                           -- rohe Modellantwort (fuer LLM-Kontext)
    titel TEXT                            -- bei 'plan': Titel
);

-- ==========================================================================
--  Phase 3: Anytype abloesen. Alles, was heute im Anytype-Space 'Frauen TVG'
--  liegt, bekommt hier eine native Heimat. Strukturiert, wo Struktur da ist
--  (Trainings, Teilnahme, Uebungen); ein flexibles 'seiten'-Wiki fuer den Rest
--  (Playbook, Gegnercheck, Saison-Orga, Statistik-Notizen, Besprechungen).
-- ==========================================================================

-- Trainingstermine (Anytype-Typ 'training'). Quelle der Teilnahme ist
-- SpielerPlus; 'spielerplus_event_id' dient als Dedupe-Schluessel beim Import.
CREATE TABLE IF NOT EXISTS trainings (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    datum                 TEXT    NOT NULL,           -- ISO 'YYYY-MM-DD'
    titel                 TEXT    NOT NULL DEFAULT '',
    uhrzeit               TEXT,                       -- optional 'HH:MM'
    ort                   TEXT,                       -- optional
    inhalt                TEXT,                       -- freier Trainingsinhalt (Anytype 'Inhalt')
    plan_markdown         TEXT,                       -- Coach-Plan (war Anytype-Body)
    spielerplus_event_id  TEXT,                       -- Zuordnung/Dedupe zu SpielerPlus
    anytype_id            TEXT,                       -- Herkunft aus Anytype (Migration)
    erstellt_am           TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Teilnahme je Training x Spielerin. status: 'anwesend'/'abgesagt'/
-- 'unsicher'/'nominiert'. quelle: 'spielerplus'/'manuell'.
CREATE TABLE IF NOT EXISTS training_teilnahme (
    training_id  INTEGER NOT NULL REFERENCES trainings(id) ON DELETE CASCADE,
    spieler_id   INTEGER NOT NULL REFERENCES spieler(id)   ON DELETE CASCADE,
    status       TEXT    NOT NULL DEFAULT 'nominiert',
    quelle       TEXT    NOT NULL DEFAULT 'spielerplus',
    PRIMARY KEY (training_id, spieler_id)
);

-- Trainingsplan als Bloecke: "wann mache ich was". Ersetzt das eine grosse
-- Textfeld 'trainings.plan_markdown' (das bleibt fuer Altbestand liegen).
-- NUR fuer das Trainerteam sichtbar - erzwungen in app.py, nicht im Frontend.
-- 'dauer_min' ist ABSICHTLICH optional: viele Plaene stehen ohne Minuten da.
-- Dann entfaellt fuer diesen Block die Uhrzeit, der Rest rechnet weiter.
CREATE TABLE IF NOT EXISTS training_block (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    training_id  INTEGER NOT NULL REFERENCES trainings(id) ON DELETE CASCADE,
    reihenfolge  INTEGER NOT NULL DEFAULT 0,
    dauer_min    INTEGER,
    titel        TEXT    NOT NULL DEFAULT '',
    notiz        TEXT
);
CREATE INDEX IF NOT EXISTS ix_training_block ON training_block(training_id, reihenfolge);

-- Uebungssammlung (Idee 3). 'zuletzt_gemacht' wird aus training_uebung
-- abgeleitet und erlaubt die Auswertung 'lang nicht mehr trainiert'.
CREATE TABLE IF NOT EXISTS uebungen (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    kategorie       TEXT,                             -- 'Aufwaermen'/'Wurf'/'Kraft'/'Konter'/'Abschluss'/'Technik'/'Taktik'/'Ausdauer'...
    phase           TEXT,                             -- 'Erwaermung'/'Hauptteil'/'Abschluss'
    beschreibung    TEXT,                             -- kurz
    markdown        TEXT,                             -- ausfuehrlich
    zuletzt_gemacht TEXT,                             -- ISO Datum (abgeleitet)
    anytype_id      TEXT,
    aktiv           INTEGER NOT NULL DEFAULT 1,
    erstellt_am     TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Welche Uebung kam in welchem Training vor (fuer Statistik + 'lang nicht gemacht').
CREATE TABLE IF NOT EXISTS training_uebung (
    training_id  INTEGER NOT NULL REFERENCES trainings(id) ON DELETE CASCADE,
    uebung_id    INTEGER NOT NULL REFERENCES uebungen(id)  ON DELETE CASCADE,
    reihenfolge  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (training_id, uebung_id)
);

-- Laufchallenge-Ergebnis je Spielerin (aus dem separaten Laufchallenge-Projekt
-- importiert). Pro Challenge eine Zeile; km = Summe der LAUF-Distanzen (andere
-- Aktivitaeten wie Radfahren zaehlen separat, wie in der Original-Wertung).
CREATE TABLE IF NOT EXISTS laufchallenge (
    spieler_id   INTEGER NOT NULL REFERENCES spieler(id) ON DELETE CASCADE,
    challenge    TEXT    NOT NULL,
    km           REAL    NOT NULL DEFAULT 0,
    laeufe       INTEGER NOT NULL DEFAULT 0,
    andere       INTEGER NOT NULL DEFAULT 0,   -- andere Aktivitaeten (Rad etc.)
    rang         INTEGER,                       -- Platz in der Challenge
    teilnehmer   INTEGER,                       -- Teilnehmerzahl der Challenge
    PRIMARY KEY (spieler_id, challenge)
);

-- Flexibles Wiki fuer alles ohne feste Struktur (Anytype-Typen 'page',
-- 'besprechung', 'collection'). Hierarchie ueber parent_id.
CREATE TABLE IF NOT EXISTS seiten (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    titel        TEXT    NOT NULL,
    kategorie    TEXT,                                -- 'playbook'/'gegner'/'saison'/'orga'/'statistik'/'besprechung'/'notiz'
    parent_id    INTEGER REFERENCES seiten(id) ON DELETE SET NULL,
    markdown     TEXT,
    tags         TEXT,                                -- JSON-Liste von Strings
    sortierung   INTEGER NOT NULL DEFAULT 0,
    anytype_id   TEXT,
    anytype_typ  TEXT,                                -- Herkunftstyp (page/besprechung/collection)
    aktualisiert TEXT    NOT NULL DEFAULT (datetime('now')),
    erstellt_am  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Phase 4: Login + Rollen. Ein Benutzer je Trainer/Spielerin. PIN als Hash
-- (nie im Klartext). 'spieler_id' verknuepft eine Spieler-Rolle mit ihrem
-- Kader-Eintrag (fuer 'nur eigene Daten').
CREATE TABLE IF NOT EXISTS benutzer (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,             -- Login-/Anzeigename
    rolle        TEXT    NOT NULL DEFAULT 'spieler',  -- 'trainer' | 'spieler'
    pin_hash     TEXT,                                -- pbkdf2, NULL = keine/gesperrte PIN
    spieler_id   INTEGER REFERENCES spieler(id) ON DELETE SET NULL,
    aktiv        INTEGER NOT NULL DEFAULT 1,
    fehlversuche INTEGER NOT NULL DEFAULT 0,           -- 3 falsche -> PIN wird gesperrt
    erstellt_am  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Phase 4: Web-Push-Abos (ein Geraet = ein Abo; ein Benutzer kann mehrere haben).
CREATE TABLE IF NOT EXISTS push_abo (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    benutzer_id  INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
    endpoint     TEXT    NOT NULL UNIQUE,
    p256dh       TEXT    NOT NULL,
    auth         TEXT    NOT NULL,
    erstellt_am  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Szenen-Videos: einzelne Spielszenen, geschnitten und beschriftet am PC
-- (Projekt "Balu-Videoschnitt"), hier nur als fertige MP4 abgelegt. Die Datei
-- liegt unter media/clips/ (nicht im Repo, wie die Portraits); 'datei' ist der
-- reine Dateiname. Eine Szene kann mehrere Spielerinnen betreffen.
CREATE TABLE IF NOT EXISTS video_clip (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    titel        TEXT    NOT NULL,
    notiz        TEXT,
    datei        TEXT    NOT NULL,                       -- Dateiname in media/clips/
    spiel_datum  TEXT,                                   -- YYYY-MM-DD der Aufnahme
    dauer_s      REAL,
    erstellt_von INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
    erstellt_am  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS video_clip_spieler (
    clip_id    INTEGER NOT NULL REFERENCES video_clip(id) ON DELETE CASCADE,
    spieler_id INTEGER NOT NULL REFERENCES spieler(id)    ON DELETE CASCADE,
    PRIMARY KEY (clip_id, spieler_id)
);

-- Spielanalysen: ganzes Spielvideo + Zeitstempel, erfasst am PC (Projekt
-- "Balu-Spielanalyse"). 'extern_id' ist die ID der Desktop-App; ein erneuter
-- Upload desselben Spiels ersetzt Ereignisse/Spielzuege statt zu verdoppeln.
-- Die Videodatei liegt unter media/spiele/ ('datei' = reiner Dateiname, NULL
-- solange nur die Daten hochgeladen sind).
CREATE TABLE IF NOT EXISTS spiel_analyse (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    extern_id    TEXT    NOT NULL UNIQUE,
    gegner       TEXT    NOT NULL,
    datum        TEXT,                                   -- YYYY-MM-DD
    art          TEXT,
    datei        TEXT,
    erstellt_von INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
    erstellt_am  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Ereignisse der EIGENEN Mannschaft: tor, fehlwurf, ballverlust, strafe,
-- siebenmeter, parade. t = Sekunden im Video.
CREATE TABLE IF NOT EXISTS spiel_event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    analyse_id INTEGER NOT NULL REFERENCES spiel_analyse(id) ON DELETE CASCADE,
    typ        TEXT    NOT NULL,
    t          REAL    NOT NULL,
    spieler_id INTEGER REFERENCES spieler(id) ON DELETE SET NULL,
    assist_id  INTEGER REFERENCES spieler(id) ON DELETE SET NULL,
    detail     TEXT,
    szene_key  TEXT                                      -- Kennung der Szene (-> spiel_szene_clip)
);

-- Spielzuege mit Ampel (gruen = Tor, orange = ok, rot = elementarer Fehler).
CREATE TABLE IF NOT EXISTS spiel_zug (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    analyse_id INTEGER NOT NULL REFERENCES spiel_analyse(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    t_start    REAL    NOT NULL,
    t_ende     REAL    NOT NULL,
    ampel      TEXT    NOT NULL,
    kommentar  TEXT,
    szene_key  TEXT
);

-- Kurze Clips je Szene (am PC aus dem Spielvideo geschnitten). Zugeordnet wird ueber
-- 'szene_key', nicht ueber die Zeilen-ID: Daten-Uploads ersetzen Ereignisse/Spielzuege,
-- die Clips bleiben davon unberuehrt. 'von'/'bis' = Ausschnitt im Spielvideo (Sekunden),
-- damit die Desktop-App erkennt, ob ein Clip nach einer Korrektur neu geschnitten werden muss.
CREATE TABLE IF NOT EXISTS spiel_szene_clip (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    analyse_id  INTEGER NOT NULL REFERENCES spiel_analyse(id) ON DELETE CASCADE,
    szene_key   TEXT    NOT NULL,
    datei       TEXT    NOT NULL,                        -- Dateiname in media/szenen/
    von         REAL    NOT NULL,
    bis         REAL    NOT NULL,
    erstellt_am TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (analyse_id, szene_key)
);

CREATE TABLE IF NOT EXISTS spiel_zug_spieler (
    zug_id     INTEGER NOT NULL REFERENCES spiel_zug(id) ON DELETE CASCADE,
    spieler_id INTEGER NOT NULL REFERENCES spieler(id)   ON DELETE CASCADE,
    PRIMARY KEY (zug_id, spieler_id)
);

CREATE INDEX IF NOT EXISTS idx_spiel_event_analyse ON spiel_event(analyse_id);
CREATE INDEX IF NOT EXISTS idx_spiel_zug_analyse   ON spiel_zug(analyse_id);

-- Nutzung: wer wann die App geoeffnet, welchen Bereich besucht, welches Video
-- angesehen hat. Nur fuer die Trainer-Seite "Team -> Nutzung". Keine IP, keine
-- Geraetedaten. 'zeit' ist UTC. 'ziel' ist je nach Typ ein Bereich ("ich/videos")
-- oder ein Video ("clip:5", "szene:12", "spiel:3"); 'info' haelt den Titel zum
-- Zeitpunkt des Ansehens, damit er auch nach dem Loeschen des Videos lesbar bleibt.
CREATE TABLE IF NOT EXISTS nutzung (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
    zeit        TEXT    NOT NULL DEFAULT (datetime('now')),
    typ         TEXT    NOT NULL,                        -- besuch | bereich | video
    ziel        TEXT,
    info        TEXT
);
CREATE INDEX IF NOT EXISTS idx_nutzung_benutzer ON nutzung(benutzer_id, zeit);

-- Geraete: je Konto und Geraetekombination eine Zeile (grobe Angaben, damit
-- Fehler zu Android/iOS/Browser-Versionen passen). Keine Kennungen, keine IP,
-- kein Standort. Bei jedem Besuch wird 'zuletzt' und die App-Version aufgefrischt.
CREATE TABLE IF NOT EXISTS geraet (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
    os          TEXT    NOT NULL DEFAULT '',             -- "Android 13", "iOS 17"
    browser     TEXT    NOT NULL DEFAULT '',             -- "Chrome 126", "Safari 17"
    modus       TEXT    NOT NULL DEFAULT '',             -- installiert | Browser | Android-App
    bildschirm  TEXT    NOT NULL DEFAULT '',             -- "412x915"
    modell      TEXT    NOT NULL DEFAULT '',             -- nur wenn der Browser es nennt
    app_version TEXT    NOT NULL DEFAULT '',
    sw          INTEGER NOT NULL DEFAULT 0,              -- Service Worker aktiv
    erstmals    TEXT    NOT NULL DEFAULT (datetime('now')),
    zuletzt     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (benutzer_id, os, browser, modus, bildschirm, modell)
);

-- Fehlerberichte aus der App (JavaScript-Fehler, Videos die nicht laden).
-- 'geraet' ist eine Kurzfassung zum Zeitpunkt des Fehlers.
CREATE TABLE IF NOT EXISTS fehler (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
    zeit        TEXT    NOT NULL DEFAULT (datetime('now')),
    quelle      TEXT,                                    -- script | promise | video
    meldung     TEXT    NOT NULL,
    ort         TEXT,                                    -- Bereich, z. B. "ich/videos"
    app_version TEXT,
    geraet      TEXT
);
CREATE INDEX IF NOT EXISTS idx_fehler_zeit ON fehler(zeit);
"""


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


# ---------------------------------------------------------------- Spieler ----

def spieler_anlegen(
    conn: sqlite3.Connection,
    name: str,
    stufe: str = "mittel",
    position: str = "Feld",
    anytype_id: str | None = None,
    spielerplus_id: str | None = None,
) -> int:
    start_elo = elo.STUFEN.get(stufe, elo.START_ELO_DEFAULT)
    cur = conn.execute(
        "INSERT INTO spieler (name, anytype_id, spielerplus_id, position, elo) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, anytype_id, spielerplus_id, position, start_elo),
    )
    conn.commit()
    return int(cur.lastrowid)


def aktive_spieler(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM spieler WHERE aktiv = 1 ORDER BY name"
    ).fetchall()
    return [dict(r) for r in rows]


def spieler_nach_ids(conn: sqlite3.Connection, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    platzhalter = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT * FROM spieler WHERE id IN ({platzhalter})", ids
    ).fetchall()
    nach_id = {r["id"]: dict(r) for r in rows}
    return [nach_id[i] for i in ids if i in nach_id]


def rangliste(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM spieler WHERE aktiv = 1 ORDER BY elo DESC, name"
    ).fetchall()
    return [dict(r) for r in rows]


def spieler_aktualisieren(
    conn: sqlite3.Connection,
    spieler_id: int,
    stufe: str | None = None,
    position: str | None = None,
    aktiv: bool | None = None,
    position_angriff: str | None = None,
) -> None:
    """Aendert Stufe/Position/Aktiv/Angriffsposition. Stufe setzt die ELO nur,
    solange die Spielerin noch kein Spiel hat (sonst wuerde der Fortschritt
    ueberschrieben).

    `position_angriff` ist Freitext mit '/' als Trenner ("Halblinks/Kreis") -
    so stehen die Werte schon aus Anytype drin. Enthaelt die Angabe "Tor",
    zieht die grobe `position` (Tor/Feld) automatisch mit, damit die
    Team-Aufteilung weiter die Torhueterinnen findet."""
    row = conn.execute(
        "SELECT spiele_gesamt FROM spieler WHERE id = ?", (spieler_id,)
    ).fetchone()
    if row is None:
        return
    felder, werte = [], []
    if stufe is not None and stufe in elo.STUFEN and row["spiele_gesamt"] == 0:
        felder.append("elo = ?")
        werte.append(elo.STUFEN[stufe])
    if position_angriff is not None:
        felder.append("position_angriff = ?")
        werte.append(position_angriff.strip()[:80])
        if position is None:                    # grobe Position mitziehen
            position = "Tor" if "tor" in position_angriff.lower() else "Feld"
    if position is not None:
        felder.append("position = ?")
        werte.append(position)
    if aktiv is not None:
        felder.append("aktiv = ?")
        werte.append(1 if aktiv else 0)
    if not felder:
        return
    werte.append(spieler_id)
    conn.execute(f"UPDATE spieler SET {', '.join(felder)} WHERE id = ?", werte)
    conn.commit()


def import_kader(conn: sqlite3.Connection, kader: list[dict]) -> dict:
    """Spielerinnen aus Anytype einspielen. Neue werden mit Stufe 'mittel'
    angelegt; vorhandene (per anytype_id) bekommen Name/Position/spielerplus_id
    aktualisiert, ihre ELO bleibt unangetastet."""
    neu = aktualisiert = 0
    for k in kader:
        aid = k.get("anytype_id")
        vorhanden = None
        if aid:
            vorhanden = conn.execute(
                "SELECT id FROM spieler WHERE anytype_id = ?", (aid,)
            ).fetchone()
        if vorhanden:
            conn.execute(
                "UPDATE spieler SET name = ?, position = ?, spielerplus_id = ? WHERE id = ?",
                (k["name"], k["position"], k.get("spielerplus_id"), vorhanden["id"]),
            )
            aktualisiert += 1
        else:
            spieler_anlegen(
                conn, k["name"], stufe="mittel", position=k["position"],
                anytype_id=aid, spielerplus_id=k.get("spielerplus_id"),
            )
            neu += 1
    conn.commit()
    return {"neu": neu, "aktualisiert": aktualisiert, "gesamt": len(kader)}


# ------------------------------------------------------------------ Spiele ----

def _deltas_aus_verlauf(conn: sqlite3.Connection, spiel_id: int) -> dict[int, int]:
    """Rekonstruiert die Deltas eines bereits eingetragenen Spiels."""
    rows = conn.execute(
        "SELECT spieler_id, delta FROM elo_verlauf WHERE spiel_id = ?", (spiel_id,)
    ).fetchall()
    return {r["spieler_id"]: r["delta"] for r in rows}


def teams_ids_von(row) -> list[list[int]]:
    """Die Teams eines Spiels als Listen von Spieler-IDs.

    Neue Spiele stehen in 'teams' (JSON-Liste von Listen). Aeltere Zeilen
    haben nur 'team_a'/'team_b' - die werden hier zu zwei Teams."""
    roh = row["teams"] if "teams" in row.keys() else None
    if roh:
        try:
            teams = json.loads(roh)
            if isinstance(teams, list) and teams and all(isinstance(t, list) for t in teams):
                return teams
        except (ValueError, TypeError):
            pass
    return [json.loads(row["team_a"]), json.loads(row["team_b"])]


def mein_team_buchstabe(teams: list[list[int]], spieler_id: int) -> str:
    for i, t in enumerate(teams):
        if spieler_id in t:
            return elo.BUCHSTABEN[i]
    return "?"


def spiel_eintragen(
    conn: sqlite3.Connection,
    team_a_ids: list[int],
    team_b_ids: list[int],
    ergebnis: str,
    datum: str | None = None,
    token: str | None = None,
) -> tuple[dict[int, int], bool]:
    """Zwei Teams eintragen - duenne Huelle um `spiel_eintragen_n`."""
    return spiel_eintragen_n(conn, [team_a_ids, team_b_ids], ergebnis,
                             datum=datum, token=token)


def spiel_eintragen_n(
    conn: sqlite3.Connection,
    teams_ids: list[list[int]],
    ergebnis: str,
    datum: str | None = None,
    token: str | None = None,
) -> tuple[dict[int, int], bool]:
    """Traegt ein Spiel mit zwei bis vier Teams ein, aktualisiert ELO und
    Spielzaehler.

    ``token`` ist ein einmaliger Idempotenz-Schluessel des Clients: wird
    derselbe Token erneut geschickt (z. B. weil eine wackelige Mobilverbindung
    den Request doppelt zustellt), wird das Spiel NICHT ein zweites Mal gezaehlt.

    Liefert ``(deltas, war_neu)`` — ``war_neu=False`` heisst „schon vorhanden,
    nichts geaendert".
    """
    datum = datum or date.today().isoformat()

    # Bereits mit diesem Token eingetragen? Dann unveraendert zurueckgeben.
    if token:
        vorhanden = conn.execute(
            "SELECT id FROM spiele WHERE token = ?", (token,)
        ).fetchone()
        if vorhanden:
            return _deltas_aus_verlauf(conn, vorhanden["id"]), False

    teams = [spieler_nach_ids(conn, ids) for ids in teams_ids]
    deltas = elo.berechne_spiel_mehrere(teams, ergebnis)

    try:
        cur = conn.execute(
            "INSERT INTO spiele (datum, team_a, team_b, teams, ergebnis, token) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (datum, json.dumps(teams_ids[0]), json.dumps(teams_ids[1]),
             json.dumps(teams_ids), ergebnis, token),
        )
    except sqlite3.IntegrityError:
        # Zwei fast gleichzeitige Requests mit gleichem Token: der andere war
        # schneller. Nichts doppelt eintragen, vorhandenes Ergebnis liefern.
        conn.rollback()
        vorhanden = conn.execute(
            "SELECT id FROM spiele WHERE token = ?", (token,)
        ).fetchone()
        return _deltas_aus_verlauf(conn, vorhanden["id"]), False

    spiel_id = int(cur.lastrowid)

    for p in [p for t in teams for p in t]:
        delta = deltas[p["id"]]
        vorher = p["elo"]
        nachher = vorher + delta
        conn.execute(
            "UPDATE spieler SET elo = ?, spiele_gesamt = spiele_gesamt + 1 WHERE id = ?",
            (nachher, p["id"]),
        )
        conn.execute(
            "INSERT INTO elo_verlauf (spiel_id, spieler_id, elo_vorher, delta, elo_nachher) "
            "VALUES (?, ?, ?, ?, ?)",
            (spiel_id, p["id"], vorher, delta, nachher),
        )
    conn.commit()
    return deltas, True


def _namen_map(conn: sqlite3.Connection, ids) -> dict[int, dict]:
    """Name/Position je Spieler-ID (auch inaktive/geloeschte werden abgedeckt)."""
    ids = list(ids)
    if not ids:
        return {}
    platzhalter = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT id, name, position FROM spieler WHERE id IN ({platzhalter})", ids
    ).fetchall()
    return {r["id"]: {"name": r["name"], "position": r["position"]} for r in rows}


def spieler_detail(conn: sqlite3.Connection, spieler_id: int, limit: int = 40) -> dict | None:
    """Eine Spielerin mit ihren letzten Spielen (neueste zuerst): je Spiel das
    angewendete Delta, das Ergebnis und beide Team-Aufstellungen (mit Namen)."""
    sp = conn.execute(
        "SELECT id, name, elo, position, position_angriff, position_abwehr, "
        "spiele_gesamt FROM spieler WHERE id = ?",
        (spieler_id,),
    ).fetchone()
    if sp is None:
        return None

    rows = conn.execute(
        "SELECT s.id AS spiel_id, s.datum, s.ergebnis, s.team_a, s.team_b, s.teams, v.delta "
        "FROM elo_verlauf v JOIN spiele s ON s.id = v.spiel_id "
        "WHERE v.spieler_id = ? ORDER BY s.id DESC LIMIT ?",
        (spieler_id, limit),
    ).fetchall()

    spiele = []
    alle_ids: set[int] = set()
    for r in rows:
        teams = teams_ids_von(r)
        for t in teams:
            alle_ids.update(t)
        spiele.append({
            "spiel_id": r["spiel_id"],
            "datum": r["datum"],
            "ergebnis": r["ergebnis"],
            "delta": r["delta"],
            "mein_team": mein_team_buchstabe(teams, spieler_id),
            "_teams": teams,
        })

    namen = _namen_map(conn, alle_ids)

    def bestueckt(ids):
        return [{
            "id": i,
            "name": namen.get(i, {}).get("name", f"#{i}"),
            "position": namen.get(i, {}).get("position", "Feld"),
        } for i in ids]

    for s in spiele:
        teams = s.pop("_teams")
        s["teams"] = [bestueckt(t) for t in teams]
        # Fuer den Zwei-Team-Fall zusaetzlich die alten Schluessel liefern.
        s["team_a"] = s["teams"][0]
        s["team_b"] = s["teams"][1] if len(s["teams"]) > 1 else []

    # Trainings-Anwesenheit (aus training_teilnahme, Quelle SpielerPlus/Anytype).
    # Nur echte TRAININGS zaehlen - Test- und Ligaspiele stehen in derselben
    # Tabelle, gehoeren aber nicht in die Trainingsquote.
    tt = conn.execute(
        "SELECT tt.status, COUNT(*) AS n FROM training_teilnahme tt "
        "JOIN trainings t ON t.id = tt.training_id "
        "WHERE tt.spieler_id = ? AND t.art = 'training' GROUP BY tt.status",
        (spieler_id,)
    ).fetchall()
    z = {r["status"]: r["n"] for r in tt}
    anw, abg, uns = z.get("anwesend", 0), z.get("abgesagt", 0), z.get("unsicher", 0)
    training = {
        "anwesend": anw, "abgesagt": abg, "unsicher": uns,
        "erfasst": anw + abg + uns,
        "quote": round(100 * anw / (anw + abg)) if (anw + abg) else None,
    }

    # Laufchallenge-Ergebnis (falls importiert): jüngste Challenge der Spielerin.
    lc = conn.execute(
        "SELECT challenge, km, laeufe, andere, rang, teilnehmer "
        "FROM laufchallenge WHERE spieler_id = ? ORDER BY rowid DESC LIMIT 1",
        (spieler_id,)
    ).fetchone()
    laufchallenge = dict(lc) if lc else None

    return {"spieler": dict(sp), "spiele": spiele, "training": training,
            "laufchallenge": laufchallenge, "stats": _spieler_stats(conn, sp)}


def _spieler_stats(conn: sqlite3.Connection, sp) -> dict:
    """Kennzahlen ueber ALLE Spiele einer Spielerin: Bilanz, aktuelle Serie,
    bestes Einzel-Delta, ELO-Hoechststand."""
    spieler_id = sp["id"]
    rows = conn.execute(
        "SELECT s.ergebnis, s.team_a, s.team_b, s.teams, v.delta, v.elo_vorher, v.elo_nachher "
        "FROM elo_verlauf v JOIN spiele s ON s.id = v.spiel_id "
        "WHERE v.spieler_id = ? ORDER BY s.id DESC",
        (spieler_id,),
    ).fetchall()

    def typ(r) -> str:
        if r["ergebnis"] == "U":
            return "U"
        mein = mein_team_buchstabe(teams_ids_von(r), spieler_id)
        return "S" if r["ergebnis"] == mein else "N"

    typen = [typ(r) for r in rows]
    siege = typen.count("S")
    unent = typen.count("U")
    niederlagen = typen.count("N")

    serie_typ = serie_anzahl = None
    if typen:
        serie_typ = typen[0]
        serie_anzahl = 0
        for t in typen:
            if t == serie_typ:
                serie_anzahl += 1
            else:
                break

    werte = [sp["elo"]]
    for r in rows:
        werte += [r["elo_vorher"], r["elo_nachher"]]
    peak = max(werte) if werte else sp["elo"]
    bester = max((r["delta"] for r in rows), default=None)

    return {
        "siege": siege, "unent": unent, "niederlagen": niederlagen,
        "serie_typ": serie_typ, "serie_anzahl": serie_anzahl,
        "bester": bester, "peak": peak,
    }


def _seeds(conn: sqlite3.Connection) -> dict[int, int]:
    """Startwert (Seed) je Spielerin = ELO vor ihrem ersten Spiel (aus
    elo_verlauf); wer noch kein Spiel hat, bekommt die aktuelle ELO.

    Muss aufgerufen werden, SOLANGE die Historie noch vollstaendig ist – sonst
    geht beim Loeschen des ersten Spiels der echte Startwert verloren."""
    seeds: dict[int, int] = {
        r["id"]: r["elo"] for r in conn.execute("SELECT id, elo FROM spieler")
    }
    for r in conn.execute(
        "SELECT v.spieler_id AS sid, v.elo_vorher AS seed FROM elo_verlauf v "
        "JOIN (SELECT spieler_id, MIN(spiel_id) AS msid FROM elo_verlauf "
        "      GROUP BY spieler_id) m "
        "ON v.spieler_id = m.spieler_id AND v.spiel_id = m.msid"
    ):
        seeds[r["sid"]] = r["seed"]
    return seeds


def neu_berechnen(conn: sqlite3.Connection, seeds: dict[int, int] | None = None) -> None:
    """Rechnet ELO + Spielzaehler aller Spielerinnen komplett neu aus der
    Spiele-Historie. ``seeds`` sollte VOR einer Loeschung eingefangen werden
    (siehe _seeds); ohne Angabe werden sie aus dem aktuellen Verlauf gelesen."""
    if seeds is None:
        seeds = _seeds(conn)

    conn.execute("DELETE FROM elo_verlauf")
    for pid, seed in seeds.items():
        conn.execute(
            "UPDATE spieler SET elo = ?, spiele_gesamt = 0 WHERE id = ?", (seed, pid)
        )

    for s in conn.execute(
        "SELECT id, team_a, team_b, teams, ergebnis FROM spiele ORDER BY id"
    ).fetchall():
        teams = [spieler_nach_ids(conn, ids) for ids in teams_ids_von(s)]
        if len(teams) < 2 or any(not t for t in teams):
            continue                       # Spielerin geloescht -> Spiel ueberspringen
        deltas = elo.berechne_spiel_mehrere(teams, s["ergebnis"])
        for p in [p for t in teams for p in t]:
            delta = deltas[p["id"]]
            vorher = p["elo"]
            nachher = vorher + delta
            conn.execute(
                "UPDATE spieler SET elo = ?, spiele_gesamt = spiele_gesamt + 1 WHERE id = ?",
                (nachher, p["id"]),
            )
            conn.execute(
                "INSERT INTO elo_verlauf (spiel_id, spieler_id, elo_vorher, delta, elo_nachher) "
                "VALUES (?, ?, ?, ?, ?)",
                (s["id"], p["id"], vorher, delta, nachher),
            )
    conn.commit()


def spiel_teamzahl(conn: sqlite3.Connection, spiel_id: int) -> int:
    """Wie viele Teams hatte dieses Spiel? (Fuer die Korrektur-Knoepfe.)"""
    row = conn.execute(
        "SELECT team_a, team_b, teams FROM spiele WHERE id = ?", (spiel_id,)
    ).fetchone()
    return len(teams_ids_von(row)) if row else 0


def spiel_aendern(conn: sqlite3.Connection, spiel_id: int, ergebnis: str) -> bool:
    """Aendert das Ergebnis eines Spiels und rechnet die ELOs neu."""
    row = conn.execute(
        "SELECT team_a, team_b, teams FROM spiele WHERE id = ?", (spiel_id,)
    ).fetchone()
    if row is None:
        return False
    anzahl = len(teams_ids_von(row))
    if ergebnis != "U" and ergebnis not in elo.BUCHSTABEN[:anzahl]:
        raise ValueError(f"Dieses Spiel hatte {anzahl} Teams – {ergebnis!r} passt nicht.")
    seeds = _seeds(conn)                       # vor der Aenderung einfangen
    conn.execute("UPDATE spiele SET ergebnis = ? WHERE id = ?", (ergebnis, spiel_id))
    neu_berechnen(conn, seeds)
    return True


def spiel_loeschen(conn: sqlite3.Connection, spiel_id: int) -> bool:
    """Loescht ein Spiel (samt Verlauf per Cascade) und rechnet die ELOs neu."""
    if conn.execute("SELECT 1 FROM spiele WHERE id = ?", (spiel_id,)).fetchone() is None:
        return False
    seeds = _seeds(conn)                        # vor dem Loeschen einfangen!
    conn.execute("DELETE FROM spiele WHERE id = ?", (spiel_id,))
    neu_berechnen(conn, seeds)
    return True


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


def letztes_spiel_ruecknehmen(conn: sqlite3.Connection) -> bool:
    """Macht das zuletzt eingetragene Spiel rueckgaengig (ELO + Zaehler)."""
    row = conn.execute("SELECT id FROM spiele ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return False
    spiel_id = row["id"]
    for v in conn.execute(
        "SELECT spieler_id, elo_vorher FROM elo_verlauf WHERE spiel_id = ?", (spiel_id,)
    ).fetchall():
        conn.execute(
            "UPDATE spieler SET elo = ?, spiele_gesamt = spiele_gesamt - 1 WHERE id = ?",
            (v["elo_vorher"], v["spieler_id"]),
        )
    conn.execute("DELETE FROM spiele WHERE id = ?", (spiel_id,))
    conn.commit()
    return True


# ================================================================ Phase 3 ====
#  Native Lese-Funktionen fuer Trainings und das Seiten-Wiki (loesen die
#  /api/anytype/* Endpunkte ab). Reine Reads -> offline spiegelbar.

def trainings_liste(conn: sqlite3.Connection, spieler_id: int | None = None) -> list[dict]:
    """Alle Trainings, neueste zuerst, je mit Teilnahme-Zaehlung + hat_plan.
    Mit `spieler_id` zusaetzlich `meine_status` (eigene Antwort) je Training."""
    rows = conn.execute(
        "SELECT t.id, t.datum, t.titel, t.uhrzeit, t.ort, "
        "       t.art, t.gegner, t.heim, t.abfahrt, "
        "       ((t.plan_markdown IS NOT NULL AND t.plan_markdown <> '') "
        "        OR EXISTS (SELECT 1 FROM training_block b WHERE b.training_id = t.id)) AS hat_plan, "
        "       (SELECT COALESCE(SUM(b.dauer_min), 0) FROM training_block b "
        "        WHERE b.training_id = t.id) AS plan_minuten, "
        "       COALESCE(SUM(tt.status = 'anwesend'), 0) AS anwesend, "
        "       COALESCE(SUM(tt.status = 'abgesagt'), 0) AS abgesagt, "
        "       COALESCE(SUM(tt.status = 'unsicher'), 0) AS unsicher, "
        "       (SELECT COUNT(*) FROM spieler WHERE aktiv = 1) AS kader, "
        "       (SELECT status FROM training_teilnahme x "
        "        WHERE x.training_id = t.id AND x.spieler_id = ?) AS meine_status "
        "FROM trainings t "
        "LEFT JOIN training_teilnahme tt ON tt.training_id = t.id "
        "GROUP BY t.id "
        "ORDER BY t.datum DESC, t.id DESC",
        (spieler_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def training_detail(conn: sqlite3.Connection, tid: int) -> dict | None:
    """Ein Training mit voller Teilnahmeliste (Name/Position/Status) + Plan.

    Die Liste geht vom KADER aus, nicht von den vorhandenen Antworten: wer noch
    gar nicht geantwortet hat, steht mit `status = None` drin. Nur so kann die
    App zeigen, auf wen man noch wartet - vorher fehlten diese Namen komplett,
    weil ohne Antwort auch keine Zeile in `training_teilnahme` existiert.

    Ausserdem dabei: bereits ausgetretene (inaktive) Spielerinnen, die fuer
    dieses Training schon geantwortet hatten - ihre Antwort verschwindet nicht
    rueckwirkend aus einem alten Termin.
    """
    t = conn.execute("SELECT * FROM trainings WHERE id = ?", (tid,)).fetchone()
    if t is None:
        return None
    teil = conn.execute(
        "SELECT s.id, s.name, s.position, s.position_angriff, "
        "       tt.status, tt.quelle, tt.grund "
        "FROM spieler s "
        "LEFT JOIN training_teilnahme tt "
        "       ON tt.spieler_id = s.id AND tt.training_id = ? "
        "WHERE s.aktiv = 1 OR tt.spieler_id IS NOT NULL "
        "ORDER BY CASE tt.status WHEN 'anwesend' THEN 0 WHEN 'unsicher' THEN 1 "
        "         WHEN 'abgesagt' THEN 2 ELSE 3 END, s.name",
        (tid,),
    ).fetchall()
    d = dict(t)
    d["teilnahme"] = [dict(r) for r in teil]
    d["bloecke"] = plan_bloecke(conn, tid)
    return d


def plan_bloecke(conn: sqlite3.Connection, tid: int) -> list[dict]:
    """Die Bloecke eines Trainings in ihrer Reihenfolge."""
    rows = conn.execute(
        "SELECT id, reihenfolge, dauer_min, titel, notiz FROM training_block "
        "WHERE training_id = ? ORDER BY reihenfolge, id", (tid,)
    ).fetchall()
    return [dict(r) for r in rows]


def plan_bloecke_setzen(conn: sqlite3.Connection, tid: int,
                        bloecke: list[dict]) -> int:
    """Den kompletten Plan eines Trainings ersetzen (loeschen + neu schreiben).
    Idempotent: dieselbe Liste zweimal gesendet ergibt denselben Zustand -
    wichtig, weil die Outbox einen Sendeversuch wiederholen darf."""
    conn.execute("DELETE FROM training_block WHERE training_id = ?", (tid,))
    for i, b in enumerate(bloecke):
        dauer = b.get("dauer_min")
        try:
            dauer = int(dauer) if dauer not in (None, "") else None
        except (TypeError, ValueError):
            dauer = None
        if dauer is not None and not (0 < dauer <= 300):
            dauer = None                      # unsinnige Werte lieber verwerfen
        conn.execute(
            "INSERT INTO training_block (training_id, reihenfolge, dauer_min, titel, notiz) "
            "VALUES (?,?,?,?,?)",
            (tid, i, dauer, (b.get("titel") or "").strip()[:120],
             (b.get("notiz") or "").strip()[:500] or None),
        )
    conn.commit()
    return len(bloecke)


def training_loeschen(conn: sqlite3.Connection, tid: int) -> bool:
    """Training samt Teilnahme, Plan-Bloecken und Uebungs-Zuordnung entfernen.
    Idempotent: ein bereits geloeschtes Training liefert False, ist aber
    kein Fehler - so darf ein wiederholter Aufruf gefahrlos durchlaufen."""
    conn.execute("DELETE FROM training_teilnahme WHERE training_id = ?", (tid,))
    conn.execute("DELETE FROM training_block WHERE training_id = ?", (tid,))
    conn.execute("DELETE FROM training_uebung WHERE training_id = ?", (tid,))
    cur = conn.execute("DELETE FROM trainings WHERE id = ?", (tid,))
    conn.commit()
    return cur.rowcount > 0


def teilnahme_setzen(conn: sqlite3.Connection, training_id: int, spieler_id: int,
                     status: str, grund: str | None = None,
                     quelle: str = "app") -> None:
    """Zu-/Absage einer Spielerin setzen (Upsert). App-Antworten haben Vorrang."""
    conn.execute(
        "INSERT INTO training_teilnahme (training_id, spieler_id, status, grund, quelle) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(training_id, spieler_id) DO UPDATE SET "
        "  status = excluded.status, grund = excluded.grund, quelle = excluded.quelle",
        (training_id, spieler_id, status, grund, quelle),
    )
    conn.commit()


# Quellen, die nur SPIEGEL eines Fremdsystems sind. Alles andere ('app',
# 'trainer') ist eine bewusste Eingabe in dieser App und bleibt unangetastet.
SPIEGEL_QUELLEN = ("spielerplus", "anytype")


def teilnahme_spiegeln(conn: sqlite3.Connection, training_id: int, spieler_id: int,
                       status: str) -> bool:
    """Antwort aus einem Fremdsystem (SpielerPlus) uebernehmen - OHNE eine
    Eingabe aus der App zu ueberschreiben. Liefert False, wenn die Spielerin
    schon selbst (app) oder durch den Trainer geantwortet hat. Kein Commit:
    der Aufrufer committet einmal pro Lauf."""
    cur = conn.execute(
        "INSERT INTO training_teilnahme (training_id, spieler_id, status, grund, quelle) "
        "VALUES (?,?,?,NULL,'spielerplus') "
        "ON CONFLICT(training_id, spieler_id) DO UPDATE SET "
        "  status = excluded.status, grund = NULL, quelle = 'spielerplus' "
        "WHERE training_teilnahme.quelle IN ('spielerplus', 'anytype')",
        (training_id, spieler_id, status),
    )
    return cur.rowcount > 0


def teilnahme_spiegel_entfernen(conn: sqlite3.Connection, training_id: int,
                                spieler_id: int) -> bool:
    """Gespiegelte Antwort entfernen (in SpielerPlus wieder 'offen'). Eingaben
    aus der App bleiben. Kein Commit."""
    cur = conn.execute(
        "DELETE FROM training_teilnahme WHERE training_id = ? AND spieler_id = ? "
        "AND quelle IN ('spielerplus', 'anytype')",
        (training_id, spieler_id),
    )
    return cur.rowcount > 0


def teilnahme_loeschen(conn: sqlite3.Connection, training_id: int,
                       spieler_id: int) -> None:
    """Antwort zuruecksetzen auf 'noch offen' (Trainer-Korrektur). Ohne Zeile
    zaehlt die Spielerin wieder zu denen, auf die man wartet."""
    conn.execute(
        "DELETE FROM training_teilnahme WHERE training_id = ? AND spieler_id = ?",
        (training_id, spieler_id),
    )
    conn.commit()


def naechstes_training(conn: sqlite3.Connection) -> dict | None:
    """Das naechste Training ab heute (fuer den Home-Screen), sonst None."""
    row = conn.execute(
        "SELECT id FROM trainings WHERE datum >= ? AND art = 'training' "
        "ORDER BY datum ASC, id ASC LIMIT 1",
        (date.today().isoformat(),),
    ).fetchone()
    return training_detail(conn, row["id"]) if row else None


def seiten_liste(conn: sqlite3.Connection, kategorie: str | None = None) -> list[dict]:
    """Wiki-Seiten (Titel/Kategorie/Hierarchie), ohne die vollen Bodies.
    `parent_id`/`sortierung` gehen mit raus, damit das Frontend den Baum bauen
    kann (Playbook: Gruppe 'Spielzuege' mit Unterseiten)."""
    basis = ("SELECT id, titel, kategorie, parent_id, sortierung, anytype_typ, tags, "
             "(markdown IS NOT NULL AND markdown <> '') AS hat_inhalt FROM seiten ")
    if kategorie:
        rows = conn.execute(basis + "WHERE kategorie = ? ORDER BY sortierung, titel",
                            (kategorie,)).fetchall()
    else:
        rows = conn.execute(basis + "ORDER BY kategorie, sortierung, titel").fetchall()
    return [dict(r) for r in rows]


def seite_detail(conn: sqlite3.Connection, sid: int) -> dict | None:
    r = conn.execute("SELECT * FROM seiten WHERE id = ?", (sid,)).fetchone()
    return dict(r) if r else None


def seite_anlegen(conn: sqlite3.Connection, titel: str, kategorie: str,
                  parent_id: int | None = None, markdown: str | None = None,
                  sortierung: int | None = None) -> int:
    """Neue Wiki-Seite. Ohne `sortierung` hinten auf ihrer Ebene anhaengen."""
    if sortierung is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(sortierung), -1) + 1 AS n FROM seiten "
            "WHERE kategorie IS ? AND parent_id IS ?", (kategorie, parent_id)
        ).fetchone()
        sortierung = int(row["n"])
    cur = conn.execute(
        "INSERT INTO seiten (titel, kategorie, parent_id, markdown, sortierung) "
        "VALUES (?,?,?,?,?)", (titel, kategorie, parent_id, markdown, sortierung))
    conn.commit()
    return int(cur.lastrowid)


def seite_speichern(conn: sqlite3.Connection, sid: int, markdown: str | None = None,
                    titel: str | None = None) -> bool:
    """Inhalt und/oder Titel aendern. Reine Zuweisung -> mehrfaches Senden aus
    der Outbox ist unschaedlich."""
    sets, params = [], []
    if markdown is not None:
        sets.append("markdown = ?"); params.append(markdown)
    if titel is not None:
        sets.append("titel = ?"); params.append(titel)
    if not sets:
        return False
    sets.append("aktualisiert = datetime('now')")
    params.append(sid)
    cur = conn.execute(f"UPDATE seiten SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    return cur.rowcount > 0


def seite_loeschen(conn: sqlite3.Connection, sid: int) -> bool:
    """Seite loeschen. Unterseiten bleiben erhalten und ruecken eine Ebene hoch
    (parent_id -> NULL per ON DELETE SET NULL)."""
    cur = conn.execute("DELETE FROM seiten WHERE id = ?", (sid,))
    conn.commit()
    return cur.rowcount > 0


def training_plan_setzen(conn: sqlite3.Connection, tid: int, markdown: str) -> bool:
    """Coach-Plan nativ am Training speichern (ersetzt die Anytype-Body-Anlage)."""
    cur = conn.execute(
        "UPDATE trainings SET plan_markdown = ? WHERE id = ?", (markdown, tid)
    )
    conn.commit()
    return cur.rowcount > 0


def training_anlegen(conn: sqlite3.Connection, datum: str, titel: str = "",
                     plan_markdown: str | None = None, uhrzeit: str | None = None,
                     ort: str | None = None, art: str = "training",
                     gegner: str | None = None, heim: int | None = None,
                     abfahrt: str | None = None) -> tuple[int, bool]:
    """Termin anlegen. Liefert (id, war_neu).

    Ein TRAINING am selben Datum wird wiederverwendet statt doppelt angelegt
    (der Anytype-/SpielerPlus-Import lauft sonst in Dubletten). SPIELE dagegen
    werden immer neu angelegt und auch nie als Ziel wiederverwendet: an einem
    Tag koennen ein Training und ein Testspiel nebeneinander stehen, und ein
    Spiel darf ein Training nicht ueberschreiben.
    """
    art = art if art in ARTEN else "training"
    vorhanden = None
    if art == "training":
        vorhanden = conn.execute(
            "SELECT id FROM trainings WHERE datum = ? AND art = 'training' "
            "ORDER BY id LIMIT 1", (datum,)
        ).fetchone()
    if vorhanden:
        tid = int(vorhanden["id"])
        felder, werte = [], []
        for spalte, wert in (("titel", titel), ("uhrzeit", uhrzeit), ("ort", ort)):
            if wert:
                felder.append(f"{spalte} = ?"); werte.append(wert)
        if felder:
            werte.append(tid)
            conn.execute(f"UPDATE trainings SET {', '.join(felder)} WHERE id = ?", werte)
        if plan_markdown and plan_markdown.strip():
            training_plan_setzen(conn, tid, plan_markdown)
        conn.commit()
        return tid, False
    cur = conn.execute(
        "INSERT INTO trainings (datum, titel, uhrzeit, ort, plan_markdown, "
        "art, gegner, heim, abfahrt) VALUES (?,?,?,?,?,?,?,?,?)",
        (datum, titel or "", uhrzeit, ort, plan_markdown,
         art, gegner, heim, abfahrt),
    )
    conn.commit()
    return int(cur.lastrowid), True


def kader_info(conn: sqlite3.Connection) -> dict:
    """Fuer den Coach: Anzahl Spielerinnen + Torhueterinnen fuers naechste
    Training. Primaer die Zusagen (anwesend) des naechsten Trainings, sonst der
    Gesamtkader. Ersetzt anytype_sync.kader_info (kein Anytype mehr noetig)."""
    nt = naechstes_training(conn)
    if nt:
        anwesend = [t for t in nt.get("teilnahme", []) if t["status"] == "anwesend"]
        if anwesend:
            return {
                "anzahl": len(anwesend),
                "torhueter": sum(1 for t in anwesend if t["position"] == "Tor"),
                "quelle": f"Zusagen Training {nt['datum']}",
            }
    spieler = aktive_spieler(conn)
    return {
        "anzahl": len(spieler),
        "torhueter": sum(1 for s in spieler if s["position"] == "Tor"),
        "quelle": "Gesamtkader",
    }


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
    # Neue PIN setzen entsperrt zugleich (Fehlversuche zuruecksetzen).
    conn.execute("UPDATE benutzer SET pin_hash = ?, fehlversuche = 0 WHERE id = ?",
                 (pin_hash, bid))
    conn.commit()


def benutzer_fehlversuch(conn: sqlite3.Connection, bid: int) -> int:
    """Fehlversuch zaehlen, neuen Stand liefern."""
    conn.execute("UPDATE benutzer SET fehlversuche = fehlversuche + 1 WHERE id = ?", (bid,))
    conn.commit()
    r = conn.execute("SELECT fehlversuche FROM benutzer WHERE id = ?", (bid,)).fetchone()
    return int(r["fehlversuche"]) if r else 0


def benutzer_login_ok(conn: sqlite3.Connection, bid: int) -> None:
    conn.execute("UPDATE benutzer SET fehlversuche = 0 WHERE id = ?", (bid,))
    conn.commit()


def benutzer_pin_sperren(conn: sqlite3.Connection, bid: int) -> None:
    """PIN ungueltig machen (nach zu vielen Fehlversuchen). Trainer muss neu setzen."""
    conn.execute("UPDATE benutzer SET pin_hash = NULL, fehlversuche = 0 WHERE id = ?", (bid,))
    conn.commit()


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


def offene_spieler_benutzer(conn: sqlite3.Connection, training_id: int) -> list[int]:
    """Benutzer-IDs aktiver Spielerinnen, fuer die noch gar keine Antwort
    vorliegt - die Empfaengerinnen der Push-Erinnerung.

    Als Antwort zaehlt die eigene in der App (quelle 'app') UND das, was der
    Trainer fuer sie eingetragen hat (quelle 'trainer'). Wer schon abgesagt
    hat, soll keine Erinnerung mehr bekommen - egal, wer es eingetippt hat.
    Blosse Nominierungen aus SpielerPlus sind KEINE Antwort.
    """
    rows = conn.execute(
        "SELECT b.id FROM benutzer b "
        "WHERE b.rolle = 'spieler' AND b.aktiv = 1 AND b.spieler_id IS NOT NULL "
        "AND b.spieler_id NOT IN ("
        "  SELECT spieler_id FROM training_teilnahme "
        "  WHERE training_id = ? AND quelle IN ('app', 'trainer'))",
        (training_id,)).fetchall()
    return [r["id"] for r in rows]


def benutzer_liste(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT b.id, b.name, b.rolle, b.spieler_id, b.aktiv, "
        "       (b.pin_hash IS NOT NULL) AS pin_gesetzt "
        "FROM benutzer b ORDER BY b.rolle DESC, b.name"
    ).fetchall()
    return [dict(r) for r in rows]


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
    rows = conn.execute(
        "SELECT id, titel, notiz, datei, spiel_datum, dauer_s, erstellt_am "
        "FROM video_clip ORDER BY COALESCE(spiel_datum, '') DESC, id DESC"
    ).fetchall()
    return _clips_mit_spielern(conn, rows)


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


# ------------------------------------------------------------ Spielanalysen ----
#  Ganzes Spielvideo + Ereignisse/Spielzuege aus "Balu-Spielanalyse".

def analyse_speichern(conn: sqlite3.Connection, extern_id: str, gegner: str,
                      datum: str | None, art: str | None, events: list[dict],
                      zuege: list[dict], erstellt_von: int | None) -> int:
    """Legt die Analyse an oder ersetzt Ereignisse/Spielzuege einer vorhandenen
    (gleiche extern_id). Das Video bleibt dabei erhalten. Spielerinnen-IDs, die
    es hier nicht gibt, werden zu NULL bzw. fallen aus der Zuordnung."""
    gueltig = {r["id"] for r in conn.execute("SELECT id FROM spieler")}
    sp = lambda x: x if x in gueltig else None          # noqa: E731
    r = conn.execute("SELECT id FROM spiel_analyse WHERE extern_id = ?", (extern_id,)).fetchone()
    if r:
        aid = int(r["id"])
        conn.execute("UPDATE spiel_analyse SET gegner = ?, datum = ?, art = ? WHERE id = ?",
                     (gegner, datum, art, aid))
        conn.execute("DELETE FROM spiel_event WHERE analyse_id = ?", (aid,))
        conn.execute("DELETE FROM spiel_zug WHERE analyse_id = ?", (aid,))   # Kaskade -> Zuordnung
    else:
        cur = conn.execute(
            "INSERT INTO spiel_analyse (extern_id, gegner, datum, art, erstellt_von) VALUES (?,?,?,?,?)",
            (extern_id, gegner, datum, art, erstellt_von))
        aid = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO spiel_event (analyse_id, typ, t, spieler_id, assist_id, detail, szene_key) "
        "VALUES (?,?,?,?,?,?,?)",
        [(aid, e["typ"], e["t"], sp(e.get("spieler_id")), sp(e.get("assist_id")), e.get("detail"),
          e.get("key")) for e in events])
    for z in zuege:
        cur = conn.execute(
            "INSERT INTO spiel_zug (analyse_id, name, t_start, t_ende, ampel, kommentar, szene_key) "
            "VALUES (?,?,?,?,?,?,?)",
            (aid, z["name"], z["t_start"], z["t_ende"], z["ampel"], z.get("kommentar") or None,
             z.get("key")))
        conn.executemany(
            "INSERT OR IGNORE INTO spiel_zug_spieler (zug_id, spieler_id) VALUES (?, ?)",
            [(int(cur.lastrowid), s) for s in z.get("spieler_ids", []) if s in gueltig])
    conn.commit()
    return aid


def analyse_datei_setzen(conn: sqlite3.Connection, aid: int, datei: str) -> str | None:
    """Setzt den Videodateinamen und gibt den alten zurueck (zum Aufraeumen)."""
    r = conn.execute("SELECT datei FROM spiel_analyse WHERE id = ?", (aid,)).fetchone()
    alt = r["datei"] if r else None
    conn.execute("UPDATE spiel_analyse SET datei = ? WHERE id = ?", (datei, aid))
    conn.commit()
    return alt


def analyse_nach_id(conn: sqlite3.Connection, aid: int) -> dict | None:
    r = conn.execute("SELECT * FROM spiel_analyse WHERE id = ?", (aid,)).fetchone()
    return dict(r) if r else None


def analysen_liste(conn: sqlite3.Connection, spieler_id: int | None = None,
                   alle: bool = False) -> list[dict]:
    """Alle Analysen (Trainer) oder nur die, in denen die Spielerin vorkommt.
    Mit `alle=True` (und spieler_id) kommen ALLE Analysen, dazu je Spiel die
    Zahl der Ereignisse (`meine_events`) und Spielzuege (`meine_zuege`), an denen
    die Spielerin beteiligt ist - 0/0 heisst: sie kommt nicht vor."""
    sql = ("SELECT a.id, a.gegner, a.datum, a.art, a.datei IS NOT NULL AS video_da, "
           "(SELECT COUNT(*) FROM spiel_event e WHERE e.analyse_id = a.id) AS events, "
           "(SELECT COUNT(*) FROM spiel_zug z WHERE z.analyse_id = a.id) AS zuege")
    params: tuple = ()
    if spieler_id is not None and alle:
        sql += (", (SELECT COUNT(*) FROM spiel_event e WHERE e.analyse_id = a.id "
                "AND (e.spieler_id = ?1 OR e.assist_id = ?1)) AS meine_events, "
                "(SELECT COUNT(*) FROM spiel_zug z JOIN spiel_zug_spieler s ON s.zug_id = z.id "
                "WHERE z.analyse_id = a.id AND s.spieler_id = ?1) AS meine_zuege")
        params = (spieler_id,)
    sql += " FROM spiel_analyse a"
    if spieler_id is not None and not alle:
        sql += (" WHERE EXISTS (SELECT 1 FROM spiel_event e WHERE e.analyse_id = a.id "
                "AND (e.spieler_id = ?1 OR e.assist_id = ?1)) "
                "OR EXISTS (SELECT 1 FROM spiel_zug z JOIN spiel_zug_spieler s ON s.zug_id = z.id "
                "WHERE z.analyse_id = a.id AND s.spieler_id = ?1)")
        params = (spieler_id,)
    sql += " ORDER BY COALESCE(a.datum, '') DESC, a.id DESC"
    return [dict(r) | {"video_da": bool(r["video_da"])} for r in conn.execute(sql, params)]


def analyse_inhalt(conn: sqlite3.Connection, aid: int,
                   spieler_id: int | None = None) -> dict:
    """Ereignisse + Spielzuege einer Analyse; mit spieler_id nur die, an denen
    die Spielerin beteiligt ist (Torschuetzin/Vorlage bzw. im Spielzug)."""
    ev_sql = ("SELECT e.id, e.typ, e.t, e.spieler_id, e.assist_id, e.detail, c.id AS clip_id "
              "FROM spiel_event e LEFT JOIN spiel_szene_clip c "
              "ON c.analyse_id = e.analyse_id AND c.szene_key = e.szene_key "
              "WHERE e.analyse_id = ?")
    ev_par: list = [aid]
    if spieler_id is not None:
        ev_sql += " AND (e.spieler_id = ? OR e.assist_id = ?)"
        ev_par += [spieler_id, spieler_id]
    events = [dict(r) for r in conn.execute(ev_sql + " ORDER BY e.t", ev_par)]

    zuege = [dict(r) for r in conn.execute(
        "SELECT z.id, z.name, z.t_start, z.t_ende, z.ampel, z.kommentar, c.id AS clip_id "
        "FROM spiel_zug z LEFT JOIN spiel_szene_clip c "
        "ON c.analyse_id = z.analyse_id AND c.szene_key = z.szene_key "
        "WHERE z.analyse_id = ? ORDER BY z.t_start", (aid,))]
    zuord: dict[int, list[int]] = {}
    for r in conn.execute(
            "SELECT s.zug_id, s.spieler_id FROM spiel_zug_spieler s "
            "JOIN spiel_zug z ON z.id = s.zug_id WHERE z.analyse_id = ?", (aid,)):
        zuord.setdefault(r["zug_id"], []).append(r["spieler_id"])
    for z in zuege:
        z["spieler_ids"] = zuord.get(z["id"], [])
    if spieler_id is not None:
        zuege = [z for z in zuege if spieler_id in z["spieler_ids"]]
    return {"events": events, "zuege": zuege}


def analyse_loeschen(conn: sqlite3.Connection, aid: int) -> tuple[str, list[str]] | None:
    """Loescht die Analyse (Kaskade). Gibt Videodatei und Clip-Dateien zurueck, damit der
    Aufrufer sie von der Platte entfernen kann; None, wenn es die Analyse nicht gibt."""
    r = conn.execute("SELECT datei FROM spiel_analyse WHERE id = ?", (aid,)).fetchone()
    if not r:
        return None
    clips = [x["datei"] for x in conn.execute(
        "SELECT datei FROM spiel_szene_clip WHERE analyse_id = ?", (aid,))]
    conn.execute("DELETE FROM spiel_analyse WHERE id = ?", (aid,))     # Kaskade
    conn.commit()
    return (r["datei"] or ""), clips


# ---- Szenen-Clips ---------------------------------------------------------------

def szene_clips_liste(conn: sqlite3.Connection, aid: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, szene_key AS key, von, bis FROM spiel_szene_clip "
        "WHERE analyse_id = ? ORDER BY szene_key", (aid,))]


def szene_clip_speichern(conn: sqlite3.Connection, aid: int, key: str, datei: str,
                         von: float, bis: float) -> str | None:
    """Legt den Clip an oder ersetzt ihn. Gibt den Namen der ALTEN Datei zurueck (oder None)."""
    alt = conn.execute("SELECT datei FROM spiel_szene_clip WHERE analyse_id = ? AND szene_key = ?",
                       (aid, key)).fetchone()
    conn.execute(
        "INSERT INTO spiel_szene_clip (analyse_id, szene_key, datei, von, bis) VALUES (?,?,?,?,?) "
        "ON CONFLICT (analyse_id, szene_key) DO UPDATE SET datei = excluded.datei, "
        "von = excluded.von, bis = excluded.bis, erstellt_am = datetime('now')",
        (aid, key, datei, von, bis))
    conn.commit()
    return alt["datei"] if alt else None


def szene_clip_nach_id(conn: sqlite3.Connection, cid: int) -> dict | None:
    r = conn.execute("SELECT * FROM spiel_szene_clip WHERE id = ?", (cid,)).fetchone()
    return dict(r) if r else None


def szene_clip_darf(conn: sqlite3.Connection, cid: int, spieler_id: int) -> bool:
    """Eine Spielerin darf den Clip sehen, wenn sie an mindestens einer Szene mit dieser
    Kennung beteiligt ist (Spielzug-Mitspielerin bzw. Schuetzin/Vorlage/Betroffene)."""
    r = conn.execute(
        "SELECT 1 FROM spiel_szene_clip c WHERE c.id = ?1 AND ("
        " EXISTS (SELECT 1 FROM spiel_event e WHERE e.analyse_id = c.analyse_id "
        "         AND e.szene_key = c.szene_key AND (e.spieler_id = ?2 OR e.assist_id = ?2))"
        " OR EXISTS (SELECT 1 FROM spiel_zug z JOIN spiel_zug_spieler s ON s.zug_id = z.id "
        "            WHERE z.analyse_id = c.analyse_id AND z.szene_key = c.szene_key "
        "            AND s.spieler_id = ?2))", (cid, spieler_id)).fetchone()
    return r is not None


def szene_clips_aufraeumen(conn: sqlite3.Connection, aid: int, keys: set[str]) -> list[str]:
    """Entfernt Clips, deren Szene es nicht mehr gibt. Gibt deren Dateinamen zurueck."""
    weg = [r for r in conn.execute(
        "SELECT id, szene_key, datei FROM spiel_szene_clip WHERE analyse_id = ?", (aid,))
        if r["szene_key"] not in keys]
    for r in weg:
        conn.execute("DELETE FROM spiel_szene_clip WHERE id = ?", (r["id"],))
    conn.commit()
    return [r["datei"] for r in weg]


# ---------------------------------------------------------------- Nutzung ----
#  Siehe Tabelle 'nutzung'. Gespeichert wird fuer jedes Konto; ausgewertet
#  werden nur die Spielerinnen-Konten (Trainer testen die App staendig selbst).

NUTZUNG_TYPEN = ("besuch", "bereich", "video")
NUTZUNG_BESUCH_PAUSE_MIN = 30      # mehrere Besuche innerhalb dieser Zeit zaehlen einmal
NUTZUNG_MAX_PRO_ANFRAGE = 50


def nutzung_speichern(conn: sqlite3.Connection, benutzer_id: int,
                      ereignisse: list[dict]) -> int:
    """Speichert Ereignisse ({typ, ziel, info}); Unbekanntes wird verworfen.
    Ein 'besuch' innerhalb der Pause nach dem letzten Besuch zaehlt nicht
    (die App meldet beim Zurueckkehren oft kurz hintereinander). Gibt die
    Anzahl gespeicherter Ereignisse zurueck."""
    gespeichert = 0
    besuch_schon_da = bool(conn.execute(
        "SELECT 1 FROM nutzung WHERE benutzer_id = ? AND typ = 'besuch' "
        "AND zeit > datetime('now', ?)",
        (benutzer_id, f"-{NUTZUNG_BESUCH_PAUSE_MIN} minutes")).fetchone())
    for e in ereignisse[:NUTZUNG_MAX_PRO_ANFRAGE]:
        typ = e.get("typ")
        if typ not in NUTZUNG_TYPEN:
            continue
        if typ == "besuch":
            if besuch_schon_da:
                continue
            besuch_schon_da = True
        ziel = (str(e["ziel"])[:60] if e.get("ziel") else None)
        info = (str(e["info"])[:120] if e.get("info") else None)
        conn.execute("INSERT INTO nutzung (benutzer_id, typ, ziel, info) VALUES (?, ?, ?, ?)",
                     (benutzer_id, typ, ziel, info))
        gespeichert += 1
    conn.commit()
    return gespeichert


def geraet_speichern(conn: sqlite3.Connection, benutzer_id: int, g: dict) -> None:
    """Merkt sich ein Geraet des Kontos (oder frischt 'zuletzt'/App-Version auf)."""
    def t(k: str, n: int) -> str:
        return str(g.get(k) or "").strip()[:n]
    conn.execute(
        "INSERT INTO geraet (benutzer_id, os, browser, modus, bildschirm, modell, app_version, sw) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(benutzer_id, os, browser, modus, bildschirm, modell) "
        "DO UPDATE SET zuletzt = datetime('now'), app_version = excluded.app_version, "
        "              sw = excluded.sw",
        (benutzer_id, t("os", 30), t("browser", 30), t("modus", 20), t("bildschirm", 20),
         t("modell", 40), t("app_version", 20), 1 if g.get("sw") else 0))
    conn.commit()


FEHLER_MAX_PRO_STUNDE = 20     # Schutz davor, dass eine Fehlerschleife die DB flutet


def fehler_speichern(conn: sqlite3.Connection, benutzer_id: int, f: dict) -> bool:
    """Speichert einen Fehlerbericht; False, wenn leer oder das Stundenlimit erreicht ist."""
    meldung = str(f.get("meldung") or "").strip()[:300]
    if not meldung:
        return False
    n = conn.execute("SELECT COUNT(*) FROM fehler WHERE benutzer_id = ? "
                     "AND zeit > datetime('now', '-1 hour')", (benutzer_id,)).fetchone()[0]
    if n >= FEHLER_MAX_PRO_STUNDE:
        return False

    def t(k: str, n: int) -> str | None:
        return (str(f[k]).strip()[:n] or None) if f.get(k) else None
    conn.execute(
        "INSERT INTO fehler (benutzer_id, quelle, meldung, ort, app_version, geraet) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (benutzer_id, t("quelle", 20), meldung, t("ort", 60), t("app_version", 20),
         t("geraet", 120)))
    conn.commit()
    return True


def _berlin():
    """Zeitzone fuer die Tageszaehlung; ohne Zeitzonen-Datenbank (z. B. Windows
    ohne tzdata) UTC - nur die Tagesgrenze verschiebt sich dann um 1-2 Stunden."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Berlin")
    except Exception:
        return timezone.utc


def nutzung_auswertung(conn: sqlite3.Connection, tage: int = 30) -> dict:
    """Je Spielerinnen-Konto: zuletzt aktiv, Besuche/aktive Tage/Videos der
    letzten `tage` Tage, haeufigste Bereiche und angesehene Videos."""
    jetzt = datetime.now(timezone.utc)
    grenze = jetzt - timedelta(days=tage)
    tz = _berlin()

    def lies(z: str) -> datetime:
        return datetime.strptime(z, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

    konten = conn.execute(
        "SELECT id, name FROM benutzer WHERE rolle = 'spieler' AND aktiv = 1 ORDER BY name"
    ).fetchall()
    rows: dict[int, list] = {k["id"]: [] for k in konten}
    for r in conn.execute("SELECT benutzer_id, zeit, typ, ziel, info FROM nutzung ORDER BY zeit"):
        if r["benutzer_id"] in rows:
            rows[r["benutzer_id"]].append(r)
    erste = conn.execute("SELECT MIN(zeit) AS z FROM nutzung").fetchone()["z"]
    geraete: dict[int, list] = {k["id"]: [] for k in konten}
    for g in conn.execute("SELECT * FROM geraet ORDER BY zuletzt DESC"):
        if g["benutzer_id"] in geraete:
            geraete[g["benutzer_id"]].append({
                "os": g["os"], "browser": g["browser"], "modus": g["modus"],
                "bildschirm": g["bildschirm"], "modell": g["modell"],
                "app_version": g["app_version"], "sw": bool(g["sw"]),
                "zuletzt": _utc_z(g["zuletzt"])})

    ausgabe = []
    for k in konten:
        ev = rows[k["id"]]
        neu = [r for r in ev if lies(r["zeit"]) >= grenze]
        bereiche: dict[str, int] = {}
        videos: dict[str, dict] = {}
        for r in neu:
            if r["typ"] == "bereich" and r["ziel"]:
                bereiche[r["ziel"]] = bereiche.get(r["ziel"], 0) + 1
            elif r["typ"] == "video" and r["ziel"]:
                v = videos.setdefault(r["ziel"], {"ziel": r["ziel"], "titel": r["info"],
                                                  "anzahl": 0, "zuletzt": r["zeit"]})
                v["anzahl"] += 1
                v["zuletzt"] = r["zeit"]
                if r["info"]:
                    v["titel"] = r["info"]
        ausgabe.append({
            "benutzer_id": k["id"], "name": k["name"],
            "zuletzt": (ev[-1]["zeit"].replace(" ", "T") + "Z") if ev else None,
            "besuche": sum(1 for r in neu if r["typ"] == "besuch"),
            "tage": len({lies(r["zeit"]).astimezone(tz).date() for r in neu}),
            "videos_gesehen": sum(1 for r in neu if r["typ"] == "video"),
            "bereiche": [{"ziel": z, "anzahl": n} for z, n in
                         sorted(bereiche.items(), key=lambda x: -x[1])[:6]],
            "videos": sorted(
                [{**v, "zuletzt": v["zuletzt"].replace(" ", "T") + "Z"} for v in videos.values()],
                key=lambda v: v["zuletzt"], reverse=True)[:10],
            "geraete": geraete[k["id"]],
        })
    return {"tage": tage, "seit": (erste.replace(" ", "T") + "Z") if erste else None,
            "konten": ausgabe, "fehler": _fehler_gruppiert(conn, grenze)}


def _utc_z(z: str | None) -> str | None:
    return (z.replace(" ", "T") + "Z") if z else None


def _fehler_gruppiert(conn: sqlite3.Connection, grenze: datetime) -> list[dict]:
    """Gleiche Fehlermeldungen zusammengefasst: Anzahl, wer, welche Geraete,
    welche App-Versionen - die neuesten zuerst."""
    rows = conn.execute(
        "SELECT f.zeit, f.quelle, f.meldung, f.ort, f.app_version, f.geraet, b.name "
        "FROM fehler f JOIN benutzer b ON b.id = f.benutzer_id "
        "WHERE f.zeit >= ? ORDER BY f.zeit",
        (grenze.strftime("%Y-%m-%d %H:%M:%S"),)).fetchall()
    gruppen: dict[str, dict] = {}
    for r in rows:
        g = gruppen.setdefault(r["meldung"], {
            "meldung": r["meldung"], "quelle": r["quelle"], "anzahl": 0, "zuletzt": None,
            "namen": [], "geraete": [], "versionen": [], "orte": []})
        g["anzahl"] += 1
        g["zuletzt"] = r["zeit"]
        for feld, wert in (("namen", r["name"]), ("geraete", r["geraet"]),
                           ("versionen", r["app_version"]), ("orte", r["ort"])):
            if wert and wert not in g[feld]:
                g[feld].append(wert)
    aus = sorted(gruppen.values(), key=lambda g: g["zuletzt"], reverse=True)[:30]
    for g in aus:
        g["zuletzt"] = _utc_z(g["zuletzt"])
        g["geraete"] = g["geraete"][:4]
    return aus
