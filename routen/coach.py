"""Coach-Chat: Text, Sprachnachricht, Planvorschlag."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

import db
import trainer

from .gemeinsam import hole_conn, require_trainer


router = APIRouter()


# ------------------------------------------------------------------- PWA -----

class ChatAnfrage(BaseModel):
    verlauf: list[dict]            # [{role, content}, ...] ohne System-Prompt


class ChatNachricht(BaseModel):
    rolle: str                      # user / bot / info / plan
    text: str
    roh: str | None = None
    titel: str | None = None


@router.get("/api/chat")
def api_chat(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    return db.chat_verlauf(conn)


@router.post("/api/chat")
def api_chat_anhaengen(m: ChatNachricht, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    if m.rolle not in ("user", "bot", "info", "plan"):
        raise HTTPException(400, "Ungültige Rolle.")
    return db.chat_anhaengen(conn, m.rolle, m.text, roh=m.roh, titel=m.titel)


@router.post("/api/chat/loeschen")
def api_chat_loeschen(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    db.chat_leeren(conn)
    return {"ok": True}


@router.post("/api/trainer/chat")
def api_trainer_chat(a: ChatAnfrage, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    kontext = None
    warnung = None
    try:
        info = db.kader_info(conn)          # nativ aus SQLite (kein Anytype mehr)
        kontext = (f"{info['anzahl']} Spielerinnen, davon {info['torhueter']} "
                   f"Torhueterin(nen) (Quelle: {info['quelle']}).")
        if info["torhueter"] == 0:
            warnung = "⚠️ Keine Torhüterin dabei – Torhüter-Einwerfen anpassen / Ersatz organisieren."
        elif info["torhueter"] == 1:
            warnung = "⚠️ Nur 1 Torhüterin dabei – beim Torhüter-Einwerfen berücksichtigen."
    except Exception:
        pass  # ohne Kaderzahl trotzdem generieren
    try:
        erg, roh, modell = trainer.generiere(a.verlauf, kontext=kontext)
    except Exception as e:
        raise HTTPException(502, f"Generierung fehlgeschlagen: {e}")
    erg["modell"] = modell
    erg["roh"] = roh
    if warnung and erg.get("typ") == "plan":
        erg["warnung"] = warnung
    return erg


@router.post("/api/trainer/audio")
async def api_trainer_audio(datei: UploadFile = File(...), _t=Depends(require_trainer)):
    data = await datei.read()
    try:
        text = trainer.transkribiere(data, datei.filename or "audio.webm")
    except Exception as e:
        raise HTTPException(502, f"Transkription fehlgeschlagen: {e}")
    return {"text": text}
