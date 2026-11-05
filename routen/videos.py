"""Szenen-Clips: hochladen, abspielen, zuordnen."""

from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

import benachrichtigung
import db

from . import pfade
from .gemeinsam import _push_hintergrund, hole_conn, require_trainer, require_user


router = APIRouter()


# ------------------------------------------------------------ Szenen-Videos ----
#  Geschnitten und beschriftet am PC (Projekt "Balu-Videoschnitt"), hier nur als
#  fertige MP4. Eine Spielerin sieht nur die ihr zugeordneten Clips; die
#  Trainerin sieht und verwaltet alle. Der Upload kommt vom Schnittwerkzeug,
#  das sich als Trainerin anmeldet.

class ClipAendern(BaseModel):
    titel: str | None = None
    notiz: str | None = None
    spiel_datum: str | None = None
    spieler_ids: list[int] | None = None


def _clip_oeffentlich(clip: dict) -> dict:
    """Nur die Felder, die das Frontend braucht - ohne den Dateinamen."""
    return {
        "id": clip["id"], "titel": clip["titel"], "notiz": clip.get("notiz"),
        "spiel_datum": clip.get("spiel_datum"), "dauer_s": clip.get("dauer_s"),
        "erstellt_am": clip.get("erstellt_am"), "spieler": clip.get("spieler", []),
        **({"kommentare": clip["kommentare"]} if "kommentare" in clip else {}),   # nur in der Trainer-Liste
    }


@router.get("/api/clips")
def api_clips(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    if benutzer["rolle"] == "trainer":
        clips = db.clips_alle(conn)
    else:
        sid = benutzer.get("spieler_id")
        clips = db.clips_fuer_spieler(conn, sid) if sid else []
    return [_clip_oeffentlich(c) for c in clips]


@router.get("/api/clips/{clip_id}/video")
def api_clip_video(clip_id: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    clip = db.clip_nach_id(conn, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip nicht gefunden")
    darf = (benutzer["rolle"] == "trainer"
            or benutzer.get("spieler_id") in clip["spieler_ids"])
    if not darf:
        raise HTTPException(403, "Kein Zugriff auf diesen Clip")
    pfad = pfade.MEDIA_CLIPS / clip["datei"]
    if not pfad.is_file():
        raise HTTPException(404, "Videodatei fehlt")
    # FileResponse (Starlette) bedient Range-Anfragen selbst -> Seek im Player.
    return FileResponse(pfad, media_type="video/mp4")


@router.post("/api/clips")
async def api_clip_anlegen(hintergrund: BackgroundTasks, video: UploadFile = File(...),
                           meta: str = Form(...), conn=Depends(hole_conn),
                           benutzer=Depends(require_trainer)):
    try:
        m = json.loads(meta)
    except json.JSONDecodeError:
        raise HTTPException(400, "meta ist kein gueltiges JSON")
    titel = (m.get("titel") or "").strip()
    if not titel:
        raise HTTPException(400, "Titel fehlt")
    spiel_datum = (m.get("spiel_datum") or "").strip() or None
    if spiel_datum and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", spiel_datum):
        raise HTTPException(400, "spiel_datum muss YYYY-MM-DD sein")
    spieler_ids = [int(x) for x in (m.get("spieler_ids") or [])]

    daten = await video.read()
    if not daten:
        raise HTTPException(400, "Leere Videodatei")
    datei = f"{uuid.uuid4().hex}.mp4"           # kein Nutzer-Dateiname
    (pfade.MEDIA_CLIPS / datei).write_bytes(daten)

    try:
        clip_id = db.clip_anlegen(
            conn, titel=titel, notiz=(m.get("notiz") or "").strip() or None,
            datei=datei, spiel_datum=spiel_datum, dauer_s=m.get("dauer_s"),
            erstellt_von=benutzer["id"], spieler_ids=spieler_ids)
    except Exception:
        (pfade.MEDIA_CLIPS / datei).unlink(missing_ok=True)   # kein verwaistes File
        raise
    hintergrund.add_task(_push_hintergrund, benachrichtigung.clip_neu, titel, spieler_ids)
    return _clip_oeffentlich(db.clip_nach_id(conn, clip_id))


@router.post("/api/clips/{clip_id}")
def api_clip_aendern(clip_id: int, aenderung: ClipAendern, hintergrund: BackgroundTasks,
                     conn=Depends(hole_conn), _t=Depends(require_trainer)):
    alt = db.clip_nach_id(conn, clip_id)
    if alt is None:
        raise HTTPException(404, "Clip nicht gefunden")
    if aenderung.spiel_datum and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", aenderung.spiel_datum):
        raise HTTPException(400, "spiel_datum muss YYYY-MM-DD sein")
    db.clip_metadaten_setzen(conn, clip_id, titel=aenderung.titel,
                             notiz=aenderung.notiz, spiel_datum=aenderung.spiel_datum)
    if aenderung.spieler_ids is not None:
        db.clip_spieler_setzen(conn, clip_id, aenderung.spieler_ids)
        neu = [s for s in aenderung.spieler_ids if s not in alt["spieler_ids"]]   # nur wer neu dazukommt
        if neu:
            hintergrund.add_task(_push_hintergrund, benachrichtigung.clip_neu,
                                 db.clip_nach_id(conn, clip_id)["titel"], neu)
    return _clip_oeffentlich(db.clip_nach_id(conn, clip_id))


@router.post("/api/clips/{clip_id}/loeschen")
def api_clip_loeschen(clip_id: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    datei = db.clip_loeschen(conn, clip_id)
    if datei is None:
        raise HTTPException(404, "Clip nicht gefunden")
    (pfade.MEDIA_CLIPS / datei).unlink(missing_ok=True)
    return {"ok": True}
