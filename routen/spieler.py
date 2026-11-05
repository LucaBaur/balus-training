"""Spielerinnen: Liste, Kader pflegen, Spielverlauf."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db

from .gemeinsam import hole_conn, require_trainer, require_user


router = APIRouter()


# ------------------------------------------------------------ Datenmodelle ----

class SpielerNeu(BaseModel):
    name: str
    stufe: str = "mittel"          # stark / mittel / schwach
    position: str = "Feld"         # Tor / Feld


class SpielerAendern(BaseModel):
    stufe: str | None = None              # stark / mittel / schwach
    position: str | None = None           # Tor / Feld
    aktiv: bool | None = None
    position_angriff: str | None = None   # "Halblinks/Kreis" (Freitext, '/'-getrennt)


@router.get("/api/spieler")
def api_spieler(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    return db.aktive_spieler(conn)


@router.post("/api/spieler")
def api_spieler_anlegen(s: SpielerNeu, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    if not s.name.strip():
        raise HTTPException(400, "Name fehlt")
    neue_id = db.spieler_anlegen(
        conn, s.name.strip(), stufe=s.stufe, position=s.position
    )
    return {"id": neue_id}


@router.post("/api/spieler/{spieler_id}")
def api_spieler_aendern(spieler_id: int, aenderung: SpielerAendern,
                        conn=Depends(hole_conn), _t=Depends(require_trainer)):
    db.spieler_aktualisieren(
        conn, spieler_id,
        stufe=aenderung.stufe, position=aenderung.position, aktiv=aenderung.aktiv,
        position_angriff=aenderung.position_angriff,
    )
    return {"ok": True}


@router.get("/api/spieler/{spieler_id}/spiele")
def api_spieler_spiele(spieler_id: int, conn=Depends(hole_conn),
                       benutzer=Depends(require_user)):
    # Trainer sehen alle; Spielerinnen nur ihr eigenes Profil.
    if benutzer["rolle"] != "trainer" and benutzer.get("spieler_id") != spieler_id:
        raise HTTPException(403, "Kein Zugriff auf dieses Profil")
    d = db.spieler_detail(conn, spieler_id)
    if d is None:
        raise HTTPException(404, "Spielerin nicht gefunden")
    return d
