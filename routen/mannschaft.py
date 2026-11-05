"""Aemter der Mannschaft: Listen, Zuteilung, Bussle."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

import aemter
import benachrichtigung
import db

from .gemeinsam import _push_hintergrund, hole_conn, require_trainer, require_user


router = APIRouter()


def _darf_amt_pflegen(conn, benutzer: dict, amt_id: int) -> bool:
    return benutzer["rolle"] == "trainer" or aemter.ist_inhaber(conn, amt_id, benutzer.get("spieler_id"))


# ------------------------------------------------------------------ Ämter ----
#  Ämter der Mannschaft (aemter.py). Lesen dürfen alle angemeldeten Benutzer: Wer das Amt hat und
#  wie oft jede dran war, soll für alle sichtbar sein (das ist der Sinn der Listen). Schreiben:
#  Ämter und Inhaberinnen nur der Trainer, die Liste eines Amts dessen Inhaberinnen (und der
#  Trainer). Alle Schreibaufrufe SETZEN einen Zustand (da: true/false) statt umzuschalten, darum
#  ist ein doppelt gesendeter Aufruf harmlos.

def _amt_fehler(e: Exception) -> HTTPException:
    return HTTPException(404 if isinstance(e, LookupError) else 400, str(e.args[0] if e.args else e))


class AmtNeu(BaseModel):
    name: str
    beschreibung: str = ""


class AmtBeschreibung(BaseModel):
    beschreibung: str = ""


class AmtInhaber(BaseModel):
    spieler_id: int
    da: bool


class AmtZuteilung(BaseModel):
    training_id: int
    spieler_id: int
    da: bool


class AmtErledigt(BaseModel):
    training_id: int
    spieler_id: int
    erledigt: bool


class AmtBussle(BaseModel):
    training_id: int
    status: str | None = None


@router.get("/api/aemter")
def api_aemter(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    kader = [{"id": s["id"], "name": s["name"]} for s in db.aktive_spieler(conn)]
    return {"aemter": aemter.alle(conn, benutzer.get("spieler_id"), benutzer["rolle"] == "trainer"),
            "kader": kader, "kann_verwalten": benutzer["rolle"] == "trainer"}


@router.get("/api/aemter/meine-aufgaben")
def api_amt_aufgaben(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    return {"aufgaben": aemter.aufgaben(conn, benutzer.get("spieler_id"))}


@router.post("/api/aemter")
def api_amt_neu(a: AmtNeu, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        return {"id": aemter.amt_anlegen(conn, a.name, a.beschreibung)}
    except (ValueError, LookupError) as e:
        raise _amt_fehler(e)


@router.post("/api/aemter/{amt_id}/beschreibung")
def api_amt_beschreibung(amt_id: int, a: AmtBeschreibung, conn=Depends(hole_conn),
                         _t=Depends(require_trainer)):
    try:
        aemter.beschreibung_setzen(conn, amt_id, a.beschreibung)
    except (ValueError, LookupError) as e:
        raise _amt_fehler(e)
    return {"ok": True}


@router.post("/api/aemter/{amt_id}/inhaber")
def api_amt_inhaber(amt_id: int, a: AmtInhaber, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        aemter.inhaber_setzen(conn, amt_id, a.spieler_id, a.da)
    except (ValueError, LookupError) as e:
        raise _amt_fehler(e)
    return {"ok": True}


@router.get("/api/aemter/{amt_id}/liste")
def api_amt_liste(amt_id: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    try:
        daten = aemter.liste(conn, amt_id)
    except (ValueError, LookupError) as e:
        raise _amt_fehler(e)
    daten["darf_pflegen"] = _darf_amt_pflegen(conn, benutzer, amt_id)
    return daten


def _pflege_pruefen(conn, benutzer: dict, amt_id: int) -> None:
    """Nur Inhaberin oder Trainer ändern die Liste. Ein unbekanntes Amt meldet 404 statt 403,
    sonst ließe sich die Antwort nicht von "darf ich nicht" unterscheiden."""
    try:
        aemter.amt_holen(conn, amt_id)
    except LookupError as e:
        raise _amt_fehler(e)
    if not _darf_amt_pflegen(conn, benutzer, amt_id):
        raise HTTPException(403, "Diese Liste pflegt nur, wer das Amt hat.")


@router.post("/api/aemter/{amt_id}/zuteilung")
def api_amt_zuteilung(amt_id: int, a: AmtZuteilung, hintergrund: BackgroundTasks,
                      conn=Depends(hole_conn), benutzer=Depends(require_user)):
    _pflege_pruefen(conn, benutzer, amt_id)
    try:
        neu = aemter.zuteilung_setzen(conn, amt_id, a.training_id, a.spieler_id, a.da)
    except (ValueError, LookupError) as e:
        raise _amt_fehler(e)
    # Mitteilung nur, wenn die Zuteilung neu ist (ein wiederholter Aufruf klingelt nicht noch einmal)
    # und nicht, wenn jemand sich selbst einträgt.
    if neu and a.spieler_id != benutzer.get("spieler_id"):
        hintergrund.add_task(_push_hintergrund, benachrichtigung.amt_zugeteilt, amt_id, a.training_id, a.spieler_id)
    return {"ok": True}


@router.post("/api/aemter/{amt_id}/erledigt")
def api_amt_erledigt(amt_id: int, a: AmtErledigt, conn=Depends(hole_conn),
                     benutzer=Depends(require_user)):
    _pflege_pruefen(conn, benutzer, amt_id)
    try:
        aemter.erledigt_setzen(conn, amt_id, a.training_id, a.spieler_id, a.erledigt)
    except (ValueError, LookupError) as e:
        raise _amt_fehler(e)
    return {"ok": True}


@router.post("/api/aemter/{amt_id}/bussle")
def api_amt_bussle(amt_id: int, a: AmtBussle, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    _pflege_pruefen(conn, benutzer, amt_id)
    try:
        aemter.bussle_setzen(conn, amt_id, a.training_id, a.status)
    except (ValueError, LookupError) as e:
        raise _amt_fehler(e)
    return {"ok": True}
