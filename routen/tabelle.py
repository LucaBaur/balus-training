"""Liga: Tabelle und Spielplan vom Verband."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

import liga

from .gemeinsam import require_user


router = APIRouter()


# ------------------------------------------------------------------- Liga ----
#  Tabelle und Spielplan aus handball4all (dem Dienst hinter bwhv.org), siehe liga.py.
#  Fuer alle angemeldeten Konten lesbar; die Daten sind oeffentlich.

@router.get("/api/liga")
def api_liga(_b=Depends(require_user)):
    try:
        return liga.liga_daten()
    except Exception:
        raise HTTPException(503, "Die Liga-Daten sind gerade nicht erreichbar.")
