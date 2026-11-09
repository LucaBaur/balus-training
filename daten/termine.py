"""Termine (Training, Test- und Ligaspiele), Teilnahme und Trainingsplan."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from datetime import time as _uhrzeit

from .zeit import _berlin


# Termin-Arten. 'training' ist der Normalfall (und der Default in der DB),
# 'testspiel'/'ligaspiel' sind Spiele: sie haben einen Gegner, sind Heim- oder
# Auswaertsspiel und tragen bei Auswaerts eine Abfahrtszeit.
ARTEN = ("training", "testspiel", "ligaspiel")
SPIEL_ARTEN = ("testspiel", "ligaspiel")


# Freiwillige Trainings: Wochentage (Montag = 0 ... Freitag = 4), an denen ein Training freiwillig ist.
# Dort ist es in Ordnung, wenn nur wenige kommen (individuelles Training): keine Warnung wegen zu
# weniger Zusagen, weder für Trainer noch für Spielerinnen. Spiele sind nie freiwillig.
# Ändert sich das, genügt diese eine Zeile; Frontend und Mitteilungen lesen das Feld `freiwillig`.
FREIWILLIGE_WOCHENTAGE = (4,)


def ist_freiwillig(datum: str | None, art: str | None = "training") -> bool:
    if art not in (None, "training"):
        return False
    try:
        return date.fromisoformat(datum or "").weekday() in FREIWILLIGE_WOCHENTAGE
    except ValueError:
        return False


# ============================================ Wochenmuster und Zeiten ändern ====
#  Das Training ist EIN Objekt (Zeile in `trainings`). Eine neue Zeit ändert nur Uhrzeit/Ort daran, nie das Objekt:
#  Zu-/Absagen, Plan, Ämter und Aufstellung bleiben. Das Wochenmuster (`trainings_regel`) bestimmt, womit
#  trainings_termine.py künftige Trainings anlegt.

# Startwerte des Wochenmusters (Montag = 0): (Beginn, Ort). Danach gilt die Tabelle.
REGELN_START = {0: ("20:00", "Gerhausen"), 3: ("20:15", "Blaubeuren")}
WOCHENTAGE_NAMEN = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


def trainings_regeln(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    """Wochenmuster {Wochentag: (Uhrzeit, Ort)}; fehlende Zeilen werden aus REGELN_START ergänzt."""
    for wt, (uhr, ort) in REGELN_START.items():
        conn.execute("INSERT OR IGNORE INTO trainings_regel (wochentag, uhrzeit, ort) VALUES (?,?,?)", (wt, uhr, ort))
    conn.commit()
    return {r["wochentag"]: (r["uhrzeit"], r["ort"])
            for r in conn.execute("SELECT wochentag, uhrzeit, ort FROM trainings_regel ORDER BY wochentag")}


def _uhrzeit_pruefen(wert: str | None) -> str | None:
    """None = nicht ändern. Sonst 'HH:MM' (24 Stunden), alles andere ist ein Fehler."""
    if wert is None or not str(wert).strip():
        return None
    try:
        return _uhrzeit.fromisoformat(str(wert).strip()).strftime("%H:%M")
    except ValueError:
        raise ValueError("Die Uhrzeit muss so aussehen: 18:30.")


def termin_aendern(conn: sqlite3.Connection, tid: int, uhrzeit: str | None = None, ort: str | None = None,
                   titel: str | None = None, gegner: str | None = None, abfahrt: str | None = None) -> dict | None:
    """Ändert Uhrzeit, Ort, Titel (und bei Spielen Gegner, Abfahrt) EINES Termins; nicht Angegebenes bleibt.
    Heißt das Training noch 'Training <alter Ort>', zieht der Titel mit dem neuen Ort mit.
    Liefert {'vorher': {...}, 'nachher': {...}} oder None, wenn es den Termin nicht gibt."""
    t = conn.execute("SELECT * FROM trainings WHERE id = ?", (tid,)).fetchone()
    if t is None:
        return None
    uhrzeit, abfahrt = _uhrzeit_pruefen(uhrzeit), _uhrzeit_pruefen(abfahrt)
    neu: dict[str, str] = {}
    if uhrzeit:
        neu["uhrzeit"] = uhrzeit
    if ort is not None and ort.strip():
        neu["ort"] = ort.strip()[:80]
        if (t["titel"] or "") == f"Training {t['ort']}" and t["ort"]:
            neu["titel"] = f"Training {neu['ort']}"
    if titel is not None and titel.strip():
        neu["titel"] = titel.strip()[:120]
    if t["art"] in SPIEL_ARTEN:
        if gegner is not None and gegner.strip():
            neu["gegner"] = gegner.strip()[:80]
        if abfahrt and t["heim"] == 0:
            neu["abfahrt"] = abfahrt
    if neu:
        conn.execute(f"UPDATE trainings SET {', '.join(f'{k} = ?' for k in neu)} WHERE id = ?", [*neu.values(), tid])
        conn.commit()
    return {"vorher": {k: t[k] for k in neu}, "nachher": neu}


def serie_aendern(conn: sqlite3.Connection, wochentag: int, ab_datum: str, uhrzeit: str | None = None,
                  ort: str | None = None) -> dict:
    """Neue Zeit/neuer Ort für alle Trainings dieses Wochentags AB `ab_datum` (einschließlich) und für das
    Wochenmuster, damit auch künftig angelegte Trainings stimmen. Die Termine bleiben dieselben Objekte,
    niemand muss neu antworten. Einzeln abweichende Zeiten ab dem Datum werden mit überschrieben.
    Liefert {'termine': [ids], 'vorher': (Uhrzeit, Ort), 'nachher': (Uhrzeit, Ort)}."""
    regeln = trainings_regeln(conn)
    if wochentag not in regeln:
        raise ValueError("Für diesen Wochentag gibt es kein Wochenmuster.")
    try:
        date.fromisoformat(ab_datum)
    except (TypeError, ValueError):
        raise ValueError("Das Datum fehlt oder ist ungültig.")
    uhrzeit = _uhrzeit_pruefen(uhrzeit)
    ort = (ort or "").strip()[:80] or None
    if not uhrzeit and not ort:
        raise ValueError("Es gibt nichts zu ändern.")
    alt_uhr, alt_ort = regeln[wochentag]
    neu_uhr, neu_ort = uhrzeit or alt_uhr, ort or alt_ort
    conn.execute("UPDATE trainings_regel SET uhrzeit = ?, ort = ? WHERE wochentag = ?", (neu_uhr, neu_ort, wochentag))
    ids = []
    for t in conn.execute("SELECT id, datum FROM trainings WHERE art = 'training' AND datum >= ? ORDER BY datum",
                          (ab_datum,)).fetchall():
        if date.fromisoformat(t["datum"]).weekday() != wochentag:
            continue
        termin_aendern(conn, t["id"], uhrzeit=uhrzeit, ort=ort)
        ids.append(t["id"])
    conn.commit()
    return {"termine": ids, "vorher": (alt_uhr, alt_ort), "nachher": (neu_uhr, neu_ort)}


# Opt-out statt Opt-in: Bei normalen Trainings (Mo/Do, nicht freiwillig, keine Spiele) sind alle aus dem Kader
# automatisch zugesagt, sobald es das Training gibt (Zeile in training_teilnahme mit quelle 'auto'). Wer nicht
# kommt, sagt bis 24 Stunden vorher in der App ab, danach nur noch beim Trainer (der trägt es ein).
# Gilt für Trainings ab diesem Datum; davor bleibt alles wie bisher (Zu-/Absage aus SpielerPlus oder App).
AUTO_ZUSAGE_AB = "2026-11-09"
ABSAGE_VORLAUF_STUNDEN = 24


def auto_zusage_gilt(datum: str | None, art: str | None = "training") -> bool:
    """Gilt für diesen Termin die automatische Zusage samt 24-Stunden-Frist?"""
    return (art in (None, "training") and bool(datum) and datum >= AUTO_ZUSAGE_AB
            and not ist_freiwillig(datum, art))


def absage_frist(datum: str | None, uhrzeit: str | None, art: str | None = "training") -> datetime | None:
    """Bis wann Spielerinnen selbst absagen dürfen (Berliner Zeit). None: für diesen Termin gilt keine Frist.
    Ohne Uhrzeit zählt der Beginn des Tages, die Frist ist dann entsprechend früh."""
    if not auto_zusage_gilt(datum, art):
        return None
    try:
        uhr = _uhrzeit.fromisoformat(uhrzeit) if uhrzeit else _uhrzeit(0, 0)
    except ValueError:
        uhr = _uhrzeit(0, 0)
    return datetime.combine(date.fromisoformat(datum), uhr, tzinfo=_berlin()) - timedelta(hours=ABSAGE_VORLAUF_STUNDEN)


def absage_frist_iso(datum: str | None, uhrzeit: str | None, art: str | None = "training") -> str | None:
    f = absage_frist(datum, uhrzeit, art)
    return f.isoformat() if f else None


def absage_gesperrt(datum: str | None, uhrzeit: str | None, art: str | None = "training",
                    jetzt: datetime | None = None) -> bool:
    """True, wenn die Frist für diesen Termin schon vorbei ist."""
    f = absage_frist(datum, uhrzeit, art)
    return f is not None and (jetzt or datetime.now(_berlin())) > f


def auto_zusagen(conn: sqlite3.Connection, heute: date | None = None, trocken: bool = False) -> int:
    """Trägt alle aktiven Spielerinnen bei kommenden normalen Trainings als zugesagt ein (quelle 'auto'), wo noch
    keine Zeile existiert. Idempotent: Vorhandenes (auch Absagen) bleibt unberührt. Liefert die Zahl neuer Zeilen
    (mit `trocken` die Zahl, die es würden, ohne etwas zu schreiben)."""
    heute = heute or date.today()
    neu = 0
    for t in conn.execute("SELECT id, datum, art FROM trainings WHERE art = 'training' AND datum >= ?",
                          (heute.isoformat(),)).fetchall():
        if not auto_zusage_gilt(t["datum"], t["art"]):
            continue
        if trocken:
            neu += conn.execute(
                "SELECT COUNT(*) FROM spieler s WHERE s.aktiv = 1 AND NOT EXISTS ("
                "  SELECT 1 FROM training_teilnahme x WHERE x.training_id = ? AND x.spieler_id = s.id)",
                (t["id"],)).fetchone()[0]
            continue
        neu += conn.execute(
            "INSERT OR IGNORE INTO training_teilnahme (training_id, spieler_id, status, quelle) "
            "SELECT ?, s.id, 'anwesend', 'auto' FROM spieler s WHERE s.aktiv = 1", (t["id"],)).rowcount
    conn.commit()
    return neu


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
    liste = [dict(r) for r in rows]
    for t in liste:
        t["freiwillig"] = int(ist_freiwillig(t["datum"], t["art"]))
        t["absage_frist"] = absage_frist_iso(t["datum"], t["uhrzeit"], t["art"])
    return liste


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
    d["freiwillig"] = int(ist_freiwillig(d.get("datum"), d.get("art")))
    d["absage_frist"] = absage_frist_iso(d.get("datum"), d.get("uhrzeit"), d.get("art"))
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
        # 'auto' ist nur die Voreinstellung (alle sind dabei), keine Eingabe: eine echte Antwort aus
        # SpielerPlus darf sie ersetzen.
        "WHERE training_teilnahme.quelle IN ('spielerplus', 'anytype', 'auto')",
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


def einteilung_trainings(conn: sqlite3.Connection, tage_zurueck: int = 1,
                         tage_vor: int = 21, heute: date | None = None) -> list[dict]:
    """Trainings um heute herum samt den Zusagen - Grundlage fuer "Training uebernehmen"
    in der Team-Einteilung. Nur art='training' (Spiele werden nicht eingeteilt).

    `spieler_ids` sind die zugesagten AKTIVEN Spielerinnen (die allein lassen sich
    einteilen); `anwesend_gesamt` zaehlt alle Zusagen, damit die App "n nicht im
    Kader" melden kann."""
    heute = heute or date.today()
    von = (heute - timedelta(days=tage_zurueck)).isoformat()
    bis = (heute + timedelta(days=tage_vor)).isoformat()
    out = []
    for t in conn.execute(
            "SELECT id, datum, titel FROM trainings "
            "WHERE art = 'training' AND datum BETWEEN ? AND ? ORDER BY datum, id", (von, bis)):
        zu = conn.execute(
            "SELECT tt.spieler_id, s.aktiv FROM training_teilnahme tt "
            "JOIN spieler s ON s.id = tt.spieler_id "
            "WHERE tt.training_id = ? AND tt.status = 'anwesend' ORDER BY s.name", (t["id"],)).fetchall()
        out.append({"id": t["id"], "datum": t["datum"], "name": t["titel"],
                    "spieler_ids": [r["spieler_id"] for r in zu if r["aktiv"]],
                    "anwesend_gesamt": len(zu)})
    return out


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
        auto_zusagen(conn)
        return tid, False
    cur = conn.execute(
        "INSERT INTO trainings (datum, titel, uhrzeit, ort, plan_markdown, "
        "art, gegner, heim, abfahrt) VALUES (?,?,?,?,?,?,?,?,?)",
        (datum, titel or "", uhrzeit, ort, plan_markdown,
         art, gegner, heim, abfahrt),
    )
    conn.commit()
    auto_zusagen(conn)                       # alle aus dem Kader sind gleich dabei (gilt nur, wo die Regel gilt)
    return int(cur.lastrowid), True


def zusagen_anzahl(conn: sqlite3.Connection, training_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM training_teilnahme WHERE training_id = ? AND status = 'anwesend'",
        (training_id,)).fetchone()[0]


def zugesagte_spieler_benutzer(conn: sqlite3.Connection, training_id: int) -> list[int]:
    """Benutzer-IDs aktiver Spielerinnen, die für dieses Training zugesagt sind (auch automatisch):
    die Empfängerinnen des Hinweises auf die Absagefrist."""
    rows = conn.execute(
        "SELECT b.id FROM benutzer b "
        "WHERE b.rolle = 'spieler' AND b.aktiv = 1 AND b.spieler_id IS NOT NULL "
        "AND b.spieler_id IN (SELECT id FROM spieler WHERE aktiv = 1) "
        "AND b.spieler_id IN ("
        "  SELECT spieler_id FROM training_teilnahme WHERE training_id = ? AND status = 'anwesend')",
        (training_id,)).fetchall()
    return [r["id"] for r in rows]


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
        "AND b.spieler_id IN (SELECT id FROM spieler WHERE aktiv = 1) "      # keine Helferinnen (ehemalige mit Konto)
        "AND b.spieler_id NOT IN ("
        "  SELECT spieler_id FROM training_teilnahme "
        "  WHERE training_id = ? AND quelle IN ('app', 'trainer', 'auto'))",       # 'auto': schon eingetragen, nichts offen
        (training_id,)).fetchall()
    return [r["id"] for r in rows]
