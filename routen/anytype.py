"""Anytype-Anbindung: Import, Sync und Trainingsanlage."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db

from .gemeinsam import hole_conn, require_trainer


router = APIRouter()


@router.post("/api/anytype/import")
def api_anytype_import(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        import anytype_sync
        at = anytype_sync.get_client()
        res = db.import_kader(conn, anytype_sync.lade_kader(at))
    except Exception as e:  # requests-/Anytype-Fehler sauber ans Frontend
        raise HTTPException(502, f"Anytype-Import fehlgeschlagen: {e}")
    return res


@router.post("/api/anytype/sync")
def api_anytype_sync(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        import anytype_sync
        at = anytype_sync.get_client()
        key = anytype_sync.elo_key()
        paare = [(p["anytype_id"], p["elo"])
                 for p in db.rangliste(conn) if p.get("anytype_id")]
        n = anytype_sync.schreibe_elos(at, paare, key)
    except Exception as e:
        raise HTTPException(502, f"Anytype-Sync fehlgeschlagen: {e}")
    return {"geschrieben": n}


class AnytypeTraining(BaseModel):
    titel: str
    markdown: str
    datum: str | None = None        # ISO, z. B. 2026-07-05 (fuer neues Training)
    training_id: str | None = None  # bestehendes Training, an das angehaengt wird


@router.post("/api/trainer/anytype")
def api_trainer_anytype(t: AnytypeTraining, _t=Depends(require_trainer)):
    try:
        import anytype_sync
        at = anytype_sync.get_client()
        res = anytype_sync.training_plan_einfuegen(
            at, t.titel, t.markdown, training_id=t.training_id, datum=t.datum)
    except Exception as e:
        raise HTTPException(502, f"Anytype-Anlage fehlgeschlagen: {e}")
    return res
