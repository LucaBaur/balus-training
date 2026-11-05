"""Wochen-To-Dos der Spielerinnen und das Feedback der Trainer."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

import db

from .gemeinsam import _log, hole_conn, require_trainer, require_user


router = APIRouter()


# --------------------------------------------------------- Wochen-To-Dos ----
#  Trainer legen je Spielerin To-Dos an, die Spielerin waehlt eins fuer die Woche, der
#  Trainer gibt Feedback und entscheidet 'bleibt' oder 'erledigt' (Regeln: db.todo_*).
#  Eine Spielerin sieht und aendert nur ihre eigenen To-Dos.

class TodoNeu(BaseModel):
    spieler_id: int
    text: str


class TodoAendern(BaseModel):
    text: str | None = None
    status: str | None = None


class TodoWahl(BaseModel):
    gewaehlt: bool


class TodoFeedback(BaseModel):
    woche: str
    text: str = ""
    ergebnis: str


def _todo_push(spieler_id: int, titel: str, text: str) -> None:
    """Hintergrund-Push an die Konten einer Spielerin (eigene DB-Verbindung, siehe _kommentar_push)."""
    import push
    conn = db.verbinde()
    try:
        an = db.benutzer_ids_fuer_spieler(conn, spieler_id)
        if an:
            _log.info("To-Do-Push -> Benutzer %s: %s", an,
                      push.sende(conn, an, titel, text, url="/", art="rueckmeldungen"))
    except Exception:
        _log.exception("To-Do-Push fehlgeschlagen")
    finally:
        conn.close()


@router.get("/api/todos")
def api_todos(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    sid = benutzer.get("spieler_id")
    if sid is None:
        return {"woche": db.woche_montag(), "max_wahl": db.TODO_MAX_WAHL, "todos": []}
    return db.todos_fuer_spieler(conn, sid)


@router.post("/api/todos/{tid}/waehlen")
def api_todo_waehlen(tid: int, a: TodoWahl, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    sid = benutzer.get("spieler_id")
    if sid is None:
        raise HTTPException(403, "Dein Zugang hat kein Spielerprofil.")
    try:
        db.todo_waehlen(conn, tid, sid, a.gewaehlt)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return db.todos_fuer_spieler(conn, sid)


@router.get("/api/todos/team")
def api_todos_team(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    return db.todos_team(conn)


@router.post("/api/todos")
def api_todo_neu(a: TodoNeu, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        db.todo_anlegen(conn, a.spieler_id, a.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return db.todos_team(conn)


@router.post("/api/todos/{tid}/aendern")
def api_todo_aendern(tid: int, a: TodoAendern, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        gefunden = db.todo_aendern(conn, tid, a.text, a.status)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not gefunden:
        raise HTTPException(404, "To-Do nicht gefunden")
    return db.todos_team(conn)


@router.post("/api/todos/{tid}/loeschen")
def api_todo_loeschen(tid: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    if not db.todo_loeschen(conn, tid):
        raise HTTPException(404, "To-Do nicht gefunden")
    return db.todos_team(conn)


@router.post("/api/todos/{tid}/feedback")
def api_todo_feedback(tid: int, a: TodoFeedback, hintergrund: BackgroundTasks,
                      conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        r = db.todo_feedback(conn, tid, a.woche, a.text, a.ergebnis)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if a.ergebnis == "erledigt":
        hintergrund.add_task(_todo_push, r["spieler_id"], "To-Do geschafft ✓", r["todo"][:100])
    else:
        hintergrund.add_task(_todo_push, r["spieler_id"], "Feedback zu deinem To-Do",
                             f"{r['todo'][:60]} – bleibt noch, schau in die App.")
    return db.todos_team(conn)
