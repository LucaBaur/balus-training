"""Das Datenbankschema (CREATE TABLE ...) als eine Konstante."""

from __future__ import annotations


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
-- NUR fuer das Trainerteam sichtbar - erzwungen in routen/termine.py, nicht im Frontend.
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

-- Mitteilungs-Einstellungen: je Benutzer und Art ein- oder ausgeschaltet. Es steht nur
-- eine Zeile, wenn jemand etwas geaendert hat; ohne Zeile gilt "an".
CREATE TABLE IF NOT EXISTS push_praeferenz (
    benutzer_id  INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
    art          TEXT    NOT NULL,
    an           INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (benutzer_id, art)
);

-- Schon verschickte Einmal-Nachrichten (z. B. "Abfahrt morgen" fuer Spiel 7). Der
-- Schluessel verhindert, dass ein zweiter Cron-Lauf dieselbe Nachricht noch einmal sendet.
CREATE TABLE IF NOT EXISTS push_gesendet (
    schluessel   TEXT PRIMARY KEY,
    zeit         TEXT NOT NULL DEFAULT (datetime('now'))
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
    typ         TEXT    NOT NULL,                        -- besuch | bereich | video | gespielt | verweil
    ziel        TEXT,
    info        TEXT,
    dauer_s     INTEGER                                  -- nur bei 'verweil': Sekunden auf 'ziel'
);
CREATE INDEX IF NOT EXISTS idx_nutzung_benutzer ON nutzung(benutzer_id, zeit);

-- Fragen und Kommentare zu einem Video. 'ziel' wie in 'nutzung' ("clip:5", "szene:12",
-- "spiel:3"). Sichtbarkeit: nur_trainer = 0 -> alle, die das Video sehen duerfen;
-- nur_trainer = 1 -> Trainer + 'privat_fuer' (die Spielerin, der der private Faden gehoert;
-- Antworten des Trainers erben beides vom Ursprungs-Kommentar). Antworten haengen immer am
-- Ursprungs-Kommentar ('antwort_auf'), es gibt nur eine Ebene.
CREATE TABLE IF NOT EXISTS video_kommentar (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ziel        TEXT    NOT NULL,
    benutzer_id INTEGER NOT NULL REFERENCES benutzer(id) ON DELETE CASCADE,
    text        TEXT    NOT NULL,
    antwort_auf INTEGER REFERENCES video_kommentar(id) ON DELETE CASCADE,
    nur_trainer INTEGER NOT NULL DEFAULT 0,
    privat_fuer INTEGER REFERENCES benutzer(id) ON DELETE CASCADE,
    erstellt_am TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_vkomm_ziel ON video_kommentar(ziel, id);

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

-- Wochen-To-Dos: Der Trainer legt je Spielerin 2-4 Ziele an ('todo'), die Spielerin waehlt
-- fuer die laufende Woche eins davon ('todo_woche', Woche = ISO-Datum des Montags).
-- Feedback und Entscheidung ('bleibt' | 'erledigt') haengen an der Wochenzeile, damit der
-- Verlauf bleibt. Erst 'erledigt' setzt das To-Do selbst auf status = 'erledigt'.
CREATE TABLE IF NOT EXISTS todo (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    spieler_id  INTEGER NOT NULL REFERENCES spieler(id) ON DELETE CASCADE,
    text        TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'offen',        -- offen | erledigt
    erstellt_am TEXT    NOT NULL DEFAULT (datetime('now')),
    erledigt_am TEXT
);
CREATE INDEX IF NOT EXISTS idx_todo_spieler ON todo(spieler_id, status);

CREATE TABLE IF NOT EXISTS todo_woche (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    todo_id     INTEGER NOT NULL REFERENCES todo(id) ON DELETE CASCADE,
    woche       TEXT    NOT NULL,                        -- Montag der Woche, YYYY-MM-DD
    gewaehlt_am TEXT    NOT NULL DEFAULT (datetime('now')),
    feedback    TEXT,
    ergebnis    TEXT,                                    -- bleibt | erledigt (NULL = noch offen)
    feedback_am TEXT,
    UNIQUE (todo_id, woche)
);
CREATE INDEX IF NOT EXISTS idx_todowoche_woche ON todo_woche(woche);

-- Spiel-Nachbereitung (NUR Trainer): Gedanken, Gegner-Notizen und Montags-Ansprache zu einem Spiel.
-- Bewusst eigene Tabelle und nicht Spalten an 'trainings': die Terminliste geht an alle
-- Spielerinnen. 'vorspiel_id' ist der manuelle Weg zum Hinspiel, falls der Gegnername abweicht.
CREATE TABLE IF NOT EXISTS spiel_nachbereitung (
    training_id  INTEGER PRIMARY KEY REFERENCES trainings(id) ON DELETE CASCADE,
    gedanken     TEXT    NOT NULL DEFAULT '',
    gegner       TEXT    NOT NULL DEFAULT '',
    ansprache    TEXT    NOT NULL DEFAULT '',
    vorspiel_id  INTEGER REFERENCES trainings(id) ON DELETE SET NULL,
    geaendert_am TEXT    NOT NULL DEFAULT (datetime('now')),
    autor        TEXT
);

-- Mannschaftskasse (Amt Kassenwart). Ein Kassenbuch: Buchungen werden nie geloescht, nur storniert,
-- damit die Kasse nachvollziehbar bleibt. Betraege sind GANZE CENT (nie Gleitkomma), immer positiv;
-- die Richtung steckt in der Art:
--   forderung  Spielerin schuldet der Kasse etwas (Strafe, Beitrag)   - bewegt kein Bargeld
--   einzahlung Spielerin zahlt in die Kasse                           - Kasse +, Schuld -
--   ausgabe    Die Kasse zahlt etwas (Getraenke, Rundenabschluss)     - Kasse -
--   einnahme   Sonstiges Geld in der Kasse (Spende, Flohmarkt)        - Kasse +
-- 'token' macht doppeltes Absenden harmlos (gleiches Token = dieselbe Buchung). Der Fremdschluessel ohne
-- CASCADE verhindert, dass eine Spielerin mit Buchungen versehentlich geloescht wird.
CREATE TABLE IF NOT EXISTS kasse_buchung (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    art          TEXT    NOT NULL CHECK (art IN ('forderung','einzahlung','ausgabe','einnahme')),
    betrag_cent  INTEGER NOT NULL CHECK (betrag_cent > 0),
    text         TEXT    NOT NULL,
    datum        TEXT    NOT NULL,                       -- YYYY-MM-DD, Tag der Buchung (nicht der Eingabe)
    spieler_id   INTEGER REFERENCES spieler(id),         -- nur bei forderung / einzahlung
    erstellt_am  TEXT    NOT NULL DEFAULT (datetime('now')),
    erstellt_von TEXT    NOT NULL,
    token        TEXT    UNIQUE,
    storniert_am TEXT,
    storniert_von TEXT
);
CREATE INDEX IF NOT EXISTS idx_kasse_spieler ON kasse_buchung(spieler_id);
"""
