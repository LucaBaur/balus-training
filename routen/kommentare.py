"""Fragen und Kommentare unter Videos (mit Push an die Gegenseite)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

import db

from .gemeinsam import _log, hole_conn, require_trainer, require_user


router = APIRouter()


# ------------------------------------------------------ Video-Kommentare ----
#  Fragen und Kommentare unter einem Video (Clip, Szene, ganzes Spiel). Wer das
#  Video sehen darf, darf auch kommentieren. "Nur Trainer" macht einen Kommentar
#  privat: sichtbar fuer Trainer und die Spielerin selbst (siehe db.kommentar_anlegen).

def _darf_video(conn, benutzer: dict, ziel: str) -> bool:
    art, _, nr = ziel.partition(":")
    if not nr.isdigit():
        return False
    nr = int(nr)
    trainer = benutzer["rolle"] == "trainer"
    sid = benutzer.get("spieler_id")
    if art == "clip":
        clip = db.clip_nach_id(conn, nr)
        return clip is not None and (trainer or (sid is not None and sid in clip["spieler_ids"]))
    if art == "szene":
        return (db.szene_clip_nach_id(conn, nr) is not None
                and (trainer or (sid is not None and db.szene_clip_darf(conn, nr, sid))))
    if art == "spiel":          # ganzes Spiel: fuer jedes Konto mit Spielerprofil
        return (conn.execute("SELECT 1 FROM spiel_analyse WHERE id = ?", (nr,)).fetchone()
                is not None and (trainer or sid is not None))
    return False


class KommentarNeu(BaseModel):
    ziel: str
    text: str
    nur_trainer: bool = False
    antwort_auf: int | None = None


def _kommentar_push(autor: dict, ziel: str, text: str, ergebnis: dict, titel: str) -> None:
    """Benachrichtigt im Hintergrund (eigene DB-Verbindung): Fragen der Spielerinnen gehen an die
    Trainer, Antworten der Trainer an den, auf dessen Kommentar geantwortet wurde."""
    import push
    conn = db.verbinde()
    try:
        if autor["rolle"] == "trainer":
            an = [ergebnis["eltern_benutzer"]] if ergebnis["eltern_benutzer"] else []
        else:
            an = db.trainer_benutzer_ids(conn)
        an = [b for b in an if b != autor["id"]]
        if an:
            kurz = text if len(text) <= 100 else text[:97] + "…"
            res = push.sende(conn, an, f"Video: {titel}"[:60], f"{autor['name']}: {kurz}", url="/",
                             art="rueckmeldungen")
            _log.info("Kommentar-Push %s -> Benutzer %s: %s", ziel, an, res)
        else:
            _log.info("Kommentar-Push %s: kein Empfaenger", ziel)
    except Exception:
        # Push ist Zugabe: der Kommentar ist da, auch wenn Push scheitert - aber im Log sichtbar.
        _log.exception("Kommentar-Push %s fehlgeschlagen", ziel)
    finally:
        conn.close()


@router.get("/api/kommentare")
def api_kommentare(ziel: str, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    if not _darf_video(conn, benutzer, ziel):
        raise HTTPException(403, "Kein Zugriff auf dieses Video")
    return db.kommentare_fuer(conn, ziel, benutzer)


@router.post("/api/kommentare")
def api_kommentar_neu(a: KommentarNeu, hintergrund: BackgroundTasks, conn=Depends(hole_conn),
                      benutzer=Depends(require_user)):
    if not _darf_video(conn, benutzer, a.ziel):
        raise HTTPException(403, "Kein Zugriff auf dieses Video")
    try:
        r = db.kommentar_anlegen(conn, a.ziel, benutzer, a.text, a.nur_trainer, a.antwort_auf)
    except ValueError as e:
        raise HTTPException(400, str(e))
    # Push nur an Betroffene (siehe _kommentar_push): ein Trainer-Kommentar ohne Bezug auf
    # einen anderen loest keinen aus, sonst bekaeme das ganze Team jeden.
    # Titel fuer den Push: der zuletzt gemeldete aus der Nutzung (der Titel steht nicht in einer eigenen Tabelle).
    titel =(conn.execute("SELECT info FROM nutzung WHERE ziel = ? AND info IS NOT NULL "
                          "ORDER BY id DESC LIMIT 1", (a.ziel,)).fetchone() or {"info": "Video"})["info"]
    hintergrund.add_task(_kommentar_push, benutzer, a.ziel, a.text.strip(), r, titel)
    return db.kommentare_fuer(conn, a.ziel, benutzer)


@router.get("/api/fragen-offen")
def api_fragen_offen(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """'Braucht dich': Videos mit Fragen/Kommentaren, auf die der Trainer noch nicht geantwortet hat."""
    return db.offene_fragen(conn)


@router.post("/api/kommentare/{kid}/loeschen")
def api_kommentar_loeschen(kid: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    if not db.kommentar_loeschen(conn, kid, benutzer):
        raise HTTPException(404, "Kommentar nicht gefunden oder nicht dein eigener")
    return {"ok": True}
