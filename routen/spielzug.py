"""Spielzug-Ansicht: Entscheidungsbaum mit Angriff, Abwehr und Videos je Loesung (Playbook)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import db

from . import pfade
from .gemeinsam import hole_conn, require_trainer, require_user, team_von


router = APIRouter()


class AnsichtIn(BaseModel):
    ansicht: dict | None            # None entfernt die Ansicht
    token: str | None = None        # Outbox-Idempotenz (hier ignoriert: Speichern ersetzt ohnehin alles)


def _seite_im_team(conn, team_id: int, sid: int) -> dict:
    r = conn.execute("SELECT id, kategorie FROM seiten WHERE id = ? AND team_id = ?", (sid, team_id)).fetchone()
    if r is None or r["kategorie"] == db.SEITEN_ARCHIV:        # archiviert = fuer die App geloescht
        raise HTTPException(404, "Seite nicht gefunden")
    return dict(r)


@router.get("/api/seiten/{sid}/ansicht")
def api_ansicht(sid: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Der Baum zur Seite. Spielerinnen sehen nur das Playbook. Ohne Ansicht: {"ansicht": null}."""
    team = team_von(benutzer)
    seite = _seite_im_team(conn, team, sid)
    if benutzer["rolle"] != "trainer" and seite["kategorie"] != "playbook":
        raise HTTPException(403, "Nur das Playbook ist für Spielerinnen sichtbar")
    return {"ansicht": db.ansicht_laden(conn, team, sid)}


@router.post("/api/seiten/{sid}/ansicht")
def api_ansicht_speichern(sid: int, a: AnsichtIn, conn=Depends(hole_conn), benutzer=Depends(require_trainer)):
    """Ansicht ersetzen (nur Trainer). Idempotent; ungueltige Daten -> 400, nichts wird veraendert."""
    team = team_von(benutzer)
    _seite_im_team(conn, team, sid)
    if a.ansicht is None:
        db.ansicht_entfernen(conn, team, sid)
        return {"ok": True}
    try:
        db.ansicht_speichern(conn, team, sid, a.ansicht)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@router.get("/api/spielzug-clips")
def api_spielzug_clips(conn=Depends(hole_conn), benutzer=Depends(require_trainer)):
    """Clips zum Verknuepfen (Spielzuege aus den Spielanalysen des Teams)."""
    return db.spielzug_clips(conn, team_von(benutzer))


@router.get("/api/spielzug-schritte/{schritt_id}/video")
def api_spielzug_video(schritt_id: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Das Video einer Loesung. Das Playbook ist fuer alle da, also auch dieses Video."""
    c = db.spielzug_schritt_clip(conn, team_von(benutzer), schritt_id)
    if c is None:
        raise HTTPException(404, "Kein Video verknüpft")
    pfad = pfade.MEDIA_SZENEN / c["datei"]
    if not pfad.is_file():
        raise HTTPException(404, "Videodatei fehlt")
    return FileResponse(pfad, media_type="video/mp4")      # Range -> Seek im Player
