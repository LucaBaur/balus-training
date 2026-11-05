"""Portraits der Spielerinnen: hochladen, anzeigen, loeschen, Modus waehlen."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import db

from . import pfade
from .gemeinsam import hole_conn, require_user


router = APIRouter()


# --------------------------------------------------------------- Portraits ----
#  Standardfotos liegen statisch unter /portraits/ (portraits.py). Zusaetzlich
#  kann jede Spielerin ein EIGENES Foto hochladen und auf den Anfangsbuchstaben
#  umstellen. Das Foto kommt fertig zugeschnitten (5:6, JPEG) aus dem Browser;
#  der Server prueft nur, dass es wirklich ein kleines JPEG ist.
PORTRAIT_MAX_BYTES = 400_000


class PortraitModus(BaseModel):
    modus: str                              # "foto" | "initial"


def _eigene_spielerin(benutzer: dict) -> int:
    sid = benutzer.get("spieler_id")
    if not sid:
        raise HTTPException(400, "Zu diesem Zugang gehört keine Spielerin")
    return int(sid)


@router.get("/api/portraits")
def api_portraits(conn=Depends(hole_conn), _u=Depends(require_user)):
    return db.portrait_liste(conn)


@router.get("/api/portrait/{spieler_id}")
def api_portrait(spieler_id: int, conn=Depends(hole_conn), _u=Depends(require_user)):
    pfad = pfade.MEDIA_PORTRAITS / f"{spieler_id}.jpg"
    if not db.portrait_version(conn, spieler_id) or not pfad.is_file():
        raise HTTPException(404, "Kein eigenes Foto")
    # Die URL traegt ?v=<Version>: ein neues Foto ist eine neue URL, darum darf
    # das alte lange im Cache bleiben.
    return FileResponse(pfad, media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=31536000",
                                 "X-Content-Type-Options": "nosniff"})


@router.post("/api/ich/portrait")
async def api_portrait_hochladen(bild: UploadFile = File(...), conn=Depends(hole_conn),
                                 benutzer=Depends(require_user)):
    sid = _eigene_spielerin(benutzer)
    daten = await bild.read(PORTRAIT_MAX_BYTES + 1)
    if not daten:
        raise HTTPException(400, "Leere Datei")
    if len(daten) > PORTRAIT_MAX_BYTES:
        raise HTTPException(413, "Bild zu groß")
    if not daten.startswith(b"\xff\xd8\xff"):
        raise HTTPException(400, "Nur JPEG-Bilder")
    tmp = pfade.MEDIA_PORTRAITS / f"{sid}.jpg.part"
    tmp.write_bytes(daten)
    tmp.replace(pfade.MEDIA_PORTRAITS / f"{sid}.jpg")          # atomar: nie ein halbes Bild
    version = int(time.time())
    db.portrait_setzen(conn, sid, version)
    return {"v": version, "modus": "foto"}


@router.post("/api/ich/portrait/loeschen")
def api_portrait_loeschen(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    sid = _eigene_spielerin(benutzer)
    (pfade.MEDIA_PORTRAITS / f"{sid}.jpg").unlink(missing_ok=True)
    db.portrait_setzen(conn, sid, 0)
    return {"ok": True}


@router.post("/api/ich/portrait-modus")
def api_portrait_modus(a: PortraitModus, conn=Depends(hole_conn),
                       benutzer=Depends(require_user)):
    sid = _eigene_spielerin(benutzer)
    if a.modus not in ("foto", "initial"):
        raise HTTPException(400, "modus muss 'foto' oder 'initial' sein")
    db.portrait_modus_setzen(conn, sid, a.modus)
    return {"modus": a.modus}
