"""Trainingsspiele und ELO: eintragen, Verlauf, Neuberechnung, Spielerstatistik."""

from __future__ import annotations

import json
import sqlite3
from datetime import date

import elo

from .spieler import spieler_nach_ids


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
