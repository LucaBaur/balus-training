"""Wochen-To-Dos: Ziele, Wahl, Feedback."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from .spieler import aktive_spieler
from .zeit import _berlin


# ============================================================ Wochen-To-Dos ==
#  Siehe Tabellen 'todo' und 'todo_woche'. Die Rechte (wer darf was) pruefen die Routen (routen/todos.py);
#  hier stehen die Regeln, die immer gelten: Textlaenge, Wahl-Limit, Feedback nur
#  fuer gewaehlte To-Dos.

TODO_MAX_WAHL = 1          # So viele To-Dos darf eine Spielerin je Woche waehlen
TODO_MAX_TEXT = 200
TODO_ERGEBNISSE = ("bleibt", "erledigt")


def woche_montag(tag: date | None = None) -> str:
    """Montag der Woche (ISO-Datum) - der Schluessel einer Woche in 'todo_woche'.
    Berechnet in deutscher Zeit, der Server selbst laeuft in UTC."""
    tag = tag or datetime.now(_berlin()).date()
    return (tag - timedelta(days=tag.weekday())).isoformat()


def _todo_text(text: str) -> str:
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("Der Text darf nicht leer sein.")
    if len(text) > TODO_MAX_TEXT:
        raise ValueError(f"Der Text ist zu lang (höchstens {TODO_MAX_TEXT} Zeichen).")
    return text


def todo_anlegen(conn: sqlite3.Connection, spieler_id: int, text: str) -> int:
    text = _todo_text(text)
    if conn.execute("SELECT 1 FROM spieler WHERE id = ?", (spieler_id,)).fetchone() is None:
        raise ValueError("Spielerin nicht gefunden.")
    cur = conn.execute("INSERT INTO todo (spieler_id, text) VALUES (?, ?)", (spieler_id, text))
    conn.commit()
    return int(cur.lastrowid)


def todo_nach_id(conn: sqlite3.Connection, todo_id: int) -> dict | None:
    r = conn.execute("SELECT * FROM todo WHERE id = ?", (todo_id,)).fetchone()
    return dict(r) if r else None


def todo_aendern(conn: sqlite3.Connection, todo_id: int, text: str | None = None,
                 status: str | None = None) -> bool:
    """Text aendern und/oder ein erledigtes To-Do wieder oeffnen (status='offen')."""
    t = todo_nach_id(conn, todo_id)
    if t is None:
        return False
    if text is not None:
        conn.execute("UPDATE todo SET text = ? WHERE id = ?", (_todo_text(text), todo_id))
    if status is not None:
        if status not in ("offen", "erledigt"):
            raise ValueError("Unbekannter Status.")
        conn.execute("UPDATE todo SET status = ?, erledigt_am = "
                     "CASE WHEN ? = 'erledigt' THEN datetime('now') END WHERE id = ?",
                     (status, status, todo_id))
    conn.commit()
    return True


def todo_loeschen(conn: sqlite3.Connection, todo_id: int) -> bool:
    cur = conn.execute("DELETE FROM todo WHERE id = ?", (todo_id,))   # todo_woche folgt per CASCADE
    conn.commit()
    return cur.rowcount > 0


def _todos_laden(conn: sqlite3.Connection, spieler_ids: list[int]) -> dict[int, list[dict]]:
    """spieler_id -> To-Dos (offene zuerst), je mit 'wochen' (neueste zuerst), 'gewaehlt'
    (in der laufenden Woche gewaehlt) und 'offene_woche' (juengste Wahl ohne Feedback)."""
    if not spieler_ids:
        return {}
    jetzt = woche_montag()
    pl = ",".join("?" for _ in spieler_ids)
    todos = [dict(r) for r in conn.execute(
        f"SELECT * FROM todo WHERE spieler_id IN ({pl}) "
        "ORDER BY status = 'erledigt', id", spieler_ids)]
    wochen: dict[int, list[dict]] = {}
    if todos:
        ids = [t["id"] for t in todos]
        pl2 = ",".join("?" for _ in ids)
        for w in conn.execute(
                f"SELECT * FROM todo_woche WHERE todo_id IN ({pl2}) ORDER BY woche DESC", ids):
            wochen.setdefault(w["todo_id"], []).append(
                {k: w[k] for k in ("woche", "feedback", "ergebnis", "feedback_am")})
    aus: dict[int, list[dict]] = {sid: [] for sid in spieler_ids}
    for t in todos:
        ws = wochen.get(t["id"], [])
        t["wochen"] = ws
        t["gewaehlt"] = any(w["woche"] == jetzt for w in ws)
        t["offene_woche"] = next((w["woche"] for w in ws if w["ergebnis"] is None), None)
        # Feedback ist erst faellig, wenn die gewaehlte Woche vorbei ist: so lange probiert die
        # Spielerin das To-Do noch aus. ISO-Daten lassen sich als Text vergleichen.
        t["feedback_faellig"] = any(w["ergebnis"] is None and w["woche"] < jetzt for w in ws)
        aus[t["spieler_id"]].append(t)
    return aus


def todos_fuer_spieler(conn: sqlite3.Connection, spieler_id: int) -> dict:
    return {"woche": woche_montag(), "max_wahl": TODO_MAX_WAHL,
            "todos": _todos_laden(conn, [spieler_id]).get(spieler_id, [])}


def todos_team(conn: sqlite3.Connection) -> dict:
    """Trainer-Ueberblick: alle aktiven Spielerinnen mit ihren To-Dos. 'warten' zaehlt
    die Wahlen ohne Feedback (die laufende Woche eingeschlossen)."""
    spieler = aktive_spieler(conn)
    je = _todos_laden(conn, [s["id"] for s in spieler])
    liste = [{"spieler_id": s["id"], "name": s["name"], "todos": je[s["id"]]} for s in spieler]
    warten = sum(1 for e in liste for t in e["todos"] if t["offene_woche"])
    faellig = sum(1 for e in liste for t in e["todos"] if t["feedback_faellig"])
    return {"woche": woche_montag(), "max_wahl": TODO_MAX_WAHL, "warten": warten,
            "warten_faellig": faellig, "spielerinnen": liste}


def todo_waehlen(conn: sqlite3.Connection, todo_id: int, spieler_id: int,
                 gewaehlt: bool) -> None:
    """Setzt die Wahl fuer die laufende Woche auf den gewuenschten Zustand (idempotent).
    Eine Wahl mit Feedback laesst sich nicht mehr zuruecknehmen."""
    t = todo_nach_id(conn, todo_id)
    if t is None or t["spieler_id"] != spieler_id:
        raise ValueError("To-Do nicht gefunden.")
    woche = woche_montag()
    vorhanden = conn.execute("SELECT * FROM todo_woche WHERE todo_id = ? AND woche = ?",
                             (todo_id, woche)).fetchone()
    if gewaehlt:
        if vorhanden:
            return
        if t["status"] != "offen":
            raise ValueError("Dieses To-Do ist schon erledigt.")
        n = conn.execute(
            "SELECT COUNT(*) FROM todo_woche w JOIN todo t ON t.id = w.todo_id "
            "WHERE t.spieler_id = ? AND w.woche = ?", (spieler_id, woche)).fetchone()[0]
        if n >= TODO_MAX_WAHL:
            raise ValueError("Du hast für diese Woche schon gewählt. "
                             "Nimm die Auswahl zuerst zurück, wenn du wechseln willst.")
        conn.execute("INSERT INTO todo_woche (todo_id, woche) VALUES (?, ?)", (todo_id, woche))
    elif vorhanden:
        if vorhanden["ergebnis"] is not None:
            raise ValueError("Dazu gibt es schon Feedback - die Auswahl bleibt.")
        conn.execute("DELETE FROM todo_woche WHERE id = ?", (vorhanden["id"],))
    conn.commit()


def todo_feedback(conn: sqlite3.Connection, todo_id: int, woche: str, text: str,
                  ergebnis: str) -> dict:
    """Feedback des Trainers zu einer gewaehlten Woche. 'erledigt' hakt das To-Do ab,
    'bleibt' haelt es offen (auch ein vorher erledigtes). Liefert {spieler_id, todo}."""
    if ergebnis not in TODO_ERGEBNISSE:
        raise ValueError("Bitte „bleibt“ oder „erledigt“ wählen.")
    t = todo_nach_id(conn, todo_id)
    w = conn.execute("SELECT id FROM todo_woche WHERE todo_id = ? AND woche = ?",
                     (todo_id, woche)).fetchone()
    if t is None or w is None:
        raise ValueError("Diese Woche wurde für das To-Do nicht gewählt.")
    text = " ".join((text or "").split())[:1000]
    conn.execute("UPDATE todo_woche SET feedback = ?, ergebnis = ?, feedback_am = datetime('now') "
                 "WHERE id = ?", (text or None, ergebnis, w["id"]))
    if ergebnis == "erledigt":
        conn.execute("UPDATE todo SET status = 'erledigt', erledigt_am = datetime('now') "
                     "WHERE id = ?", (todo_id,))
    else:
        conn.execute("UPDATE todo SET status = 'offen', erledigt_am = NULL WHERE id = ?", (todo_id,))
    conn.commit()
    return {"spieler_id": t["spieler_id"], "todo": t["text"]}


def todos_wartend(conn: sqlite3.Connection) -> list[dict]:
    """Gewaehlte To-Dos ohne Feedback (bis einschliesslich der laufenden Woche) - Grundlage
    der Wochenend-Benachrichtigung an die Trainer."""
    return [dict(r) for r in conn.execute(
        "SELECT s.name AS spieler, t.text AS todo, w.woche FROM todo_woche w "
        "JOIN todo t ON t.id = w.todo_id JOIN spieler s ON s.id = t.spieler_id "
        "WHERE w.ergebnis IS NULL AND w.woche <= ? AND s.aktiv = 1 ORDER BY s.name",
        (woche_montag(),))]
