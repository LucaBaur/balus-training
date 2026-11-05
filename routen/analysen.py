"""Spielanalysen mit Video, Ereignissen, Spielzuegen und Szenen-Clips."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

import benachrichtigung
import db

from . import pfade
from .gemeinsam import _push_hintergrund, hole_conn, require_trainer, require_user


router = APIRouter()


KEY_MUSTER = re.compile(r"[A-Za-z0-9_\-]{1,40}")
EVENT_TYPEN = {"tor", "fehlwurf", "ballverlust", "strafe", "siebenmeter", "parade"}
AMPELN = {"gruen", "orange", "rot"}


class EventIn(BaseModel):
    typ: str
    t: float
    spieler_id: int | None = None
    assist_id: int | None = None
    detail: str | None = None
    key: str | None = None            # Szenen-Kennung (-> Clip); Tor aus einem Spielzug teilt dessen Kennung


class ZugIn(BaseModel):
    name: str
    t_start: float
    t_ende: float
    ampel: str
    kommentar: str | None = None
    spieler_ids: list[int] = []
    key: str | None = None


class AnalyseIn(BaseModel):
    extern_id: str
    gegner: str
    datum: str | None = None
    art: str | None = None
    events: list[EventIn] = []
    zuege: list[ZugIn] = []


def _analyse_stats(inhalt: dict, spieler_id: int | None) -> dict:
    ev = [e for e in inhalt["events"] if spieler_id is None or e["spieler_id"] == spieler_id]
    n = lambda typ: sum(1 for e in ev if e["typ"] == typ)          # noqa: E731
    return {
        "tore": n("tor"), "fehlwuerfe": n("fehlwurf"), "ballverluste": n("ballverlust"),
        "strafen": n("strafe") + n("siebenmeter"), "paraden": n("parade"),
        "vorlagen": sum(1 for e in inhalt["events"]
                        if spieler_id is not None and e["assist_id"] == spieler_id),
        "zuege": len(inhalt["zuege"]),
        "gruen": sum(1 for z in inhalt["zuege"] if z["ampel"] == "gruen"),
        "orange": sum(1 for z in inhalt["zuege"] if z["ampel"] == "orange"),
        "rot": sum(1 for z in inhalt["zuege"] if z["ampel"] == "rot"),
    }


def _analyse_ausgabe(conn, a: dict, spieler_id: int | None) -> dict:
    inhalt = db.analyse_inhalt(conn, a["id"], spieler_id)
    return {"id": a["id"], "gegner": a["gegner"], "datum": a["datum"], "art": a["art"],
            "video_da": bool(a["datei"]), **inhalt,
            "stats": _analyse_stats(inhalt, spieler_id)}


@router.post("/api/analysen")
def api_analyse_speichern(a: AnalyseIn, conn=Depends(hole_conn), benutzer=Depends(require_trainer)):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", a.extern_id):
        raise HTTPException(400, "extern_id ungueltig")
    if not a.gegner.strip():
        raise HTTPException(400, "Gegner fehlt")
    datum = (a.datum or "").strip() or None
    if datum and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", datum):
        raise HTTPException(400, "datum muss YYYY-MM-DD sein")
    for e in a.events:
        if e.typ not in EVENT_TYPEN or e.t < 0:
            raise HTTPException(400, f"Ungueltiges Ereignis: {e.typ!r} bei {e.t}")
    for z in a.zuege:
        if z.ampel not in AMPELN or not z.name.strip() or z.t_start < 0 or z.t_ende < z.t_start:
            raise HTTPException(400, f"Ungueltiger Spielzug: {z.name!r}")
    keys = {x.key for x in [*a.events, *a.zuege] if x.key}
    if any(not KEY_MUSTER.fullmatch(k) for k in keys):
        raise HTTPException(400, "Ungueltige Szenen-Kennung")
    aid = db.analyse_speichern(
        conn, a.extern_id, a.gegner.strip(), datum, (a.art or "").strip() or None,
        [e.model_dump() for e in a.events], [z.model_dump() for z in a.zuege], benutzer["id"])
    for datei in db.szene_clips_aufraeumen(conn, aid, keys):       # Szene gibt es nicht mehr -> Clip weg
        (pfade.MEDIA_SZENEN / datei).unlink(missing_ok=True)
    r = db.analyse_nach_id(conn, aid)
    return {"id": aid, "video_da": bool(r["datei"]), "events": len(a.events), "zuege": len(a.zuege),
            "clips": len(db.szene_clips_liste(conn, aid))}


@router.put("/api/analysen/{aid}/video")
async def api_analyse_video(aid: int, request: Request, hintergrund: BackgroundTasks,
                            conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Rohes Streaming des Videos (Body = MP4-Bytes). Schreibt in eine
    Temp-Datei und benennt erst am Ende um - ein abgebrochener Upload hinterlaesst
    kein halbes Video unter dem echten Namen."""
    if db.analyse_nach_id(conn, aid) is None:
        raise HTTPException(404, "Analyse nicht gefunden")
    datei = f"{uuid.uuid4().hex}.mp4"
    tmp = pfade.MEDIA_SPIELE / (datei + ".part")
    groesse = 0
    try:
        with open(tmp, "wb") as f:
            async for stueck in request.stream():
                groesse += len(stueck)
                f.write(stueck)
        if groesse == 0:
            raise HTTPException(400, "Leere Videodatei")
        tmp.replace(pfade.MEDIA_SPIELE / datei)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    alt = db.analyse_datei_setzen(conn, aid, datei)
    if alt:
        (pfade.MEDIA_SPIELE / alt).unlink(missing_ok=True)
    hintergrund.add_task(_push_hintergrund, benachrichtigung.analyse_video_neu, aid)
    return {"ok": True, "bytes": groesse}


@router.get("/api/analysen/{aid}/clips")
def api_analyse_clips(aid: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Welche Szenen-Clips es schon gibt (Kennung + Ausschnitt) - die Desktop-App laedt nur Fehlendes nach."""
    if db.analyse_nach_id(conn, aid) is None:
        raise HTTPException(404, "Analyse nicht gefunden")
    return db.szene_clips_liste(conn, aid)


@router.put("/api/analysen/{aid}/clips/{key}")
async def api_analyse_clip_hochladen(aid: int, key: str, von: float, bis: float, request: Request,
                                     conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Ein Szenen-Clip als roher Stream (Body = MP4). Ersetzt einen vorhandenen Clip derselben Szene."""
    if db.analyse_nach_id(conn, aid) is None:
        raise HTTPException(404, "Analyse nicht gefunden")
    if not KEY_MUSTER.fullmatch(key) or von < 0 or bis <= von:
        raise HTTPException(400, "Ungueltige Szene oder Ausschnitt")
    datei = f"{uuid.uuid4().hex}.mp4"
    tmp = pfade.MEDIA_SZENEN / (datei + ".part")
    groesse = 0
    try:
        with open(tmp, "wb") as f:
            async for stueck in request.stream():
                groesse += len(stueck)
                f.write(stueck)
        if groesse == 0:
            raise HTTPException(400, "Leerer Clip")
        tmp.replace(pfade.MEDIA_SZENEN / datei)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    alt = db.szene_clip_speichern(conn, aid, key, datei, von, bis)
    if alt:
        (pfade.MEDIA_SZENEN / alt).unlink(missing_ok=True)
    return {"ok": True, "bytes": groesse}


@router.get("/api/szenen/{cid}/video")
def api_szene_video(cid: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Szenen-Clip ansehen: Trainer immer, Spielerinnen nur bei Szenen, an denen sie beteiligt sind."""
    c = db.szene_clip_nach_id(conn, cid)
    if c is None:
        raise HTTPException(404, "Clip nicht gefunden")
    if benutzer["rolle"] != "trainer":
        sid = benutzer.get("spieler_id")
        if not sid or not db.szene_clip_darf(conn, cid, sid):
            raise HTTPException(403, "Kein Zugriff auf diesen Clip")
    pfad = pfade.MEDIA_SZENEN / c["datei"]
    if not pfad.is_file():
        raise HTTPException(404, "Videodatei fehlt")
    return FileResponse(pfad, media_type="video/mp4")


@router.get("/api/analysen")
def api_analysen(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    if benutzer["rolle"] == "trainer":
        return db.analysen_liste(conn)
    # Jede Spielerin sieht jedes Spiel (auch wenn sie darin nicht vorkommt);
    # 'meine_events'/'meine_zuege' sagen, wie viele Szenen es fuer sie gibt.
    sid = benutzer.get("spieler_id")
    return db.analysen_liste(conn, sid, alle=True) if sid else []


@router.get("/api/analysen/{aid}")
def api_analyse(aid: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    a = db.analyse_nach_id(conn, aid)
    if a is None:
        raise HTTPException(404, "Analyse nicht gefunden")
    if benutzer["rolle"] == "trainer":
        return _analyse_ausgabe(conn, a, None)
    # Ereignisse und Spielzuege sind auf die EIGENEN gefiltert (leer, wenn sie
    # nicht vorkommt) - die Szenen anderer Spielerinnen stehen hier nie drin.
    # Ohne Spielerprofil NICHT filtern: spieler_id=None hiesse "alles" (Trainerblick).
    sid = benutzer.get("spieler_id")
    if sid is None:
        raise HTTPException(403, "Kein Spielerprofil zugeordnet")
    return _analyse_ausgabe(conn, a, sid)


@router.get("/api/analysen/{aid}/video")
def api_analyse_video_holen(aid: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    a = db.analyse_nach_id(conn, aid)
    if a is None or not a["datei"]:
        raise HTTPException(404, "Video nicht gefunden")
    # Das ganze Spielvideo ist fuer die ganze Mannschaft da (jedes Konto mit
    # Spielerprofil); die einzelnen Szenen-Clips bleiben auf Beteiligte beschraenkt.
    if benutzer["rolle"] != "trainer" and benutzer.get("spieler_id") is None:
        raise HTTPException(403, "Kein Spielerprofil zugeordnet")
    pfad = pfade.MEDIA_SPIELE / a["datei"]
    if not pfad.is_file():
        raise HTTPException(404, "Videodatei fehlt")
    return FileResponse(pfad, media_type="video/mp4")      # Range -> Seek im Player


@router.get("/api/spieler/{spieler_id}/analyse")
def api_spieler_analyse(spieler_id: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Alle Spielanalysen einer Spielerin: Statistik + ihre Zeitstempel."""
    trainer = benutzer["rolle"] == "trainer"
    if not trainer and benutzer.get("spieler_id") != spieler_id:
        raise HTTPException(403, "Nur das eigene Profil")
    return [_analyse_ausgabe(conn, db.analyse_nach_id(conn, x["id"]), spieler_id)
            for x in db.analysen_liste(conn, spieler_id)]


@router.post("/api/analysen/{aid}/loeschen")
def api_analyse_loeschen(aid: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    r = db.analyse_loeschen(conn, aid)
    if r is None:
        raise HTTPException(404, "Analyse nicht gefunden")
    datei, clips = r
    if datei:
        (pfade.MEDIA_SPIELE / datei).unlink(missing_ok=True)
    for c in clips:
        (pfade.MEDIA_SZENEN / c).unlink(missing_ok=True)
    return {"ok": True}
