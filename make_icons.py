"""Erzeugt die App-Symbole: weißes "B" mit Handball auf dunklem Vereinsblau.

Das Symbol besteht aus drei Dingen: dem "B" (für Balu), der gestrichelten 9-m-Linie als Kreis
(die Signatur der App, sie läuft auch unter dem Kopf der App entlang) und einem Handball auf dieser
Linie. Alle Größen entstehen aus derselben Geometrie (Koordinaten in einem Feld von 108 x 108),
damit sie nie auseinanderlaufen:

  icon-512.png / icon-192.png   Browser, Startbildschirm, Android-App
  icon-maskable-512.png         Inhalt auf 82 % verkleinert: Android schneidet Kreise/Rundungen aus
  icon-180.png                  iPhone (iOS rundet selbst ab)
  badge-96.png                  Weißes B auf durchsichtig, für die kleine Statusleisten-Marke der Mitteilung
  icon.svg                      Vorlage als Vektor (Favicon, spätere Änderungen)

Nutzt Pillow und rendert 4x hoch, damit die Kanten glatt werden.
Aufruf:  py make_icons.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SS = 4                                   # Supersampling
BLAU = (18, 47, 94)                      # #122F5E, tiefes Vereinsblau (Hintergrund)
VEREINSBLAU = (35, 78, 158)              # #234E9E
OCKER = (198, 139, 79)                   # #C68B4F, Torraum
WEISS = (255, 255, 255)
LINIE = (113, 130, 158)                  # weiß mit 40 % auf BLAU, als Vollfarbe
FELD = 108                               # Koordinaten der Vorlage

# Der Buchstabe: ein Strich und zwei Bögen, in Feldkoordinaten
BOGEN = 12.5


def _bogen(cx, cy, r, von, bis, n=40):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in [von + (bis - von) * i / n for i in range(n + 1)]]


B_PFADE = [
    [(39, 29), (39, 79)],
    [(39, 29), (57, 29)] + _bogen(57, 29 + BOGEN, BOGEN, -90, 90) + [(39, 54)],
    [(39, 54), (60, 54)] + _bogen(60, 54 + BOGEN, BOGEN, -90, 90) + [(39, 79)],
]
B_STRICH = 9
BALL = (81, 27, 11.4)                    # Mitte x, y und Radius (sitzt auf der gestrichelten Linie)


def _strich(d, pfad, breite, farbe, u):
    """Linienzug mit runden Enden und Ecken: dicht gesetzte Kreise statt `line(joint=...)`,
    das an engen Bögen ausfranst."""
    r = breite * u / 2
    schritt = max(0.5, u * 0.25)                      # Abstand der Kreise in Pixeln
    for (x0, y0), (x1, y1) in zip(pfad, pfad[1:]):
        x0, y0, x1, y1 = x0 * u, y0 * u, x1 * u, y1 * u
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / schritt))
        for i in range(n + 1):
            x, y = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n
            d.ellipse([x - r, y - r, x + r, y + r], fill=farbe)


def _handball(d, cx, cy, r, u):
    """Weißer Ball, nur aus blauen Nähten: ein Fünfeck in der Mitte und fünf Linien zum Rand."""
    X, Y, R = cx * u, cy * u, r * u
    d.ellipse([X - R, Y - R, X + R, Y + R], fill=WEISS, outline=BLAU, width=max(1, int(1.5 * u)))
    pent = [(X + 0.40 * R * math.cos(math.radians(a)), Y + 0.40 * R * math.sin(math.radians(a)))
            for a in (-90, -18, 54, 126, 198)]
    for (px, py), a in zip(pent, (-90, -18, 54, 126, 198)):
        ex, ey = X + 0.86 * R * math.cos(math.radians(a)), Y + 0.86 * R * math.sin(math.radians(a))
        d.line([(px, py), (ex, ey)], fill=VEREINSBLAU, width=max(1, int(1.2 * u)))
    # das Fünfeck nur als Naht, gleich dünn und gleich blau wie die fünf Linien nach außen
    d.line(pent + [pent[0]], fill=VEREINSBLAU, width=max(1, int(1.2 * u)), joint="curve")


def zeichne(groesse: int, skala: float = 1.0, hintergrund=BLAU, nur_b: bool = False) -> Image.Image:
    """Ein quadratisches Symbol. `skala` < 1 lässt Rand (maskable), `nur_b` = weißes B ohne Rest."""
    N = groesse * SS
    u = N / FELD * skala
    off = N * (1 - skala) / 2
    bild = Image.new("RGBA", (N, N), hintergrund + (255,) if hintergrund else (0, 0, 0, 0))
    ebene = Image.new("RGBA", (int(FELD * u), int(FELD * u)), (0, 0, 0, 0))
    d = ImageDraw.Draw(ebene)
    if not nur_b:
        # gestrichelte Kreislinie, Strichlänge 5, Lücke 4 (wie im Kopf der App)
        R = 42
        winkel = 0.0
        while winkel < 360:
            a0, a1 = winkel, winkel + math.degrees(5 / R)
            d.arc([(54 - R) * u, (54 - R) * u, (54 + R) * u, (54 + R) * u], a0, a1,
                  fill=LINIE, width=max(1, int(2.4 * u)))
            winkel += math.degrees(9 / R)
    for pfad in B_PFADE:
        _strich(d, pfad, B_STRICH, WEISS, u)
    if not nur_b:
        _handball(d, *BALL[:2], BALL[2], u)
    bild.alpha_composite(ebene, (int(off), int(off)))
    return bild.resize((groesse, groesse), Image.LANCZOS)


def svg() -> str:
    """Dieselbe Geometrie als Vektor."""
    b = " ".join(
        "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in pfad) for pfad in B_PFADE)
    cx, cy, r = BALL
    pent = [(cx + 0.40 * r * math.cos(math.radians(a)), cy + 0.40 * r * math.sin(math.radians(a)))
            for a in (-90, -18, 54, 126, 198)]
    nahte = "".join(
        f'<path d="M{px:.2f} {py:.2f} L{cx + 0.86 * r * math.cos(math.radians(a)):.2f} '
        f'{cy + 0.86 * r * math.sin(math.radians(a)):.2f}" stroke="#234E9E" stroke-width="1.2"/>'
        for (px, py), a in zip(pent, (-90, -18, 54, 126, 198)))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108">'
        '<rect width="108" height="108" fill="#122F5E"/>'
        '<circle cx="54" cy="54" r="42" fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="2.4" stroke-dasharray="5 4"/>'
        f'<path d="{b}" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff" stroke="#122F5E" stroke-width="1.5"/>{nahte}'
        f'<polygon points="{" ".join(f"{x:.2f},{y:.2f}" for x, y in pent)}" fill="none" stroke="#234E9E" stroke-width="1.2" stroke-linejoin="round"/>'
        '</svg>\n')


if __name__ == "__main__":
    basis = Path(__file__).with_name("static")
    zeichne(512).convert("RGB").save(basis / "icon-512.png")
    zeichne(192).convert("RGB").save(basis / "icon-192.png")
    zeichne(512, skala=0.82).convert("RGB").save(basis / "icon-maskable-512.png")
    zeichne(180).convert("RGB").save(basis / "icon-180.png")
    zeichne(96, skala=0.9, hintergrund=None, nur_b=True).save(basis / "badge-96.png")
    (basis / "icon.svg").write_text(svg(), encoding="utf-8")
    print("geschrieben: icon-512, icon-192, icon-maskable-512, icon-180, badge-96, icon.svg")
