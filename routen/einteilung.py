"""ELO-Teams: bilden, Spiel eintragen, korrigieren, Rangliste."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db
import elo
import teams

from .gemeinsam import hole_conn, require_trainer


router = APIRouter()


class TeamsAnfrage(BaseModel):
    anwesend: list[int]
    anzahl: int = 2                # 2 bis 4 Teams


class SpielAnfrage(BaseModel):
    teams: list[list[int]] | None = None   # 2 bis 4 Teams (neu)
    team_a: list[int] = []                 # Altform, weiter erlaubt
    team_b: list[int] = []
    ergebnis: str                  # Buchstabe des Siegerteams (A-D) oder U
    token: str | None = None       # Idempotenz-Schluessel (einmalig je Spiel)


@router.post("/api/teams")
def api_teams(anfrage: TeamsAnfrage, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Faire Aufteilung in zwei bis vier Teams. Antwortet mit `teams` (Liste)
    und - fuer zwei Teams - zusaetzlich mit den alten Schluesseln."""
    spieler = db.spieler_nach_ids(conn, anfrage.anwesend)
    anzahl = max(2, min(anfrage.anzahl or 2, elo.MAX_TEAMS))
    if len(spieler) < anzahl * 1:
        raise HTTPException(400, "Zu wenige Spielerinnen für so viele Teams.")
    if len(spieler) < 2:
        raise HTTPException(400, "Mindestens zwei Spielerinnen auswaehlen.")
    gruppen = teams.teams_generieren_n(spieler, anzahl)
    antwort = {
        "teams": gruppen,
        "schnitte": [round(sum(p["elo"] for p in t) / len(t)) if t else 0 for t in gruppen],
    }
    if len(gruppen) == 2:
        antwort.update({
            "team_a": gruppen[0], "team_b": gruppen[1],
            "schnitt_a": antwort["schnitte"][0], "schnitt_b": antwort["schnitte"][1],
        })
    return antwort


@router.post("/api/spiel")
def api_spiel(anfrage: SpielAnfrage, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Ergebnis eintragen. Neu: `teams` als Liste von Listen (2-4 Teams) und
    `ergebnis` als Buchstabe des Siegerteams (A-D) oder 'U'. Die alten Felder
    team_a/team_b werden weiter angenommen."""
    gruppen = anfrage.teams or (
        [anfrage.team_a, anfrage.team_b] if anfrage.team_a and anfrage.team_b else []
    )
    if len(gruppen) < 2 or any(not t for t in gruppen):
        raise HTTPException(400, "Jedes Team braucht Spielerinnen.")
    if len(gruppen) > elo.MAX_TEAMS:
        raise HTTPException(400, f"Höchstens {elo.MAX_TEAMS} Teams.")
    erlaubt = ("U",) + tuple(elo.BUCHSTABEN[:len(gruppen)])
    if anfrage.ergebnis not in erlaubt:
        raise HTTPException(400, f"Ergebnis muss eines von {list(erlaubt)} sein.")
    deltas, neu = db.spiel_eintragen_n(
        conn, gruppen, anfrage.ergebnis, token=anfrage.token
    )
    return {
        "deltas": {str(k): v for k, v in deltas.items()},
        "rangliste": db.rangliste(conn),
        "neu": neu,
    }


@router.post("/api/undo")
def api_undo(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    ok = db.letztes_spiel_ruecknehmen(conn)
    return {"ok": ok, "rangliste": db.rangliste(conn)}


class SpielKorrektur(BaseModel):
    ergebnis: str                  # A-D (Siegerteam) oder U


@router.post("/api/spiel/{spiel_id}/aendern")
def api_spiel_aendern(spiel_id: int, k: SpielKorrektur, conn=Depends(hole_conn),
                      _t=Depends(require_trainer)):
    try:
        if not db.spiel_aendern(conn, spiel_id, k.ergebnis):
            raise HTTPException(404, "Spiel nicht gefunden")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "rangliste": db.rangliste(conn)}


@router.post("/api/spiel/{spiel_id}/loeschen")
def api_spiel_loeschen(spiel_id: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    if not db.spiel_loeschen(conn, spiel_id):
        raise HTTPException(404, "Spiel nicht gefunden")
    return {"ok": True, "rangliste": db.rangliste(conn)}


@router.get("/api/rangliste")
def api_rangliste(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    return db.rangliste(conn)
