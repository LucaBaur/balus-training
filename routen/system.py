"""Ping, Startseite und assetlinks."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from . import pfade


router = APIRouter()


# --------------------------------------------------------------- Endpunkte ----

@router.get("/api/ping")
def api_ping():
    """Leichter Health-Check fuer die Offline-App (Serverstatus-Punkt)."""
    return {"ok": True}


@router.get("/")
def index():
    return FileResponse(pfade.STATIC / "index.html")


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


@router.get("/.well-known/assetlinks.json")
def assetlinks():
    return JSONResponse(ASSETLINKS, media_type="application/json")
