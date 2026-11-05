"""Web-Push: Abos, Einstellungen, Test."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db

from .gemeinsam import hole_conn, require_user


router = APIRouter()


# ------------------------------------------------------------- Web-Push ----

class PushAbo(BaseModel):
    endpoint: str
    keys: dict = {}                # {p256dh, auth}


@router.get("/api/push/vapid")
def api_push_vapid(_u=Depends(require_user)):
    import push
    return {"publicKey": push.public_key()}


@router.post("/api/push/subscribe")
def api_push_subscribe(a: PushAbo, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    keys = a.keys or {}
    if not a.endpoint or not keys.get("p256dh") or not keys.get("auth"):
        raise HTTPException(400, "Ungültiges Push-Abo")
    db.push_abo_speichern(conn, benutzer["id"], a.endpoint, keys["p256dh"], keys["auth"])
    return {"ok": True}


@router.post("/api/push/unsubscribe")
def api_push_unsubscribe(a: PushAbo, conn=Depends(hole_conn), _u=Depends(require_user)):
    if a.endpoint:
        db.push_abo_loeschen(conn, a.endpoint)
    return {"ok": True}


@router.get("/api/push/einstellungen")
def api_push_einstellungen(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Welche Arten von Mitteilungen diese Person bekommt (nur die für ihre Rolle)."""
    import push
    gespeichert = db.push_praeferenzen(conn, benutzer["id"])
    return {"arten": [{"key": a["key"], "label": a["label"], "text": a["text"],
                       "an": gespeichert.get(a["key"], True)}
                      for a in push.arten_fuer(benutzer["rolle"])]}


class PushEinstellung(BaseModel):
    art: str
    an: bool


@router.post("/api/push/einstellungen")
def api_push_einstellung_setzen(e: PushEinstellung, conn=Depends(hole_conn),
                                benutzer=Depends(require_user)):
    """Eine Art ein- oder ausschalten. Reine Zuweisung, also idempotent."""
    import push
    if e.art not in push.ART_KEYS:
        raise HTTPException(400, "Unbekannte Art von Mitteilung.")
    if e.art not in {a["key"] for a in push.arten_fuer(benutzer["rolle"])}:
        raise HTTPException(403, "Diese Mitteilung gibt es für dich nicht.")
    db.push_praeferenz_setzen(conn, benutzer["id"], e.art, e.an)
    return {"ok": True, "art": e.art, "an": e.an}


@router.post("/api/push/test")
def api_push_test(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Test-Push an die eigenen Geraete (zum Selbst-Pruefen der Zustellung)."""
    import push
    return push.sende(conn, [benutzer["id"]], "Balu's Training",
                      "Test-Benachrichtigung ✓ – Push funktioniert.", url="/")
