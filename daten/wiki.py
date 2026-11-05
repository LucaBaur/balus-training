"""Wiki-Seiten (Playbook, Uebungen, Gegner, Notizen)."""

from __future__ import annotations

import sqlite3


def seiten_liste(conn: sqlite3.Connection, kategorie: str | None = None) -> list[dict]:
    """Wiki-Seiten (Titel/Kategorie/Hierarchie), ohne die vollen Bodies.
    `parent_id`/`sortierung` gehen mit raus, damit das Frontend den Baum bauen
    kann (Playbook: Gruppe 'Spielzuege' mit Unterseiten)."""
    basis = ("SELECT id, titel, kategorie, parent_id, sortierung, anytype_typ, tags, "
             "(markdown IS NOT NULL AND markdown <> '') AS hat_inhalt FROM seiten ")
    if kategorie:
        rows = conn.execute(basis + "WHERE kategorie = ? ORDER BY sortierung, titel",
                            (kategorie,)).fetchall()
    else:                                       # ohne Kategorie: ohne Archiv
        rows = conn.execute(basis + "WHERE kategorie IS NOT ? ORDER BY kategorie, sortierung, titel",
                            (SEITEN_ARCHIV,)).fetchall()
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


SEITEN_ARCHIV = "archiv"      # Kategorie fuer archivierte Seiten (die App zeigt sie nirgends an)


def seite_loeschen(conn: sqlite3.Connection, sid: int) -> bool:
    """Seite loeschen. Unterseiten bleiben erhalten und ruecken eine Ebene hoch.

    Playbook-Seiten (Spielzuege) werden nur ARCHIVIERT: Text und Ansicht verschwinden, der
    Name bleibt. So bleibt ein Spielzug, der in alten Spielen gespielt wurde, auch im
    Katalog nachvollziehbar (in den Spielen selbst steht der Name ohnehin als Kopie).
    Alle anderen Kategorien werden wirklich geloescht. Wiederholen ist harmlos (Outbox)."""
    r = conn.execute("SELECT kategorie FROM seiten WHERE id = ?", (sid,)).fetchone()
    if r is None:
        return False
    if r["kategorie"] == SEITEN_ARCHIV:
        return True
    conn.execute("UPDATE seiten SET parent_id = NULL WHERE parent_id = ?", (sid,))
    if r["kategorie"] == "playbook":
        conn.execute("UPDATE seiten SET kategorie = ?, markdown = NULL, tags = NULL, parent_id = NULL, "
                     "aktualisiert = datetime('now') WHERE id = ?", (SEITEN_ARCHIV, sid))
    else:
        conn.execute("DELETE FROM seiten WHERE id = ?", (sid,))
    conn.commit()
    return True
