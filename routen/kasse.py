"""Mannschaftskasse (Amt Kassenwart): Kassenbuch ansehen, buchen, stornieren."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db

from .gemeinsam import _rechte, hole_conn, require_recht, require_user

router = APIRouter()

#  Lesen darf jede angemeldete Person, aber nur so viel, wie db.kasse_uebersicht freigibt: den
#  Kassenstand und die Buchungen der Kasse selbst, von Spielerinnen nur die eigenen Posten.
#  Buchen und Stornieren verlangt das Recht "kasse" (Amt Kassenwart oder Trainer). Im
#  "Ansicht als"-Modus sind schreibende Aufrufe ohnehin gesperrt (Middleware in app.py).


class Buchung(BaseModel):
    art: str
    betrag_cent: int
    text: str = ""
    spieler_id: int | None = None
    datum: str | None = None
    token: str | None = None


def _fehler(e: Exception) -> HTTPException:
    return HTTPException(404 if isinstance(e, LookupError) else 400, str(e.args[0] if e.args else e))


@router.get("/api/kasse")
def api_kasse(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    darf = "kasse" in _rechte(conn, benutzer)
    daten = db.kasse_uebersicht(conn, benutzer.get("spieler_id"), alle=darf)
    daten["darf_buchen"] = darf
    daten["katalog"] = db.kasse_katalog()          # die Regeln sind für alle offen; nur Buchende sehen das Formular
    if darf:
        daten["kader"] = [{"id": s["id"], "name": s["name"]} for s in db.aktive_spieler(conn)]
    return daten


@router.post("/api/kasse/buchung")
def api_kasse_buchen(b: Buchung, conn=Depends(hole_conn), benutzer=Depends(require_recht("kasse"))):
    try:
        buchung_id, neu = db.kasse_buchen(conn, b.art, b.betrag_cent, b.text, b.spieler_id, b.datum,
                                          benutzer["name"], b.token)
    except (ValueError, LookupError) as e:
        raise _fehler(e)
    return {"id": buchung_id, "neu": neu}


@router.post("/api/kasse/buchung/{buchung_id}/storno")
def api_kasse_storno(buchung_id: int, conn=Depends(hole_conn), benutzer=Depends(require_recht("kasse"))):
    try:
        neu = db.kasse_stornieren(conn, buchung_id, benutzer["name"])
    except (ValueError, LookupError) as e:
        raise _fehler(e)
    return {"ok": True, "neu": neu}
