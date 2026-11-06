"""Ämter der Mannschaft: wer hat welches Amt, was darf sie dort, und die Listen dazu.

Ein Amt ist KEINE Rolle. `benutzer.rolle` bleibt 'trainer' oder 'spieler'; ein Amt hängt an
der Spielerin (Tabelle `amt_inhaber`) und gibt ihr höchstens ein paar gezielte Rechte.

Drei Arten (Spalte `typ`):
  titel      Nur Name und Beschreibung. Der Normalfall (Kapitän, Duschgel, Tape ...).
  zuteilung  Pro Termin wählt die Inhaberin eine Spielerin (Trikots, Leibchen, Getränke);
             dazu ein Zähler "wie oft schon", für alle sichtbar.
  fahrten    Das Vereinsbussle: pro Auswärtsspiel "da / nicht da" und wer selbst fährt.

Dieses Modul kennt nur SQLite (kein `db`-Import), damit `db.init_db` es beim Start laden und
die Standard-Ämter anlegen kann, ohne einen Importkreis zu bilden. Die Rechteprüfung am
Server steht in app.py und ruft `rechte_von` / `ist_inhaber` hier auf.

Wer welches Amt hat, steht NUR in der Datenbank (über die App eingetragen), nie im Code:
das Repository ist öffentlich.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

# Rechte, die ein Amt vergeben kann. Die Zuordnung Amt -> Recht steht bewusst hier im Code und
# nicht in der Datenbank: Wer Rechte ändern will, ändert Code (und wird dabei getestet), die
# Oberfläche kann sie nicht verschieben. Der Trainer hat jedes Recht ohnehin.
RECHTE = {"termine": "Trainings und Spiele anlegen und löschen",
          "kasse": "Mannschaftskasse führen (Strafen, Zahlungen, Ausgaben buchen und stornieren)"}
AMT_RECHTE: dict[str, tuple[str, ...]] = {"balu_app": ("termine",), "kassenwart": ("kasse",)}

# Auf welche Termine sich eine Liste bezieht.
GILT_FUER = ("training", "spiele", "alle")

# Standard-Ämter: (Schlüssel, Name, Beschreibung, Typ, gilt_für). Die Reihenfolge ist die der
# Anzeige. Beim Start wird nur ergänzt, was fehlt: Texte, die der Trainer ändert, bleiben.
AEMTER_START = [
    ("kapitaen", "Kapitän", "Sprecherin der Mannschaft und Ansprechperson für Trainer und Schiedsrichter.", "titel", "alle"),
    ("mannschaftsrat", "Mannschaftsrat", "Kümmert sich um organisatorische Fragen, wenn etwas ansteht.", "titel", "alle"),
    ("spielplanung", "Spielplanung", "Plant vor der Saison die Hallenzeiten und spricht Termine ab.", "titel", "alle"),
    ("kassenwart", "Kassenwart", "Führt die Mannschaftskasse: bucht Strafen, Einzahlungen, Ausgaben und Einnahmen und zeigt den Kassenstand.", "titel", "alle"),
    ("balu_app", "Balu-Trainings-App", "Legt Trainings und Spiele in der App an (früher SpielerPlus).", "titel", "alle"),
    ("leibchen", "Leibchen", "Bestimmt, wer die Leibchen nach dem Training mit nach Hause nimmt und wäscht.", "zuteilung", "training"),
    ("waschliste", "Waschliste", "Bestimmt, wer nach dem Spiel die Trikots mit nach Hause nimmt und wäscht.", "zuteilung", "spiele"),
    ("getraenke", "Getränke", "Macht die Liste, wer Getränke mitbringt.", "zuteilung", "alle"),
    ("bussle", "Bussle", "Prüft bei Auswärtsspielen, ob das Vereinsbussle da ist, und notiert, wer selbst mit dem Auto fährt.", "fahrten", "spiele"),
    ("schichtplan", "Schichtplan", "Der Verein teilt der Mannschaft offene Schichten zu. Das Amt fragt per Umfrage in der Gruppe ab, wer wann Zeit hat.", "titel", "alle"),
    ("putzen", "Putzen", "Organisiert das Putzen der Halle und kontrolliert, ob ordentlich geputzt wurde.", "titel", "alle"),
    ("essensplan", "Essensplan", "Noch offen.", "titel", "alle"),
    ("duschgel", "Duschgel", "Bringt das Duschgel mit zum Training.", "titel", "alle"),
    ("tape", "Tape", "Bringt das Tape mit zum Training und zu den Spielen.", "titel", "alle"),
    ("harz_oel", "Harz/Öl", "Bringt Harz und Öl mit zum Training und zu den Spielen.", "titel", "alle"),
    ("eiskoffer", "Eiskoffer", "Bringt zu den Spielen den Eiskoffer mit.", "titel", "alle"),
    ("musik", "Musik", "Kümmert sich um die Musik in der Kabine während eines Spiels.", "titel", "alle"),
    ("spielberichte", "Spielberichte", "Team, das die Spielberichte schreibt, gemeinsam oder reihum, wie sie es untereinander ausmachen.", "titel", "alle"),
    ("social_media", "Social Media", "Dreht Reels und schreibt Beiträge für die Mannschaft.", "titel", "alle"),
    ("rundenabschluss", "Rundenabschluss", "Plant während der Saison den Rundenabschluss.", "titel", "alle"),
]

BUSSLE_STATUS = ("da", "nicht_da")

# Was eine Inhaberin zu jedem passenden Termin mitbringt (Amt-Schlüssel -> (Wort, gilt für)).
# Daraus entsteht die Erinnerung "heute nicht vergessen" eine Stunde vorher. Es gibt dafür keine
# Liste: wer das Amt hat, bringt es immer mit.
MITBRINGEN = {
    "duschgel": ("Duschgel", "training"),
    "tape": ("Tape", "alle"),
    "harz_oel": ("Harz und Öl", "alle"),
    "eiskoffer": ("Eiskoffer", "spiele"),
    "musik": ("Musik für die Kabine", "spiele"),
}
# Aus Zuteilungslisten kommt die Erinnerung nur an die, die an diesem Termin eingeteilt sind.
LISTEN_ERINNERUNG = {
    "getraenke": "Getränke",
    "leibchen": "Leibchen nach dem Training mitnehmen",
    "waschliste": "Trikots nach dem Spiel mitnehmen",
}
FAHRT_ERINNERUNG = "mit dem eigenen Auto fahren"

# Zeitfenster der Terminliste einer Zuteilungsliste (Tage ab heute).
TAGE_ZURUECK = 14
TAGE_VORAUS = 45

SCHEMA = """
CREATE TABLE IF NOT EXISTS amt (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    schluessel   TEXT    UNIQUE,                 -- stabiler Name im Code (Rechte); NULL bei selbst angelegten
    name         TEXT    NOT NULL,
    beschreibung TEXT    NOT NULL DEFAULT '',
    typ          TEXT    NOT NULL DEFAULT 'titel',   -- 'titel' | 'zuteilung' | 'fahrten'
    gilt_fuer    TEXT    NOT NULL DEFAULT 'alle',    -- 'training' | 'spiele' | 'alle'
    sort         INTEGER NOT NULL DEFAULT 0
);

-- Wer hat das Amt. Mehrere Inhaberinnen je Amt und mehrere Ämter je Spielerin sind normal.
CREATE TABLE IF NOT EXISTS amt_inhaber (
    amt_id      INTEGER NOT NULL REFERENCES amt(id)      ON DELETE CASCADE,
    spieler_id  INTEGER NOT NULL REFERENCES spieler(id)  ON DELETE CASCADE,
    PRIMARY KEY (amt_id, spieler_id)
);
CREATE INDEX IF NOT EXISTS ix_amt_inhaber_spieler ON amt_inhaber(spieler_id);

-- Zuteilung je Termin: wer nimmt die Trikots mit, wer bringt die Getränke, wer fährt selbst.
-- 'erledigt' ist der Haken der Inhaberin (gewaschen, mitgebracht). Beim Löschen eines Termins
-- oder einer Spielerin verschwindet die Zeile mit.
CREATE TABLE IF NOT EXISTS amt_zuteilung (
    amt_id       INTEGER NOT NULL REFERENCES amt(id)        ON DELETE CASCADE,
    training_id  INTEGER NOT NULL REFERENCES trainings(id)  ON DELETE CASCADE,
    spieler_id   INTEGER NOT NULL REFERENCES spieler(id)    ON DELETE CASCADE,
    erledigt     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (amt_id, training_id, spieler_id)
);
CREATE INDEX IF NOT EXISTS ix_amt_zuteilung_termin ON amt_zuteilung(training_id);

-- Vereinsbussle je Auswärtsspiel. Keine Zeile = noch nicht geklärt.
CREATE TABLE IF NOT EXISTS bussle_status (
    training_id  INTEGER PRIMARY KEY REFERENCES trainings(id) ON DELETE CASCADE,
    status       TEXT    NOT NULL                  -- 'da' | 'nicht_da'
);
"""


def starte(conn: sqlite3.Connection) -> None:
    """Tabellen anlegen und fehlende Standard-Ämter ergänzen (idempotent)."""
    conn.executescript(SCHEMA)
    for i, (schluessel, name, text, typ, gilt) in enumerate(AEMTER_START, start=1):
        conn.execute(
            "INSERT OR IGNORE INTO amt (schluessel, name, beschreibung, typ, gilt_fuer, sort) "
            "VALUES (?,?,?,?,?,?)", (schluessel, name, text, typ, gilt, i))


# ---------------------------------------------------------------- Rechte ----

def rechte_von(conn: sqlite3.Connection, spieler_id: int | None) -> set[str]:
    """Alle Rechte, die diese Spielerin über ihre Ämter hat (ohne Trainer-Rolle)."""
    if not spieler_id:
        return set()
    rechte: set[str] = set()
    for r in conn.execute(
            "SELECT a.schluessel FROM amt_inhaber i JOIN amt a ON a.id = i.amt_id "
            "WHERE i.spieler_id = ?", (spieler_id,)):
        rechte.update(AMT_RECHTE.get(r["schluessel"], ()))
    return rechte


def ist_inhaber(conn: sqlite3.Connection, amt_id: int, spieler_id: int | None) -> bool:
    if not spieler_id:
        return False
    return conn.execute("SELECT 1 FROM amt_inhaber WHERE amt_id = ? AND spieler_id = ?",
                        (amt_id, spieler_id)).fetchone() is not None


def meine_aemter(conn: sqlite3.Connection, spieler_id: int | None) -> list[dict]:
    """Die Ämter einer Spielerin (für das Profil-Menü und /api/me)."""
    if not spieler_id:
        return []
    return [dict(r) for r in conn.execute(
        "SELECT a.id, a.name, a.typ FROM amt_inhaber i JOIN amt a ON a.id = i.amt_id "
        "WHERE i.spieler_id = ? ORDER BY a.sort, a.id", (spieler_id,))]


# --------------------------------------------------------------- Ämter ----

def amt_holen(conn: sqlite3.Connection, amt_id: int) -> dict:
    r = conn.execute("SELECT * FROM amt WHERE id = ?", (amt_id,)).fetchone()
    if r is None:
        raise LookupError("Amt nicht gefunden")
    return dict(r)


def alle(conn: sqlite3.Connection, spieler_id: int | None, ist_trainer: bool) -> list[dict]:
    """Alle Ämter mit Inhaberinnen. `meine` = hat die anfragende Spielerin das Amt,
    `darf_pflegen` = darf sie die Liste dazu bearbeiten (Inhaberin oder Trainer)."""
    inhaber: dict[int, list[dict]] = {}
    for r in conn.execute(
            "SELECT i.amt_id, s.id AS spieler_id, s.name FROM amt_inhaber i "
            "JOIN spieler s ON s.id = i.spieler_id ORDER BY s.name"):
        inhaber.setdefault(r["amt_id"], []).append({"spieler_id": r["spieler_id"], "name": r["name"]})
    liste = []
    for r in conn.execute("SELECT * FROM amt ORDER BY sort, id"):
        a = dict(r)
        a["inhaber"] = inhaber.get(a["id"], [])
        a["meine"] = any(x["spieler_id"] == spieler_id for x in a["inhaber"])
        a["darf_pflegen"] = bool(ist_trainer or a["meine"])
        a["hat_liste"] = a["typ"] in ("zuteilung", "fahrten")
        a["rechte"] = [RECHTE[r] for r in AMT_RECHTE.get(a["schluessel"], ())]     # Klartext, für die Anzeige
        liste.append(a)
    return liste


def amt_anlegen(conn: sqlite3.Connection, name: str, beschreibung: str) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("Der Name fehlt.")
    if conn.execute("SELECT 1 FROM amt WHERE lower(name) = lower(?)", (name,)).fetchone():
        raise ValueError("Ein Amt mit diesem Namen gibt es schon.")
    sort = conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM amt").fetchone()[0]
    cur = conn.execute("INSERT INTO amt (name, beschreibung, sort) VALUES (?,?,?)",
                       (name, (beschreibung or "").strip(), sort))
    conn.commit()
    return int(cur.lastrowid)


def beschreibung_setzen(conn: sqlite3.Connection, amt_id: int, beschreibung: str) -> None:
    amt_holen(conn, amt_id)
    conn.execute("UPDATE amt SET beschreibung = ? WHERE id = ?", ((beschreibung or "").strip(), amt_id))
    conn.commit()


def inhaber_setzen(conn: sqlite3.Connection, amt_id: int, spieler_id: int, da: bool) -> None:
    """Setzt (nicht: schaltet um), ob die Spielerin das Amt hat. Wiederholen ändert nichts,
    darum ist ein doppelt gesendeter Aufruf unschädlich."""
    amt_holen(conn, amt_id)
    if conn.execute("SELECT 1 FROM spieler WHERE id = ?", (spieler_id,)).fetchone() is None:
        raise LookupError("Spielerin nicht gefunden")
    if da:
        conn.execute("INSERT OR IGNORE INTO amt_inhaber (amt_id, spieler_id) VALUES (?,?)",
                     (amt_id, spieler_id))
    else:
        conn.execute("DELETE FROM amt_inhaber WHERE amt_id = ? AND spieler_id = ?",
                     (amt_id, spieler_id))
    conn.commit()


# -------------------------------------------------------------- Listen ----

def saison_beginn(heute: date) -> str:
    """Handball-Saison beginnt am 1. Juli."""
    jahr = heute.year if heute.month >= 7 else heute.year - 1
    return f"{jahr}-07-01"


def _passt(amt: dict, art: str, heim) -> bool:
    if amt["typ"] == "fahrten":                      # nur Auswärtsspiele
        return art != "training" and heim == 0
    if amt["gilt_fuer"] == "training":
        return art == "training"
    if amt["gilt_fuer"] == "spiele":
        return art != "training"
    return True


def liste(conn: sqlite3.Connection, amt_id: int, heute: date | None = None) -> dict:
    """Termine im Zeitfenster mit Zuteilung (und beim Bussle dem Status) sowie der Zähler je
    Spielerin für die laufende Saison. Der Zähler ist absteigend nach Nachholbedarf sortiert:
    wer am seltensten dran war, steht oben."""
    amt = amt_holen(conn, amt_id)
    if amt["typ"] not in ("zuteilung", "fahrten"):
        raise ValueError("Zu diesem Amt gibt es keine Liste.")
    heute = heute or date.today()
    von = (heute - timedelta(days=TAGE_ZURUECK)).isoformat()
    bis = (heute + timedelta(days=TAGE_VORAUS)).isoformat()

    namen = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM spieler")}
    zuteilungen: dict[int, list[dict]] = {}
    for r in conn.execute(
            "SELECT z.training_id, z.spieler_id, z.erledigt FROM amt_zuteilung z "
            "JOIN trainings t ON t.id = z.training_id "
            "WHERE z.amt_id = ? AND t.datum BETWEEN ? AND ?", (amt_id, von, bis)):
        zuteilungen.setdefault(r["training_id"], []).append(
            {"spieler_id": r["spieler_id"], "name": namen.get(r["spieler_id"], "?"),
             "erledigt": bool(r["erledigt"])})
    status = {r["training_id"]: r["status"] for r in conn.execute("SELECT training_id, status FROM bussle_status")}

    termine = []
    for t in conn.execute(
            "SELECT id, datum, titel, uhrzeit, art, gegner, heim, abfahrt FROM trainings "
            "WHERE datum BETWEEN ? AND ? ORDER BY datum, id", (von, bis)):
        if not _passt(amt, t["art"], t["heim"]):
            continue
        eintrag = {"training_id": t["id"], "datum": t["datum"], "titel": t["titel"],
                   "uhrzeit": t["uhrzeit"], "art": t["art"], "gegner": t["gegner"],
                   "heim": t["heim"], "abfahrt": t["abfahrt"],
                   "zugeteilt": sorted(zuteilungen.get(t["id"], []), key=lambda x: x["name"])}
        if amt["typ"] == "fahrten":
            eintrag["status"] = status.get(t["id"])
        termine.append(eintrag)

    saison = saison_beginn(heute)
    zaehler = {r["id"]: {"spieler_id": r["id"], "name": r["name"], "anzahl": 0, "offen": 0}
               for r in conn.execute("SELECT id, name FROM spieler WHERE aktiv = 1")}
    for r in conn.execute(
            "SELECT z.spieler_id, COUNT(*) AS n, "
            "       COALESCE(SUM(z.erledigt = 0 AND t.datum <= ?), 0) AS offen "
            "FROM amt_zuteilung z JOIN trainings t ON t.id = z.training_id "
            "WHERE z.amt_id = ? AND t.datum >= ? GROUP BY z.spieler_id",
            (heute.isoformat(), amt_id, saison)):
        z = zaehler.get(r["spieler_id"])
        if z is not None:                           # inaktive Spielerinnen zählen nicht mit
            z["anzahl"], z["offen"] = r["n"], r["offen"]
    return {"amt": amt, "saison_ab": saison, "termine": termine,
            "zaehler": sorted(zaehler.values(), key=lambda z: (z["anzahl"], z["name"]))}


def aufgaben(conn: sqlite3.Connection, spieler_id: int | None, heute: date | None = None) -> list[dict]:
    """Wo ist diese Spielerin gerade dran? Kommende Termine und, bis sie abgehakt sind, die
    der letzten sieben Tage (Trikots, die noch zu waschen sind). Für die Karte auf Home."""
    if not spieler_id:
        return []
    heute = heute or date.today()
    return [dict(r) for r in conn.execute(
        "SELECT a.id AS amt_id, a.name AS amt, a.typ, t.id AS training_id, t.datum, t.titel, "
        "       t.art, t.gegner, z.erledigt "
        "FROM amt_zuteilung z JOIN amt a ON a.id = z.amt_id JOIN trainings t ON t.id = z.training_id "
        "WHERE z.spieler_id = ? AND t.datum >= ? AND (t.datum >= ? OR (z.erledigt = 0 AND a.typ = 'zuteilung')) "
        "ORDER BY t.datum, a.sort",
        (spieler_id, (heute - timedelta(days=7)).isoformat(), heute.isoformat()))]


def _art_passt(gilt: str, art: str) -> bool:
    return gilt == "alle" or (gilt == "training") == (art == "training")


def treffzeit(t) -> tuple[str, str] | None:
    """(Wort, Uhrzeit), auf die sich die Erinnerung bezieht: bei Auswärtsspielen die Abfahrt, sonst
    Beginn bzw. Anwurf. None, wenn der Termin keine Uhrzeit hat (dann gibt es keine Erinnerung)."""
    if t["art"] != "training" and t["heim"] == 0 and t["abfahrt"]:
        return "Abfahrt", t["abfahrt"]
    if t["uhrzeit"]:
        return ("Training" if t["art"] == "training" else "Anwurf"), t["uhrzeit"]
    return None


def erinnerungen(conn: sqlite3.Connection, training_id: int) -> dict[int, list[str]]:
    """Was soll wer zu diesem Termin nicht vergessen? {spieler_id: [Wort, ...]}. Mitbring-Ämter
    gelten für alle Inhaberinnen, Listen-Ämter nur für die, die für den Termin eingeteilt sind."""
    t = conn.execute("SELECT art FROM trainings WHERE id = ?", (training_id,)).fetchone()
    if t is None:
        return {}
    aus: dict[int, list[str]] = {}
    for r in conn.execute(
            "SELECT a.schluessel, i.spieler_id FROM amt_inhaber i JOIN amt a ON a.id = i.amt_id "
            "ORDER BY a.sort, a.id"):
        m = MITBRINGEN.get(r["schluessel"])
        if m and _art_passt(m[1], t["art"]):
            aus.setdefault(r["spieler_id"], []).append(m[0])
    for r in conn.execute(
            "SELECT a.schluessel, a.typ, z.spieler_id FROM amt_zuteilung z JOIN amt a ON a.id = z.amt_id "
            "WHERE z.training_id = ? ORDER BY a.sort, a.id", (training_id,)):
        wort = FAHRT_ERINNERUNG if r["typ"] == "fahrten" else LISTEN_ERINNERUNG.get(r["schluessel"])
        if wort:
            aus.setdefault(r["spieler_id"], []).append(wort)
    danach = {FAHRT_ERINNERUNG, LISTEN_ERINNERUNG["leibchen"], LISTEN_ERINNERUNG["waschliste"]}
    for dinge in aus.values():            # erst, was mitzubringen ist, dann, was danach zu tun ist
        dinge.sort(key=lambda w: w in danach)
    return aus


def _termin_pruefen(conn: sqlite3.Connection, amt: dict, training_id: int) -> None:
    t = conn.execute("SELECT art, heim FROM trainings WHERE id = ?", (training_id,)).fetchone()
    if t is None:
        raise LookupError("Termin nicht gefunden")
    if not _passt(amt, t["art"], t["heim"]):
        raise ValueError("Dieses Amt hat für diesen Termin keine Liste.")


def zuteilung_setzen(conn: sqlite3.Connection, amt_id: int, training_id: int,
                     spieler_id: int, da: bool) -> bool:
    """Setzt, ob die Spielerin an diesem Termin zugeteilt ist (idempotent). Gibt True zurück,
    wenn die Zuteilung dabei NEU entstanden ist (nur dann geht eine Mitteilung raus)."""
    amt = amt_holen(conn, amt_id)
    if amt["typ"] not in ("zuteilung", "fahrten"):
        raise ValueError("Zu diesem Amt gibt es keine Liste.")
    _termin_pruefen(conn, amt, training_id)
    if conn.execute("SELECT 1 FROM spieler WHERE id = ?", (spieler_id,)).fetchone() is None:
        raise LookupError("Spielerin nicht gefunden")
    if da:
        neu = conn.execute("INSERT OR IGNORE INTO amt_zuteilung (amt_id, training_id, spieler_id) "
                           "VALUES (?,?,?)", (amt_id, training_id, spieler_id)).rowcount == 1
    else:
        neu = False
        conn.execute("DELETE FROM amt_zuteilung WHERE amt_id = ? AND training_id = ? AND spieler_id = ?",
                     (amt_id, training_id, spieler_id))
    conn.commit()
    return neu


def erledigt_setzen(conn: sqlite3.Connection, amt_id: int, training_id: int,
                    spieler_id: int, erledigt: bool) -> None:
    cur = conn.execute(
        "UPDATE amt_zuteilung SET erledigt = ? WHERE amt_id = ? AND training_id = ? AND spieler_id = ?",
        (int(erledigt), amt_id, training_id, spieler_id))
    if cur.rowcount == 0:
        raise LookupError("Diese Zuteilung gibt es nicht.")
    conn.commit()


def bussle_setzen(conn: sqlite3.Connection, amt_id: int, training_id: int, status: str | None) -> None:
    """'da', 'nicht_da' oder None (= zurück auf "noch offen")."""
    amt = amt_holen(conn, amt_id)
    if amt["typ"] != "fahrten":
        raise ValueError("Das ist kein Fahrten-Amt.")
    _termin_pruefen(conn, amt, training_id)
    if status is None:
        conn.execute("DELETE FROM bussle_status WHERE training_id = ?", (training_id,))
    elif status in BUSSLE_STATUS:
        conn.execute("INSERT INTO bussle_status (training_id, status) VALUES (?,?) "
                     "ON CONFLICT(training_id) DO UPDATE SET status = excluded.status",
                     (training_id, status))
    else:
        raise ValueError("Unbekannter Status.")
    conn.commit()
