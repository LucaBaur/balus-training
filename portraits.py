#!/usr/bin/env python3
"""Baut aus den Original-Portraits die Web-Bilder fuer die App.

Ablage:
  portraits/<Name>.jpg          Originale (gross, unveraendert, nicht ausgeliefert)
  static/portraits/<slug>.jpg   fertige Bilder fuer die App (5:6, wie das Wappen)
  static/portraits/index.json   Zuordnung Spielerinnen-Name -> Datei

Der Zuschnitt passiert automatisch: die Studio-Fotos haben einen hellen,
einfarbigen Hintergrund, darum laesst sich die Person freistellen. Aus der
Maske ergeben sich Kopfoberkante und Kopfmitte - daraus wird ein
Kopf-Schulter-Ausschnitt im Wappen-Format 5:6 gerechnet.

Aufruf:
    py portraits.py              # alle Bilder neu bauen
    py portraits.py --pruefen    # zusaetzlich gegen die Spielerinnen am Server pruefen
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from PIL import Image

HIER = Path(__file__).resolve().parent
QUELLE = HIER / "portraits"
ZIEL = HIER / "static" / "portraits"

BREITE, HOEHE = 460, 552          # 5:6, reicht fuer die groesste Anzeige (@2x)
QUALITAET = 82
KOPF_ANTEIL = 0.32                # Ausschnitthoehe = 32 % der Bildhoehe
                                  # (eng genug, dass das Gesicht auch im 28-px-
                                  # Wappen auf dem Feld noch erkennbar ist)

# Dateiname (ohne .jpg) -> Name der Spielerin in der Datenbank.
# Neues Foto: Datei nach portraits/ legen und hier eine Zeile ergaenzen.
ZUORDNUNG = {
    "Anne": "Anne",
    "Annika": "Annika Lutz",
    "Franzi O": "Franzi O.",
    "Franzi P": "Franzi P",
    "Hanna": "Hanna R",
    "Helen": "Helen",
    "Lilly": "Lilly",
    "Linda": "Linda",
    "Maike": "Maike",
    "Rebecca": "Rebecca Scott",
    "Svenja": "Svenja",
}

# Feinjustierung je Bild, falls der automatische Zuschnitt danebenliegt:
#   "Datei": (x_versatz, y_versatz, zoom)  - Versatz in Kopfhoehen, zoom < 1 = naeher dran
FEIN: dict[str, tuple[float, float, float]] = {}


def slug(text: str) -> str:
    """'Franzi O.' -> 'franzi-o' (auch als Schluessel in der index.json)."""
    t = unicodedata.normalize("NFKD", text.lower())
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", t)).strip("-")


def maske(bild: Image.Image, breite: int = 200):
    """Grobe Silhouette: je Zeile die Spalten, die sich vom Hintergrund abheben.

    Gibt (zeilen, breite, hoehe) zurueck - zeilen[y] ist die Liste der x-Werte,
    an denen die Person steht.
    """
    klein = bild.convert("RGB").resize((breite, round(breite * bild.height / bild.width)))
    px = klein.load()
    w, h = klein.size
    # Hintergrundfarbe aus den oberen Ecken (dort steht nie jemand).
    ecken = [px[x, y] for y in range(0, max(1, h // 12))
             for x in list(range(0, w // 10)) + list(range(w - w // 10, w))]
    bg = tuple(sorted(k[i] for k in ecken)[len(ecken) // 2] for i in range(3))
    # Schwelle ueber die Summe der Kanal-Abstaende: Haare/Trikot liegen weit
    # ueber 150, Falten und Schatten der Wand deutlich darunter.
    grenze = 150
    zeilen = []
    for y in range(h):
        zeilen.append([x for x in range(w)
                       if abs(px[x, y][0] - bg[0]) + abs(px[x, y][1] - bg[1])
                       + abs(px[x, y][2] - bg[2]) > grenze])
    return zeilen, w, h


def ausschnitt(bild: Image.Image, fein=(0.0, 0.0, 1.0)) -> tuple[int, int, int, int]:
    """Kopf-Schulter-Ausschnitt im Verhaeltnis 5:6, in Original-Pixeln.

    Alle Fotos stammen aus demselben Shooting (gleiche Kamera, gleicher
    Abstand), die Koepfe sind also ueberall etwa gleich gross. Darum ist die
    Ausschnittgroesse fest (KOPF_ANTEIL der Bildhoehe) und die Erkennung legt
    nur fest, WO der Ausschnitt sitzt - das haelt den Zoom ueber alle Bilder
    gleich, statt an einer wackligen Schulterkante zu haengen.
    """
    zeilen, w, h = maske(bild)
    mind = max(3, w // 40)                      # Rauschen ignorieren

    kopf_y = next((y for y in range(h) if len(zeilen[y]) >= mind), h // 4)

    # Kopfmitte aus dem obersten Bildteil der Person (Kopf, noch ohne Schultern).
    band = [zeilen[y] for y in range(kopf_y, min(h, kopf_y + round(h * 0.075))) if zeilen[y]]
    kopf_x = (sum((z[0] + z[-1]) / 2 for z in band) / len(band)) if band else w / 2

    dx, dy, zoom = fein
    ch = h * KOPF_ANTEIL * zoom                 # feste Ausschnitthoehe
    cw = ch * 5 / 6
    oben = kopf_y - ch * 0.10 + dy * ch
    links = kopf_x - cw / 2 + dx * ch

    f = bild.width / w                          # zurueck auf Originalgroesse
    kasten = [links * f, oben * f, (links + cw) * f, (oben + ch) * f]

    # in das Bild schieben, statt es zu verzerren
    if kasten[0] < 0: kasten[0], kasten[2] = 0, kasten[2] - kasten[0]
    if kasten[1] < 0: kasten[1], kasten[3] = 0, kasten[3] - kasten[1]
    if kasten[2] > bild.width: kasten[0] -= kasten[2] - bild.width; kasten[2] = bild.width
    if kasten[3] > bild.height: kasten[1] -= kasten[3] - bild.height; kasten[3] = bild.height
    return tuple(max(0, round(k)) for k in kasten)


def baue() -> dict[str, str]:
    ZIEL.mkdir(parents=True, exist_ok=True)
    index: dict[str, str] = {}
    for datei in sorted(QUELLE.glob("*.jpg")):
        name = ZUORDNUNG.get(datei.stem)
        if not name:
            print(f"  ! {datei.name}: keine Zuordnung in ZUORDNUNG - uebersprungen")
            continue
        bild = Image.open(datei).convert("RGB")
        kasten = ausschnitt(bild, FEIN.get(datei.stem, (0.0, 0.0, 1.0)))
        aus = bild.crop(kasten).resize((BREITE, HOEHE), Image.LANCZOS)
        zieldatei = ZIEL / f"{slug(name)}.jpg"
        aus.save(zieldatei, "JPEG", quality=QUALITAET, optimize=True, progressive=True)
        index[slug(name)] = zieldatei.name
        print(f"  ok {datei.name:16s} -> {zieldatei.name:22s} "
              f"({zieldatei.stat().st_size // 1024} kB, Ausschnitt {kasten})")
    (ZIEL / "index.json").write_text(
        json.dumps({"spieler": index}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def pruefe(index: dict[str, str]) -> None:
    """Gleicht die Zuordnung mit den Spielerinnen am Homeserver ab."""
    cmd = ("python3 -c \"import sqlite3;c=sqlite3.connect('/home/you/elo/elo.db');"
           "print('\\n'.join(r[0] for r in c.execute('select name from spieler where aktiv=1')))\"")
    try:
        roh = subprocess.run(["ssh", "-o", "ConnectTimeout=8", "you@homeserver", cmd],
                             capture_output=True, text=True, timeout=30, check=True).stdout
    except Exception as e:                       # kein Netz -> Build trotzdem gruen
        print(f"  (Abgleich uebersprungen: {e})")
        return
    kader = {slug(n): n for n in roh.split("\n") if n.strip()}
    for s in index:
        print(f"  {'ok' if s in kader else '!!'} {s:22s} "
              f"{kader.get(s, 'KEINE Spielerin mit diesem Namen')}")
    ohne = [n for s, n in kader.items() if s not in index]
    if ohne:
        print("  ohne Foto: " + ", ".join(sorted(ohne)))


if __name__ == "__main__":
    print(f"== Portraits bauen ({QUELLE} -> {ZIEL}) ==")
    index = baue()
    print(f"== {len(index)} Bilder, index.json geschrieben ==")
    if "--pruefen" in sys.argv:
        print("== Abgleich mit dem Kader am Server ==")
        pruefe(index)
