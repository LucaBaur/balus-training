"""Nutzungsdaten, Geraete- und Fehlermeldungen, Spielzug-Uebersicht fuer Trainer."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import db

from .gemeinsam import hole_conn, require_trainer, require_user


router = APIRouter()


# ---------------------------------------------------------------- Nutzung ----
#  Die App meldet Besuche, geoeffnete Bereiche und angesehene Videos; die
#  Trainer-Seite "Team -> Nutzung" wertet sie aus. Im "Ansicht als"-Modus sind
#  schreibende Aufrufe gesperrt (Middleware) - der Trainer zaehlt dort nicht mit.

class NutzungEreignis(BaseModel):
    typ: str
    ziel: str | None = None
    info: str | None = None
    dauer_s: float | None = None        # nur bei typ "verweil"; float, damit ein Dezimalwert nicht den ganzen Stapel kippt


class NutzungAnfrage(BaseModel):
    ereignisse: list[NutzungEreignis]


@router.post("/api/nutzung")
def api_nutzung_melden(a: NutzungAnfrage, conn=Depends(hole_conn),
                       benutzer=Depends(require_user)):
    n = db.nutzung_speichern(conn, benutzer["id"], [e.model_dump() for e in a.ereignisse])
    return {"ok": True, "gespeichert": n}


@router.get("/api/nutzung")
def api_nutzung(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    return db.nutzung_auswertung(conn)


@router.get("/api/szenen-uebersicht")
def api_szenen_uebersicht(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Team -> Videos (Trainer): alle Szenen je Spiel mit ID und 'wer hat sie komplett gesehen'."""
    return db.szenen_uebersicht(conn)


class GeraetAnfrage(BaseModel):
    os: str | None = None
    browser: str | None = None
    modus: str | None = None
    bildschirm: str | None = None
    modell: str | None = None
    app_version: str | None = None
    sw: bool = False


@router.post("/api/geraet")
def api_geraet_melden(g: GeraetAnfrage, conn=Depends(hole_conn),
                      benutzer=Depends(require_user)):
    db.geraet_speichern(conn, benutzer["id"], g.model_dump())
    return {"ok": True}


class FehlerAnfrage(BaseModel):
    quelle: str | None = None
    meldung: str
    ort: str | None = None
    app_version: str | None = None
    geraet: str | None = None


@router.post("/api/fehler")
def api_fehler_melden(f: FehlerAnfrage, conn=Depends(hole_conn),
                      benutzer=Depends(require_user)):
    return {"ok": db.fehler_speichern(conn, benutzer["id"], f.model_dump())}
