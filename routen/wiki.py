"""Wiki-Seiten: Playbook, Uebungen, Gegner, Notizen."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db

from .gemeinsam import hole_conn, require_trainer, require_user


router = APIRouter()


@router.get("/api/seiten")
def api_seiten(kategorie: str | None = None, conn=Depends(hole_conn),
               benutzer=Depends(require_user)):
    """Wiki-Seiten. Spielerinnen sehen NUR das Playbook, Trainer alles."""
    if benutzer["rolle"] != "trainer":
        if kategorie != "playbook":
            raise HTTPException(403, "Nur das Playbook ist für Spielerinnen sichtbar")
    return db.seiten_liste(conn, kategorie)


@router.get("/api/seiten/{sid}")
def api_seite(sid: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    d = db.seite_detail(conn, sid)
    if d is None or d.get("kategorie") == db.SEITEN_ARCHIV:      # archiviert = fuer die App geloescht
        raise HTTPException(404, "Seite nicht gefunden")
    if benutzer["rolle"] != "trainer" and d.get("kategorie") != "playbook":
        raise HTTPException(403, "Nur das Playbook ist für Spielerinnen sichtbar")
    return d


class SeiteNeu(BaseModel):
    titel: str
    kategorie: str                 # 'playbook'/'uebung'/'gegner'/...
    parent_id: int | None = None   # Unterseite einer Gruppe (z. B. Spielzüge)
    markdown: str = ""
    token: str | None = None       # Outbox-Idempotenz (hier ignoriert)


class SeiteAendern(BaseModel):
    titel: str | None = None
    markdown: str | None = None
    token: str | None = None


@router.post("/api/seiten")
def api_seite_anlegen(s: SeiteNeu, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Neue Wiki-Seite anlegen (nur Trainer). Damit ist das Playbook nativ in der
    App pflegbar — kein Umweg mehr über Anytype."""
    titel = s.titel.strip()
    if not titel:
        raise HTTPException(400, "Titel fehlt")
    if s.parent_id is not None:
        eltern = db.seite_detail(conn, s.parent_id)
        if eltern is None:
            raise HTTPException(404, "Übergeordnete Seite nicht gefunden")
        if eltern.get("kategorie") != s.kategorie:
            raise HTTPException(400, "Unterseite muss dieselbe Kategorie haben")
    sid = db.seite_anlegen(conn, titel, s.kategorie, s.parent_id, s.markdown or None)
    return {"id": sid}


@router.post("/api/seiten/{sid}")
def api_seite_aendern(sid: int, a: SeiteAendern, conn=Depends(hole_conn),
                      _t=Depends(require_trainer)):
    """Titel und/oder Inhalt einer Seite setzen (nur Trainer). Idempotent."""
    titel = a.titel.strip() if a.titel is not None else None
    if titel == "":
        raise HTTPException(400, "Titel darf nicht leer sein")
    d = db.seite_detail(conn, sid)
    if d is None or d.get("kategorie") == db.SEITEN_ARCHIV:
        raise HTTPException(404, "Seite nicht gefunden")
    db.seite_speichern(conn, sid, markdown=a.markdown, titel=titel)
    return {"ok": True}


@router.post("/api/seiten/{sid}/loeschen")
def api_seite_loeschen(sid: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Seite loeschen (nur Trainer). Unterseiten ruecken eine Ebene hoch."""
    db.seite_loeschen(conn, sid)      # bereits geloescht -> ebenfalls ok (Outbox)
    return {"ok": True}
