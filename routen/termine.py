"""Termine: Training, Test- und Ligaspiele, Plan, Nachbereitung, Zu- und Absagen."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import benachrichtigung
import db
import trainer

from .gemeinsam import _push_hintergrund, hole_conn, require_recht, require_trainer, require_user


router = APIRouter()


_WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _training_label(datum_iso: str) -> str:
    d = date.fromisoformat(datum_iso)
    delta = (d - date.today()).days
    if delta == 0:
        praefix = "heute"
    elif delta == 1:
        praefix = "morgen"
    elif delta == -1:
        praefix = "gestern"
    else:
        praefix = _WOCHENTAGE[d.weekday()]
    return f"{praefix} {d.strftime('%d.%m.')}"


@router.get("/api/einteilung/trainings")
def api_einteilung_trainings(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Trainings der naechsten Tage mit den Zusagen aus der App-Datenbank. Die Team-
    Einteilung uebernimmt daraus die Anwesenden (frueher aus Anytype geholt)."""
    result = []
    for t in db.einteilung_trainings(conn):
        t["label"] = _training_label(t["datum"])
        result.append(t)
    return result


@router.get("/api/trainings")
def api_trainings(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Native Trainingsliste (SQLite). Enthaelt fuer Spielerinnen die eigene
    Antwort (`meine_status`) je Training -> Frontend faerbt Absagen."""
    result = []
    for t in db.trainings_liste(conn, benutzer.get("spieler_id")):
        try:
            t["label"] = _training_label(t["datum"]) if t.get("datum") else ""
        except ValueError:
            t["label"] = t.get("datum", "")
        result.append(t)
    if benutzer["rolle"] == "trainer":      # nur der Merker, nie der Inhalt (die Liste geht an alle)
        mit = db.nachbereitung_ids(conn)
        for t in result:
            t["hat_nachbereitung"] = 1 if t["id"] in mit else 0
    return result


def _ohne_plan(d: dict) -> dict:
    """Trainingsplan aus der Antwort entfernen. Der Plan ist Trainer-Sache -
    und zwar hier, nicht erst im Frontend: sonst stuende er trotzdem in der
    JSON-Antwort, die jede angemeldete Spielerin abrufen kann."""
    d = dict(d)
    d.pop("plan_markdown", None)
    d.pop("inhalt", None)
    d["bloecke"] = []
    return d


@router.get("/api/trainings/{tid}")
def api_training_detail(tid: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    d = db.training_detail(conn, tid)
    if d is None:
        raise HTTPException(404, "Training nicht gefunden")
    return d if benutzer["rolle"] == "trainer" else _ohne_plan(d)


class TrainingPlan(BaseModel):
    markdown: str = ""
    token: str | None = None       # Idempotenz-Token der Outbox (hier ignoriert)


@router.post("/api/trainings/{tid}/plan")
def api_training_plan(tid: int, p: TrainingPlan, conn=Depends(hole_conn),
                      _t=Depends(require_trainer)):
    """Trainingsplan nativ setzen (löst die Anytype-Body-Anlage ab). Idempotent:
    reine Zuweisung -> mehrfaches Senden (Outbox) ist unschädlich."""
    if not db.training_plan_setzen(conn, tid, p.markdown):
        raise HTTPException(404, "Training nicht gefunden")
    # Coach-Plaene sollen direkt im Block-Editor landen. Nur wenn noch keine
    # Bloecke da sind - ein von Hand gebauter Plan wird NICHT ueberschrieben.
    if not db.plan_bloecke(conn, tid):
        try:
            b = trainer.bloecke_aus_markdown(p.markdown or "")
            if b:
                db.plan_bloecke_setzen(conn, tid, b)
        except Exception:
            pass          # der Plantext ist gespeichert; die Bloecke sind Zugabe
    return {"ok": True}


class PlanBlock(BaseModel):
    dauer_min: int | None = None   # optional: nicht jeder Block braucht Minuten
    titel: str = ""
    notiz: str | None = None


class PlanBloecke(BaseModel):
    bloecke: list[PlanBlock] = []
    token: str | None = None       # Outbox-Idempotenz (hier nicht noetig)


@router.post("/api/trainings/{tid}/blocks")
def api_training_blocks(tid: int, p: PlanBloecke, conn=Depends(hole_conn),
                        _t=Depends(require_trainer)):
    """Trainingsplan als Bloecke setzen - NUR Trainer/Admin. Die Liste ersetzt
    den bisherigen Plan komplett, damit ein wiederholtes Senden nichts
    verdoppelt."""
    if conn.execute("SELECT 1 FROM trainings WHERE id = ?", (tid,)).fetchone() is None:
        raise HTTPException(404, "Training nicht gefunden")
    anzahl = db.plan_bloecke_setzen(
        conn, tid,
        [{"dauer_min": b.dauer_min, "titel": b.titel, "notiz": b.notiz} for b in p.bloecke],
    )
    return {"ok": True, "anzahl": anzahl}


@router.post("/api/trainings/{tid}/blocks/aus-text")
def api_training_blocks_aus_text(tid: int, conn=Depends(hole_conn),
                                 _t=Depends(require_trainer)):
    """Aus dem alten Plantext Bloecke machen (jede Ueberschrift ein Block).
    Fuer die Plaene, die vor der Umstellung als ein Textfeld entstanden sind."""
    row = conn.execute("SELECT plan_markdown, inhalt FROM trainings WHERE id = ?",
                       (tid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Training nicht gefunden")
    text = (row["plan_markdown"] or "").strip() or (row["inhalt"] or "")
    bloecke = trainer.bloecke_aus_markdown(text)
    if not bloecke:
        raise HTTPException(400, "In diesem Plan steht kein Text, aus dem sich Blöcke bilden lassen.")
    db.plan_bloecke_setzen(conn, tid, bloecke)
    return {"ok": True, "bloecke": db.plan_bloecke(conn, tid)}


class TrainingNeu(BaseModel):
    datum: str                     # ISO 'YYYY-MM-DD'
    titel: str = ""
    uhrzeit: str | None = None     # 'HH:MM' (bei Spielen: Anwurf)
    ort: str | None = None
    markdown: str = ""             # optionaler Plan
    art: str = "training"          # training / testspiel / ligaspiel
    gegner: str | None = None      # nur Spiele
    heim: bool | None = None       # True = Heimspiel, False = auswaerts
    abfahrt: str | None = None     # 'HH:MM' Abfahrt (Auswaertsspiele)
    token: str | None = None


def _spiel_titel(art: str, gegner: str | None, heim: bool | None) -> str:
    """Titel eines Spiels aus Art, Gegner und Heimrecht - damit in der Liste
    ohne Aufklappen steht, worum es geht."""
    wort = "Testspiel" if art == "testspiel" else "Ligaspiel"
    if not gegner:
        return wort
    return f"{wort} {'gegen' if heim else 'bei'} {gegner}"


@router.post("/api/trainings")
def api_training_anlegen(t: TrainingNeu, conn=Depends(hole_conn),
                         _t=Depends(require_recht("termine"))):
    """Termin anlegen: Training (bestehendes am Datum wird wiederverwendet)
    oder Test-/Ligaspiel mit Gegner, Heimrecht und Abfahrtszeit.
    Ersetzt die Anytype-Neuanlage. Trainer oder Amt "Balu-Trainings-App"."""
    if not t.datum.strip():
        raise HTTPException(400, "Datum fehlt")
    art = t.art if t.art in db.ARTEN else "training"
    gegner = (t.gegner or "").strip() or None
    if art in db.SPIEL_ARTEN and not gegner:
        raise HTTPException(400, "Für ein Spiel fehlt der Gegner.")
    heim = None if art == "training" else bool(t.heim)
    # Abfahrt ergibt nur auswaerts Sinn - daheim faehrt niemand gemeinsam los.
    abfahrt = (t.abfahrt or None) if (art in db.SPIEL_ARTEN and heim is False) else None
    titel = t.titel.strip() if t.titel else ""
    if not titel:
        titel = _spiel_titel(art, gegner, heim) if art in db.SPIEL_ARTEN else "Training"
    tid, neu = db.training_anlegen(conn, t.datum.strip(), titel,
                                   t.markdown or None,
                                   uhrzeit=(t.uhrzeit or None), ort=(t.ort or None),
                                   art=art, gegner=gegner,
                                   heim=(None if heim is None else int(heim)),
                                   abfahrt=abfahrt)
    return {"id": tid, "neu": neu}


@router.post("/api/trainings/{tid}/loeschen")
def api_training_loeschen(tid: int, hintergrund: BackgroundTasks, conn=Depends(hole_conn),
                          _t=Depends(require_recht("termine"))):
    """Training loeschen - Trainer oder Amt "Balu-Trainings-App". Idempotent: ist der Termin schon
    weg, gilt der Aufruf trotzdem als erfolgreich, damit ein wiederholter
    Versuch (Outbox, Doppeltipp) keinen Fehler wirft. Wer zugesagt hatte, bekommt
    eine Push-Nachricht (nur beim ersten, echten Löschen)."""
    stand = db.training_detail(conn, tid)        # vor dem Löschen: danach weiß niemand mehr, wer zugesagt hat
    weg = db.training_loeschen(conn, tid)
    if weg and stand:
        hintergrund.add_task(_push_hintergrund, benachrichtigung.termin_abgesagt, stand)
    return {"ok": True, "geloescht": weg}


# --- Spiel-Nachbereitung: NUR Trainer, nie in /api/trainings (db.nachbereitung_*) ---

class NachbereitungAnfrage(BaseModel):
    gedanken: str = ""
    gegner: str = ""
    ansprache: str = ""
    vorspiel_id: int | None = None
    basis: str | None = None       # 'geaendert_am' des geladenen Stands (Konflikterkennung)


@router.get("/api/trainings/{tid}/nachbereitung")
def api_nachbereitung(tid: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    d = db.nachbereitung_holen(conn, tid)
    if d is None:
        raise HTTPException(404, "Spiel nicht gefunden")
    return d


@router.post("/api/trainings/{tid}/nachbereitung")
def api_nachbereitung_speichern(tid: int, a: NachbereitungAnfrage, conn=Depends(hole_conn),
                                trainer=Depends(require_trainer)):
    try:
        d = db.nachbereitung_speichern(conn, tid, trainer["name"], a.gedanken, a.gegner,
                                       a.ansprache, a.vorspiel_id, a.basis)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except db.NachbereitungKonflikt as k:
        return JSONResponse(status_code=409, content={"fehler": "konflikt", "aktuell": k.aktuell})
    if d is None:
        raise HTTPException(404, "Spiel nicht gefunden")
    return d


class TeilnahmeAnfrage(BaseModel):
    status: str                    # anwesend / abgesagt / unsicher
    grund: str | None = None       # Pflicht bei 'abgesagt'
    token: str | None = None       # Outbox-Idempotenz (hier ignoriert)


@router.post("/api/trainings/{tid}/teilnahme")
def api_teilnahme(tid: int, a: TeilnahmeAnfrage, hintergrund: BackgroundTasks,
                  conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Eigene Zu-/Absage setzen. Die Spielerin wird aus der Session abgeleitet
    (nie aus dem Body) -> man kann nur fuer SICH antworten."""
    sid = benutzer.get("spieler_id")
    if not sid:
        raise HTTPException(403, "Dein Konto ist mit keiner Spielerin verknüpft.")
    if not db.ist_im_kader(conn, sid):
        raise HTTPException(403, "Du gehörst nicht zum aktuellen Kader, darum gibt es für dich keine Zu-/Absage.")
    if a.status not in ("anwesend", "abgesagt", "unsicher"):
        raise HTTPException(400, "Ungültiger Status.")
    grund = (a.grund or "").strip() or None
    if a.status == "abgesagt" and not grund:
        raise HTTPException(400, "Bei einer Absage bitte einen Grund angeben.")
    if conn.execute("SELECT 1 FROM trainings WHERE id = ?", (tid,)).fetchone() is None:
        raise HTTPException(404, "Training nicht gefunden")
    vorher = db.zusagen_anzahl(conn, tid)
    db.teilnahme_setzen(conn, tid, sid, a.status, grund, quelle="app")
    hintergrund.add_task(_push_hintergrund, benachrichtigung.zusagen_pruefen, tid, vorher)
    return {"ok": True, "status": a.status, "grund": grund}


class TeilnahmeFremdAnfrage(BaseModel):
    status: str                    # anwesend / abgesagt / unsicher / offen
    grund: str | None = None       # optional - der Trainer weiss ihn oft schon
    token: str | None = None       # Outbox-Idempotenz (hier ignoriert)


@router.post("/api/trainings/{tid}/teilnahme/{spieler_id}")
def api_teilnahme_fremd(tid: int, spieler_id: int, a: TeilnahmeFremdAnfrage,
                        hintergrund: BackgroundTasks, conn=Depends(hole_conn),
                        _t=Depends(require_trainer)):
    """Trainer traegt die Antwort FUER eine Spielerin ein (Anruf, WhatsApp,
    Absage am Hallenrand).

    Zwei bewusste Unterschiede zur eigenen Antwort oben:
    - Der Grund ist hier NICHT Pflicht. Beim Eintragen fuer andere kennt man
      ihn oft nicht genau, und eine Pflichteingabe wuerde nur Phantasie-Gruende
      erzeugen.
    - `status = "offen"` loescht die Antwort wieder (Korrektur bei Vertippen).
    Die Quelle wird als 'trainer' vermerkt - so bleibt unterscheidbar, wer
    geantwortet hat und wer eingetragen wurde. Die Push-Erinnerung geht weiter
    an alle ohne EIGENE Antwort (quelle != 'app').
    """
    if a.status not in ("anwesend", "abgesagt", "unsicher", "offen"):
        raise HTTPException(400, "Ungültiger Status.")
    if conn.execute("SELECT 1 FROM trainings WHERE id = ?", (tid,)).fetchone() is None:
        raise HTTPException(404, "Training nicht gefunden")
    if conn.execute("SELECT 1 FROM spieler WHERE id = ?", (spieler_id,)).fetchone() is None:
        raise HTTPException(404, "Spielerin nicht gefunden")
    vorher = db.zusagen_anzahl(conn, tid)
    if a.status == "offen":
        db.teilnahme_loeschen(conn, tid, spieler_id)
        hintergrund.add_task(_push_hintergrund, benachrichtigung.zusagen_pruefen, tid, vorher)
        return {"ok": True, "status": None, "grund": None}
    grund = (a.grund or "").strip() or None
    db.teilnahme_setzen(conn, tid, spieler_id, a.status, grund, quelle="trainer")
    hintergrund.add_task(_push_hintergrund, benachrichtigung.zusagen_pruefen, tid, vorher)
    return {"ok": True, "status": a.status, "grund": grund}


@router.post("/api/trainings/{tid}/erinnern")
def api_erinnern(tid: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Trainer schickt eine Push-Erinnerung an alle Spielerinnen, die fuer
    dieses Training noch nicht in der App geantwortet haben."""
    import push
    t = db.training_detail(conn, tid)
    if t is None:
        raise HTTPException(404, "Training nicht gefunden")
    offen = db.offene_spieler_benutzer(conn, tid)
    label = t.get("titel") or (t.get("datum") or "Training")
    res = push.sende(conn, offen, "Training – bitte zu-/absagen",
                     f"{label}: Bitte in der App zu- oder absagen.", url="/", art="termine")
    return {"offen": len(offen), **res}


@router.get("/api/naechstes-training")
def api_naechstes_training(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Fuer den Home-Screen: naechstes Training ab heute (oder null).
    Der Plan geht nur an Trainer - wie beim Trainings-Detail."""
    d = db.naechstes_training(conn)
    if d is None:
        return None
    return d if benutzer["rolle"] == "trainer" else _ohne_plan(d)
