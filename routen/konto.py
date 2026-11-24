"""Anmeldung, Abmeldung, /api/me und "Ansehen als"."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import aemter
import auth
import db

from .gemeinsam import STANDARD_TEAM, _rechte, echter_benutzer, hole_conn, require_echter_trainer, require_user


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


# Schutz vor Raten: zu viele FEHLversuche bedeuten eine Wartezeit, nie eine dauerhafte Sperre
# (Regeln und Begruendung in daten/login.py). Die PIN bleibt immer erhalten, sonst koennte jeder,
# der nur einen Namen kennt, das Konto aussperren.
_jetzt = time.time        # Uhr; Tests tauschen sie aus


def _minuten(sekunden: int) -> int:
    return max(1, -(-sekunden // 60))


@router.post("/api/login")
def api_login(anfrage: LoginAnfrage, request: Request, resp: Response, conn=Depends(hole_conn)):
    name = anfrage.name.strip()
    ip = db.client_ip(request.client.host if request.client else None, request.headers.get("x-forwarded-for"))
    jetzt = _jetzt()
    # Zuerst die Wartezeit: gesperrte Anfragen kosten fast nichts (kein PIN-Hash) und zaehlen nicht mit,
    # Dauerhaemmern verlaengert die Pause also nicht.
    warte = db.login_wartezeit(conn, STANDARD_TEAM, ip, name, jetzt)
    if warte > 0:
        m = _minuten(warte)
        raise HTTPException(429, f"Zu viele Versuche. Bitte in {m} Minute{'n' if m != 1 else ''} noch einmal probieren.",
                            headers={"Retry-After": str(warte)})
    b = db.benutzer_nach_name(conn, name)
    if b is not None and not b.get("pin_hash"):
        raise HTTPException(403, "PIN gesperrt – bitte beim Trainer eine neue holen.")
    if b is not None and auth.pruefe_pin(anfrage.pin, b["pin_hash"]):
        _cookie_setzen(resp, auth.session_erstellen(b["id"], version=b.get("sitzung_version") or 0))
        # Dieselben Felder wie /api/me - sonst fehlt nach dem Login die
        # spieler_id und damit der "Ich"-Reiter, bis die App neu geladen wird.
        return _me(b, conn)
    # Falscher Name oder falsche PIN: dieselbe Antwort (nichts verraten) und derselbe Zaehler.
    db.login_fehlschlag(conn, STANDARD_TEAM, ip, name, jetzt)
    uebrig = db.login_versuche_uebrig(conn, STANDARD_TEAM, ip, name, jetzt)
    if uebrig == 0:
        raise HTTPException(401, "Name oder PIN falsch – bitte 15 Minuten warten, dann geht es weiter.")
    raise HTTPException(401, f"Name oder PIN falsch – noch {uebrig} Versuch(e), danach 15 Minuten Pause.")


@router.post("/api/logout")
def api_logout(resp: Response):
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@router.post("/api/logout-alle")
def api_logout_alle(resp: Response, conn=Depends(hole_conn), benutzer=Depends(echter_benutzer)):
    """Auf ALLEN Geraeten abmelden (verlorenes Handy, fremdes Geraet): zaehlt die Sitzungs-Version des Kontos
    hoch, dadurch ist jedes bisherige Cookie wertlos. Im "Ansicht als"-Modus sperrt die Nur-Lesen-Middleware
    diesen Aufruf, es trifft also nie das falsche Konto."""
    if not benutzer:
        raise HTTPException(401, "Nicht angemeldet")
    db.benutzer_sitzungen_beenden(conn, benutzer["id"])
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
        # False = Helferin (ehemalige Spielerin mit Konto): das Frontend blendet Zu-/Absage aus, der Server sperrt sie
        me["im_kader"] = db.ist_im_kader(conn, benutzer.get("spieler_id"))
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
    _cookie_setzen(resp, auth.session_erstellen(trainer["id"], version=trainer.get("sitzung_version") or 0))
    return _me(trainer, conn)


@router.post("/api/ansicht/{benutzer_id}")
def api_ansicht_setzen(benutzer_id: int, resp: Response, conn=Depends(hole_conn),
                       trainer=Depends(require_echter_trainer)):
    ziel = db.benutzer_nach_id(conn, benutzer_id)
    if ziel is None or ziel["rolle"] != "spieler":
        raise HTTPException(404, "Kein Spielerinnen-Konto mit dieser ID")
    _cookie_setzen(resp, auth.session_erstellen(trainer["id"], als=benutzer_id,
                                                version=trainer.get("sitzung_version") or 0))
    return _me({**ziel, "_ansicht_als": True, "_echter_name": trainer["name"]}, conn)
