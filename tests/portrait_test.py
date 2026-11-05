"""Tests fuer die selbst gewaehlten Portraits (Foto hochladen, Buchstabe, entfernen).

Laeuft gegen eine temporaere Datenbank und ein temporaeres Medienverzeichnis -
echte elo.db und media/ bleiben unberuehrt.
Start:  py tests/portrait_test.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
from routen import pfade  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="portrait_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)
pfade.MEDIA_PORTRAITS = tmp / "portraits"
pfade.MEDIA_PORTRAITS.mkdir()

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
bea = db.spieler_anlegen(conn, "Bea")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
db.benutzer_anlegen(conn, "Bea", "spieler", auth.hash_pin("3333"), bea)
conn.close()

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def pruefe(bedingung, text):
    assert bedingung, text
    print("  ok  " + text)


a, b, t = client("Anna", "2222"), client("Bea", "3333"), client("Trainer", "1111")
anonym = TestClient(balu.app)

# Ausgangslage: alle auf 'foto', kein eigenes Bild
liste = {p["id"]: p for p in b.get("/api/portraits").json()}
pruefe(liste[anna]["v"] == 0 and liste[anna]["modus"] == "foto", "Standard: kein Foto, Modus foto")
pruefe(anonym.get("/api/portraits").status_code == 401, "Liste nur mit Anmeldung")
pruefe(a.get(f"/api/portrait/{anna}").status_code == 404, "ohne Upload kein eigenes Foto")

# Hochladen
r = a.post("/api/ich/portrait", files={"bild": ("x.jpg", JPEG, "image/jpeg")})
pruefe(r.status_code == 200 and r.json()["v"] > 0, "Anna laedt ein JPEG hoch")
v = r.json()["v"]
pruefe(b.get(f"/api/portrait/{anna}").content == JPEG, "Bea sieht Annas Foto (fuer die Aufstellung)")
pruefe(b.get(f"/api/portrait/{anna}").headers["content-type"] == "image/jpeg", "Typ image/jpeg")
pruefe(anonym.get(f"/api/portrait/{anna}").status_code == 401, "Foto nur mit Anmeldung")
liste = {p["id"]: p for p in b.get("/api/portraits").json()}
pruefe(liste[anna]["v"] == v and liste[bea]["v"] == 0, "nur Annas Version hat sich geaendert")

# Ablehnungen
pruefe(a.post("/api/ich/portrait", files={"bild": ("x.jpg", b"GIF89a" + b"0" * 50, "image/gif")})
       .status_code == 400, "kein JPEG -> abgelehnt")
pruefe(a.post("/api/ich/portrait", files={"bild": ("x.jpg", JPEG + b"0" * 500_000, "image/jpeg")})
       .status_code == 413, "zu gross -> abgelehnt")
pruefe(a.post("/api/ich/portrait", files={"bild": ("x.jpg", b"", "image/jpeg")})
       .status_code == 400, "leere Datei -> abgelehnt")
pruefe(t.post("/api/ich/portrait", files={"bild": ("x.jpg", JPEG, "image/jpeg")})
       .status_code == 400, "Trainer ohne Spielerin kann nichts hochladen")
pruefe(anonym.post("/api/ich/portrait", files={"bild": ("x.jpg", JPEG, "image/jpeg")})
       .status_code == 401, "Upload nur mit Anmeldung")

# Buchstabe <-> Foto: das Bild bleibt erhalten
pruefe(a.post("/api/ich/portrait-modus", json={"modus": "initial"}).json()["modus"] == "initial",
       "auf Buchstabe umgestellt")
liste = {p["id"]: p for p in a.get("/api/portraits").json()}
pruefe(liste[anna]["modus"] == "initial" and liste[anna]["v"] == v, "Modus initial, Foto bleibt gespeichert")
pruefe(a.post("/api/ich/portrait-modus", json={"modus": "quatsch"}).status_code == 400, "ungueltiger Modus")
pruefe(liste[bea]["modus"] == "foto", "Beas Wahl bleibt unberuehrt")
a.post("/api/ich/portrait-modus", json={"modus": "foto"})

# Neues Foto schaltet wieder auf 'foto'
a.post("/api/ich/portrait-modus", json={"modus": "initial"})
a.post("/api/ich/portrait", files={"bild": ("x.jpg", JPEG, "image/jpeg")})
liste = {p["id"]: p for p in a.get("/api/portraits").json()}
pruefe(liste[anna]["modus"] == "foto", "neues Foto -> Modus wieder foto")

# Entfernen
pruefe(a.post("/api/ich/portrait/loeschen").status_code == 200, "Anna entfernt ihr Foto")
pruefe(a.get(f"/api/portrait/{anna}").status_code == 404, "Datei ist weg")
pruefe(not (pfade.MEDIA_PORTRAITS / f"{anna}.jpg").exists(), "auch auf der Platte")

# 'Ansicht als': der Trainer darf im fremden Konto nichts aendern
konten = t.get("/api/ansicht/konten").json()
annas_konto = next(k for k in konten if k["name"] == "Anna")["benutzer_id"]
t.post(f"/api/ansicht/{annas_konto}")
pruefe(t.post("/api/ich/portrait-modus", json={"modus": "initial"}).status_code == 403,
       "Ansicht-als ist nur lesend")

print("\nalle Portrait-Tests gruen")
