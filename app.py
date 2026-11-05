"""FastAPI-Backend fuer Balu's Training.

Liefert die PWA aus (statische Dateien) und stellt die JSON-Endpunkte bereit,
die das Frontend nutzt. Start:  uvicorn app:app --host 0.0.0.0 --port 8200

Diese Datei baut die Anwendung nur zusammen: Middleware, Datenbank, Router.
Die Endpunkte selbst stehen in routen/ (ein APIRouter je Themenbereich),
die Datenzugriffe in daten/ (ueber die Fassade db.py).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import auth
import db
from routen import (analysen, anytype, coach, einteilung, fotos, kommentare, konto, mannschaft,
                    mitteilungen, nutzung, pfade, spieler, spielerplus, system, tabelle,
                    termine, todos, videos, wiki)

app = FastAPI(title="Balu's Training")


@app.middleware("http")
async def sw_kein_cache(request, call_next):
    resp = await call_next(request)
    if request.url.path == "/sw.js":
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.middleware("http")
async def ansicht_nur_lesen(request, call_next):
    """Im "Ansicht als"-Modus (Trainer sieht die App als eine Spielerin) sind
    alle schreibenden Aufrufe gesperrt - nichts soll versehentlich im fremden
    Konto passieren. Ausgenommen: das Umschalten selbst und Abmelden."""
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        d = auth.session_daten(request.cookies.get(auth.COOKIE_NAME))
        if d and d.get("als") is not None:
            pfad = request.url.path
            if not (pfad.startswith("/api/ansicht/") or pfad == "/api/logout"):
                return JSONResponse(
                    {"detail": "Nur-Lesen: du siehst die App gerade als jemand anderes."},
                    status_code=403)
    return await call_next(request)


# Datenbank beim Start sicherstellen (Verbindung sofort schliessen, sonst
# bleibt die Datei gesperrt)
_c = db.verbinde()
db.init_db(_c)
_c.close()

# Reihenfolge wie frueher in der einen Datei. Das ist wichtig, wo sich Pfade
# ueberlappen koennten (feste Pfade vor solchen mit {Platzhalter}); die Routen
# stehen jeweils in ihrem eigenen Modul in der richtigen Reihenfolge.
for modul in (konto, nutzung, kommentare, todos, tabelle, spieler, fotos, anytype, termine,
              mannschaft, mitteilungen, spielerplus, wiki, einteilung, coach, videos,
              analysen, system):
    app.include_router(modul.router)

# Statische Dateien zuletzt: sie fangen alles ab, was keine Route war.
app.mount("/", StaticFiles(directory=pfade.STATIC), name="static")
