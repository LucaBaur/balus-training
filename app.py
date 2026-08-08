"""FastAPI-Backend fuer das ELO-System.

Liefert die PWA aus (statische Dateien) und stellt die JSON-Endpunkte bereit,
die das Frontend nutzt. Start:  uvicorn app:app --host 0.0.0.0 --port 8200
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import auth
import db
import elo
import teams
import trainer

BASIS = Path(__file__).parent
STATIC = BASIS / "static"

app = FastAPI(title="Balu's Training")


@app.middleware("http")
async def sw_kein_cache(request, call_next):
    resp = await call_next(request)
    if request.url.path == "/sw.js":
        resp.headers["Cache-Control"] = "no-cache"
    return resp

# Datenbank beim Start sicherstellen (Verbindung sofort schliessen, sonst
# bleibt die Datei gesperrt)
_c = db.verbinde()
db.init_db(_c)
_c.close()


def hole_conn():
    conn = db.verbinde()
    try:
        yield conn
    finally:
        conn.close()


# ------------------------------------------------------------------- Auth ----
#  Rollen werden SERVER-SEITIG erzwungen (nicht im UI). 'require_user' verlangt
#  ein gueltiges Session-Cookie, 'require_trainer' zusaetzlich die Trainer-Rolle.

def aktueller_benutzer(request: Request, conn=Depends(hole_conn)) -> dict | None:
    uid = auth.session_pruefen(request.cookies.get(auth.COOKIE_NAME))
    if uid is None:
        return None
    return db.benutzer_nach_id(conn, uid)


def require_user(benutzer=Depends(aktueller_benutzer)) -> dict:
    if not benutzer:
        raise HTTPException(401, "Nicht angemeldet")
    return benutzer


def require_trainer(benutzer=Depends(require_user)) -> dict:
    if benutzer["rolle"] != "trainer":
        raise HTTPException(403, "Nur für Trainer")
    return benutzer


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


@app.post("/api/login")
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
        return {"name": b["name"], "rolle": b["rolle"]}
    # Falsche PIN -> zaehlen; beim 3. Mal sperren.
    anzahl = db.benutzer_fehlversuch(conn, b["id"])
    if anzahl >= _LOGIN_MAX_FEHLER:
        db.benutzer_pin_sperren(conn, b["id"])
        raise HTTPException(403, "3 Fehlversuche – PIN gesperrt. Bitte beim Trainer "
                                 "eine neue PIN holen.")
    uebrig = _LOGIN_MAX_FEHLER - anzahl
    raise HTTPException(401, f"Name oder PIN falsch – noch {uebrig} Versuch(e), "
                            f"dann wird die PIN gesperrt.")


@app.post("/api/logout")
def api_logout(resp: Response):
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/me")
def api_me(benutzer=Depends(require_user)):
    return {"name": benutzer["name"], "rolle": benutzer["rolle"],
            "spieler_id": benutzer.get("spieler_id")}


# ------------------------------------------------------------ Datenmodelle ----

class SpielerNeu(BaseModel):
    name: str
    stufe: str = "mittel"          # stark / mittel / schwach
    position: str = "Feld"         # Tor / Feld


class TeamsAnfrage(BaseModel):
    anwesend: list[int]
    anzahl: int = 2                # 2 bis 4 Teams


class SpielerAendern(BaseModel):
    stufe: str | None = None              # stark / mittel / schwach
    position: str | None = None           # Tor / Feld
    aktiv: bool | None = None
    position_angriff: str | None = None   # "Halblinks/Kreis" (Freitext, '/'-getrennt)


class SpielAnfrage(BaseModel):
    teams: list[list[int]] | None = None   # 2 bis 4 Teams (neu)
    team_a: list[int] = []                 # Altform, weiter erlaubt
    team_b: list[int] = []
    ergebnis: str                  # Buchstabe des Siegerteams (A-D) oder U
    token: str | None = None       # Idempotenz-Schluessel (einmalig je Spiel)


# --------------------------------------------------------------- Endpunkte ----

@app.get("/api/ping")
def api_ping():
    """Leichter Health-Check fuer die Offline-App (Serverstatus-Punkt)."""
    return {"ok": True}


@app.get("/api/spieler")
def api_spieler(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    return db.aktive_spieler(conn)


@app.post("/api/spieler")
def api_spieler_anlegen(s: SpielerNeu, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    if not s.name.strip():
        raise HTTPException(400, "Name fehlt")
    neue_id = db.spieler_anlegen(
        conn, s.name.strip(), stufe=s.stufe, position=s.position
    )
    return {"id": neue_id}


@app.post("/api/spieler/{spieler_id}")
def api_spieler_aendern(spieler_id: int, aenderung: SpielerAendern,
                        conn=Depends(hole_conn), _t=Depends(require_trainer)):
    db.spieler_aktualisieren(
        conn, spieler_id,
        stufe=aenderung.stufe, position=aenderung.position, aktiv=aenderung.aktiv,
        position_angriff=aenderung.position_angriff,
    )
    return {"ok": True}


@app.get("/api/spieler/{spieler_id}/spiele")
def api_spieler_spiele(spieler_id: int, conn=Depends(hole_conn),
                       benutzer=Depends(require_user)):
    # Trainer sehen alle; Spielerinnen nur ihr eigenes Profil.
    if benutzer["rolle"] != "trainer" and benutzer.get("spieler_id") != spieler_id:
        raise HTTPException(403, "Kein Zugriff auf dieses Profil")
    d = db.spieler_detail(conn, spieler_id)
    if d is None:
        raise HTTPException(404, "Spielerin nicht gefunden")
    return d


@app.post("/api/anytype/import")
def api_anytype_import(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        import anytype_sync
        at = anytype_sync.get_client()
        res = db.import_kader(conn, anytype_sync.lade_kader(at))
    except Exception as e:  # requests-/Anytype-Fehler sauber ans Frontend
        raise HTTPException(502, f"Anytype-Import fehlgeschlagen: {e}")
    return res


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


@app.get("/api/anytype/trainings")
def api_anytype_trainings(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        import anytype_sync
        at = anytype_sync.get_client()
        trainings = anytype_sync.lade_trainings(at)
    except Exception as e:
        raise HTTPException(502, f"Anytype-Trainings fehlgeschlagen: {e}")
    karte = {p["anytype_id"]: p["id"]
             for p in db.aktive_spieler(conn) if p.get("anytype_id")}
    result = []
    for t in trainings:
        ids = [karte[a] for a in t["anwesend_anytype"] if a in karte]
        result.append({
            "id": t["id"],
            "name": t["name"],
            "datum": t["datum"],
            "label": _training_label(t["datum"]),
            "spieler_ids": ids,
            "anwesend_gesamt": len(t["anwesend_anytype"]),
        })
    return result


@app.get("/api/trainings")
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


@app.get("/api/trainings/{tid}")
def api_training_detail(tid: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    d = db.training_detail(conn, tid)
    if d is None:
        raise HTTPException(404, "Training nicht gefunden")
    return d if benutzer["rolle"] == "trainer" else _ohne_plan(d)


class TrainingPlan(BaseModel):
    markdown: str = ""
    token: str | None = None       # Idempotenz-Token der Outbox (hier ignoriert)


@app.post("/api/trainings/{tid}/plan")
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


@app.post("/api/trainings/{tid}/blocks")
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


@app.post("/api/trainings/{tid}/blocks/aus-text")
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
    uhrzeit: str | None = None     # 'HH:MM'
    ort: str | None = None
    markdown: str = ""             # optionaler Plan
    token: str | None = None


@app.post("/api/trainings")
def api_training_anlegen(t: TrainingNeu, conn=Depends(hole_conn),
                         _t=Depends(require_trainer)):
    """Training anlegen (oder bestehendes am Datum wiederverwenden) + optional
    Uhrzeit/Ort/Coach-Plan. Ersetzt die Anytype-Neuanlage. Nur Trainer/Admin."""
    if not t.datum.strip():
        raise HTTPException(400, "Datum fehlt")
    tid, neu = db.training_anlegen(conn, t.datum.strip(), t.titel,
                                   t.markdown or None,
                                   uhrzeit=(t.uhrzeit or None), ort=(t.ort or None))
    return {"id": tid, "neu": neu}


@app.post("/api/trainings/{tid}/loeschen")
def api_training_loeschen(tid: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Training loeschen - nur Trainer/Admin. Idempotent: ist der Termin schon
    weg, gilt der Aufruf trotzdem als erfolgreich, damit ein wiederholter
    Versuch (Outbox, Doppeltipp) keinen Fehler wirft."""
    weg = db.training_loeschen(conn, tid)
    return {"ok": True, "geloescht": weg}


class TeilnahmeAnfrage(BaseModel):
    status: str                    # anwesend / abgesagt / unsicher
    grund: str | None = None       # Pflicht bei 'abgesagt'
    token: str | None = None       # Outbox-Idempotenz (hier ignoriert)


@app.post("/api/trainings/{tid}/teilnahme")
def api_teilnahme(tid: int, a: TeilnahmeAnfrage, conn=Depends(hole_conn),
                  benutzer=Depends(require_user)):
    """Eigene Zu-/Absage setzen. Die Spielerin wird aus der Session abgeleitet
    (nie aus dem Body) -> man kann nur fuer SICH antworten."""
    sid = benutzer.get("spieler_id")
    if not sid:
        raise HTTPException(403, "Dein Konto ist mit keiner Spielerin verknüpft.")
    if a.status not in ("anwesend", "abgesagt", "unsicher"):
        raise HTTPException(400, "Ungültiger Status.")
    grund = (a.grund or "").strip() or None
    if a.status == "abgesagt" and not grund:
        raise HTTPException(400, "Bei einer Absage bitte einen Grund angeben.")
    if conn.execute("SELECT 1 FROM trainings WHERE id = ?", (tid,)).fetchone() is None:
        raise HTTPException(404, "Training nicht gefunden")
    db.teilnahme_setzen(conn, tid, sid, a.status, grund, quelle="app")
    return {"ok": True, "status": a.status, "grund": grund}


# ------------------------------------------------------------- Web-Push ----

class PushAbo(BaseModel):
    endpoint: str
    keys: dict = {}                # {p256dh, auth}


@app.get("/api/push/vapid")
def api_push_vapid(_u=Depends(require_user)):
    import push
    return {"publicKey": push.public_key()}


@app.post("/api/push/subscribe")
def api_push_subscribe(a: PushAbo, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    keys = a.keys or {}
    if not a.endpoint or not keys.get("p256dh") or not keys.get("auth"):
        raise HTTPException(400, "Ungültiges Push-Abo")
    db.push_abo_speichern(conn, benutzer["id"], a.endpoint, keys["p256dh"], keys["auth"])
    return {"ok": True}


@app.post("/api/push/unsubscribe")
def api_push_unsubscribe(a: PushAbo, conn=Depends(hole_conn), _u=Depends(require_user)):
    if a.endpoint:
        db.push_abo_loeschen(conn, a.endpoint)
    return {"ok": True}


@app.post("/api/push/test")
def api_push_test(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Test-Push an die eigenen Geraete (zum Selbst-Pruefen der Zustellung)."""
    import push
    return push.sende(conn, [benutzer["id"]], "Balu's Training",
                      "Test-Benachrichtigung ✓ – Push funktioniert.", url="/")


@app.post("/api/trainings/{tid}/erinnern")
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
                     f"{label}: Bitte in der App zu- oder absagen.", url="/")
    return {"offen": len(offen), **res}


@app.get("/api/naechstes-training")
def api_naechstes_training(conn=Depends(hole_conn), benutzer=Depends(require_user)):
    """Fuer den Home-Screen: naechstes Training ab heute (oder null).
    Der Plan geht nur an Trainer - wie beim Trainings-Detail."""
    d = db.naechstes_training(conn)
    if d is None:
        return None
    return d if benutzer["rolle"] == "trainer" else _ohne_plan(d)


@app.get("/api/seiten")
def api_seiten(kategorie: str | None = None, conn=Depends(hole_conn),
               benutzer=Depends(require_user)):
    """Wiki-Seiten. Spielerinnen sehen NUR das Playbook, Trainer alles."""
    if benutzer["rolle"] != "trainer":
        if kategorie != "playbook":
            raise HTTPException(403, "Nur das Playbook ist für Spielerinnen sichtbar")
    return db.seiten_liste(conn, kategorie)


@app.get("/api/seiten/{sid}")
def api_seite(sid: int, conn=Depends(hole_conn), benutzer=Depends(require_user)):
    d = db.seite_detail(conn, sid)
    if d is None:
        raise HTTPException(404, "Seite nicht gefunden")
    if benutzer["rolle"] != "trainer" and d.get("kategorie") != "playbook":
        raise HTTPException(403, "Nur das Playbook ist für Spielerinnen sichtbar")
    return d


class SeiteNeu(BaseModel):
    titel: str
    kategorie: str                 # 'playbook'/'uebung'/'gegner'/...
    parent_id: int | None = None   # Unterseite einer Gruppe (z. B. Spielzüge)
    markdown: str = ""
    token: str | None = None       # Outbox-Idempotenz (hier ignoriert)


class SeiteAendern(BaseModel):
    titel: str | None = None
    markdown: str | None = None
    token: str | None = None


@app.post("/api/seiten")
def api_seite_anlegen(s: SeiteNeu, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Neue Wiki-Seite anlegen (nur Trainer). Damit ist das Playbook nativ in der
    App pflegbar — kein Umweg mehr über Anytype."""
    titel = s.titel.strip()
    if not titel:
        raise HTTPException(400, "Titel fehlt")
    if s.parent_id is not None:
        eltern = db.seite_detail(conn, s.parent_id)
        if eltern is None:
            raise HTTPException(404, "Übergeordnete Seite nicht gefunden")
        if eltern.get("kategorie") != s.kategorie:
            raise HTTPException(400, "Unterseite muss dieselbe Kategorie haben")
    sid = db.seite_anlegen(conn, titel, s.kategorie, s.parent_id, s.markdown or None)
    return {"id": sid}


@app.post("/api/seiten/{sid}")
def api_seite_aendern(sid: int, a: SeiteAendern, conn=Depends(hole_conn),
                      _t=Depends(require_trainer)):
    """Titel und/oder Inhalt einer Seite setzen (nur Trainer). Idempotent."""
    titel = a.titel.strip() if a.titel is not None else None
    if titel == "":
        raise HTTPException(400, "Titel darf nicht leer sein")
    if db.seite_detail(conn, sid) is None:
        raise HTTPException(404, "Seite nicht gefunden")
    db.seite_speichern(conn, sid, markdown=a.markdown, titel=titel)
    return {"ok": True}


@app.post("/api/seiten/{sid}/loeschen")
def api_seite_loeschen(sid: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Seite loeschen (nur Trainer). Unterseiten ruecken eine Ebene hoch."""
    db.seite_loeschen(conn, sid)      # bereits geloescht -> ebenfalls ok (Outbox)
    return {"ok": True}


@app.post("/api/anytype/sync")
def api_anytype_sync(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    try:
        import anytype_sync
        at = anytype_sync.get_client()
        key = anytype_sync.elo_key()
        paare = [(p["anytype_id"], p["elo"])
                 for p in db.rangliste(conn) if p.get("anytype_id")]
        n = anytype_sync.schreibe_elos(at, paare, key)
    except Exception as e:
        raise HTTPException(502, f"Anytype-Sync fehlgeschlagen: {e}")
    return {"geschrieben": n}


@app.post("/api/teams")
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


@app.post("/api/spiel")
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


@app.post("/api/undo")
def api_undo(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    ok = db.letztes_spiel_ruecknehmen(conn)
    return {"ok": ok, "rangliste": db.rangliste(conn)}


class SpielKorrektur(BaseModel):
    ergebnis: str                  # A-D (Siegerteam) oder U


@app.post("/api/spiel/{spiel_id}/aendern")
def api_spiel_aendern(spiel_id: int, k: SpielKorrektur, conn=Depends(hole_conn),
                      _t=Depends(require_trainer)):
    try:
        if not db.spiel_aendern(conn, spiel_id, k.ergebnis):
            raise HTTPException(404, "Spiel nicht gefunden")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "rangliste": db.rangliste(conn)}


@app.post("/api/spiel/{spiel_id}/loeschen")
def api_spiel_loeschen(spiel_id: int, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    if not db.spiel_loeschen(conn, spiel_id):
        raise HTTPException(404, "Spiel nicht gefunden")
    return {"ok": True, "rangliste": db.rangliste(conn)}


@app.get("/api/rangliste")
def api_rangliste(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    return db.rangliste(conn)


# ------------------------------------------------------------------- PWA -----

class ChatAnfrage(BaseModel):
    verlauf: list[dict]            # [{role, content}, ...] ohne System-Prompt


class AnytypeTraining(BaseModel):
    titel: str
    markdown: str
    datum: str | None = None        # ISO, z. B. 2026-07-05 (fuer neues Training)
    training_id: str | None = None  # bestehendes Training, an das angehaengt wird


class ChatNachricht(BaseModel):
    rolle: str                      # user / bot / info / plan
    text: str
    roh: str | None = None
    titel: str | None = None


@app.get("/api/chat")
def api_chat(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    return db.chat_verlauf(conn)


@app.post("/api/chat")
def api_chat_anhaengen(m: ChatNachricht, conn=Depends(hole_conn), _t=Depends(require_trainer)):
    if m.rolle not in ("user", "bot", "info", "plan"):
        raise HTTPException(400, "Ungültige Rolle.")
    return db.chat_anhaengen(conn, m.rolle, m.text, roh=m.roh, titel=m.titel)


@app.post("/api/chat/loeschen")
def api_chat_loeschen(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    db.chat_leeren(conn)
    return {"ok": True}


@app.post("/api/trainer/chat")
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


@app.post("/api/trainer/audio")
async def api_trainer_audio(datei: UploadFile = File(...), _t=Depends(require_trainer)):
    data = await datei.read()
    try:
        text = trainer.transkribiere(data, datei.filename or "audio.webm")
    except Exception as e:
        raise HTTPException(502, f"Transkription fehlgeschlagen: {e}")
    return {"text": text}


@app.post("/api/trainer/anytype")
def api_trainer_anytype(t: AnytypeTraining, _t=Depends(require_trainer)):
    try:
        import anytype_sync
        at = anytype_sync.get_client()
        res = anytype_sync.training_plan_einfuegen(
            at, t.titel, t.markdown, training_id=t.training_id, datum=t.datum)
    except Exception as e:
        raise HTTPException(502, f"Anytype-Anlage fehlgeschlagen: {e}")
    return res


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


# Digital Asset Links: verknuepft die Android-App de.tvg.balu (Ordner Balu-APK,
# Trusted Web Activity) mit dieser Domain. Ohne diese Datei startet die App mit
# einer Browser-Adressleiste; passt der Fingerprint, laeuft sie im Vollbild.
# Fingerprint = SHA-256 von Balu-APK/balu-release.jks (Alias 'balu'). Muss bei
# einem neuen Signing-Key aktualisiert werden. Bewusst ohne Login erreichbar.
ASSETLINKS = [{
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
        "namespace": "android_app",
        "package_name": "de.tvg.balu",
        "sha256_cert_fingerprints": [
            "61:54:17:B4:0F:D9:2C:85:1A:B8:2D:6F:5B:48:05:87:"
            "33:A9:E7:FF:5C:6F:AE:05:13:31:5C:8C:A1:64:3F:AD"
        ],
    },
}]


@app.get("/.well-known/assetlinks.json")
def assetlinks():
    return JSONResponse(ASSETLINKS, media_type="application/json")


app.mount("/", StaticFiles(directory=STATIC), name="static")
