"""Spielerinnen: Stammdaten, Portrait-Felder, Kader-Import."""

from __future__ import annotations

import sqlite3

import elo

from .termine import naechstes_training


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


def portrait_liste(conn: sqlite3.Connection) -> list[dict]:
    """Je aktiver Spielerin: Name (Schluessel fuers Standardfoto), Version des
    selbst hochgeladenen Fotos und gewaehlte Darstellung."""
    rows = conn.execute(
        "SELECT id, name, portrait_v AS v, portrait_modus AS modus "
        "FROM spieler WHERE aktiv = 1 ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def portrait_version(conn: sqlite3.Connection, spieler_id: int) -> int:
    r = conn.execute("SELECT portrait_v FROM spieler WHERE id = ?", (spieler_id,)).fetchone()
    return r["portrait_v"] if r else 0


def portrait_setzen(conn: sqlite3.Connection, spieler_id: int, version: int) -> None:
    """Neues Foto da (version > 0) oder entfernt (0). Ein neues Foto schaltet
    die Darstellung wieder auf 'foto' - wer eins hochlaedt, will es auch sehen."""
    if version:
        conn.execute("UPDATE spieler SET portrait_v = ?, portrait_modus = 'foto' WHERE id = ?",
                     (version, spieler_id))
    else:
        conn.execute("UPDATE spieler SET portrait_v = 0 WHERE id = ?", (spieler_id,))
    conn.commit()


def portrait_modus_setzen(conn: sqlite3.Connection, spieler_id: int, modus: str) -> None:
    if modus not in ("foto", "initial"):
        raise ValueError("modus muss 'foto' oder 'initial' sein")
    conn.execute("UPDATE spieler SET portrait_modus = ? WHERE id = ?", (modus, spieler_id))
    conn.commit()


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
