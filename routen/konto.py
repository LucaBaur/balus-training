"""Anmeldung, Abmeldung, /api/me und "Ansehen als"."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

import aemter
import auth
import db

from .gemeinsam import _rechte, hole_conn, require_echter_trainer, require_user


router = APIRouter()


class LoginAnfrage(BaseModel):
    name: str
    pin: str


def _cookie_setzen(resp: Response, token: str) -> None:
    # HttpOnly + SameSite=Lax. Secure bewusst NICHT gesetzt, damit der Zugriff
    # ueber das LAN (http://192.168.x:8200) nicht bricht; ueber Funnel/Tailscale
    # laeuft der Transport ohnehin per HTTPS.
    resp.set_cookie(auth.COOKIE_NAME, token, max_age=60 * 24 * 3600,
                    httponly=True, samesite="lax", path="/")


# Brute-Force-Schutz: nach 3 falschen Versuchen je Name wird die PIN GESPERRT
# (pin_hash -> NULL). Danach kein Login mehr moeglich, bis der Trainer eine neue
# PIN setzt. Macht Raten sinnlos (nur 3 Versuche pro Konto, dann Schluss).
_LOGIN_MAX_FEHLER = 3


@router.post("/api/login")
def api_login(anfrage: LoginAnfrage, resp: Response, conn=Depends(hole_conn)):
    name = anfrage.name.strip()
    b = db.benutzer_nach_name(conn, name)
    if b is None:
        # Unbekannter Name: gleiche Meldung wie falsche PIN (nichts verraten).
        raise HTTPException(401, "Name oder PIN falsch")
    if not b.get("pin_hash"):
        raise HTTPException(403, "PIN gesperrt – bitte beim Trainer eine neue holen.")
    if auth.pruefe_pin(anfrage.pin, b["pin_hash"]):
        db.benutzer_login_ok(conn, b["id"])          # Zaehler zuruecksetzen
        _cookie_setzen(resp, auth.session_erstellen(b["id"]))
        # Dieselben Felder wie /api/me - sonst fehlt nach dem Login die
        # spieler_id und damit der "Ich"-Reiter, bis die App neu geladen wird.
        return _me(b, conn)
    # Falsche PIN -> zaehlen; beim 3. Mal sperren.
    anzahl = db.benutzer_fehlversuch(conn, b["id"])
    if anzahl >= _LOGIN_MAX_FEHLER:
        db.benutzer_pin_sperren(conn, b["id"])
        raise HTTPException(403, "3 Fehlversuche – PIN gesperrt. Bitte beim Trainer "
                                 "eine neue PIN holen.")
    uebrig = _LOGIN_MAX_FEHLER - anzahl
    raise HTTPException(401, f"Name oder PIN falsch – noch {uebrig} Versuch(e), "
                            f"dann wird die PIN gesperrt.")


@router.post("/api/logout")
def api_logout(resp: Response):
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


def _me(benutzer: dict, conn=None) -> dict:
    ansicht = bool(benutzer.get("_ansicht_als"))
    me = {
        "name": benutzer["name"], "rolle": benutzer["rolle"],
        "spieler_id": benutzer.get("spieler_id"),
        "ansicht_als": ansicht,
        "echter_name": benutzer.get("_echter_name"),
        "als_benutzer_id": benutzer["id"] if ansicht else None,
    }
    if conn is not None:        # Ämter und Rechte: das Frontend blendet damit nur Knöpfe ein, der Server prüft selbst
        me["aemter"] = aemter.meine_aemter(conn, benutzer.get("spieler_id"))
        me["rechte"] = sorted(_rechte(conn, benutzer))
    return me


@router.get("/api/me")
def api_me(benutzer=Depends(require_user), conn=Depends(hole_conn)):
    return _me(benutzer, conn)


# --------------------------------------------------------------- Ansicht als ----
#  Ein Trainer kann die App aus Sicht einer Spielerin ansehen ("view as").
#  Das Ziel steht im signierten Cookie (Feld 'als'); nur ein ECHTER Trainer kann
#  es setzen. Der Modus ist nur lesend (siehe Middleware 'ansicht_nur_lesen').

@router.get("/api/ansicht/konten")
def api_ansicht_konten(conn=Depends(hole_conn), _t=Depends(require_echter_trainer)):
    return [{"benutzer_id": b["id"], "name": b["name"]}
            for b in db.benutzer_liste(conn)
            if b["rolle"] == "spieler" and b["aktiv"]]


@router.post("/api/ansicht/stop")
def api_ansicht_stop(resp: Response, conn=Depends(hole_conn), trainer=Depends(require_echter_trainer)):
    _cookie_setzen(resp, auth.session_erstellen(trainer["id"]))
    return _me(trainer, conn)


@router.post("/api/ansicht/{benutzer_id}")
def api_ansicht_setzen(benutzer_id: int, resp: Response, conn=Depends(hole_conn),
                       trainer=Depends(require_echter_trainer)):
    ziel = db.benutzer_nach_id(conn, benutzer_id)
    if ziel is None or ziel["rolle"] != "spieler":
        raise HTTPException(404, "Kein Spielerinnen-Konto mit dieser ID")
    _cookie_setzen(resp, auth.session_erstellen(trainer["id"], als=benutzer_id))
    return _me({**ziel, "_ansicht_als": True, "_echter_name": trainer["name"]}, conn)
