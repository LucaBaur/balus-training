"""Baut Anleitung-Videos.pdf (4 Seiten: Überblick, Android, iPhone, Das findest du in der App).

Start:  py docs/anleitung-videos/build_anleitung.py
Die Bilder (login.png, ich-videos.png, ich-analyse.png, ich-statistik.png) liegen neben diesem Skript.
Es sind Screenshots einer lokalen Testinstanz mit Demo-Daten, keine echten Spielerdaten.
"""
import os
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

DOCS = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DOCS, "Anleitung-Videos.pdf")
URL = "https://homeserver.tail112520.ts.net/"
SEITEN = 4

pdfmetrics.registerFont(TTFont("Seg", r"C:\Windows\Fonts\segoeui.ttf"))
pdfmetrics.registerFont(TTFont("SegB", r"C:\Windows\Fonts\segoeuib.ttf"))
pdfmetrics.registerFontFamily("Seg", normal="Seg", bold="SegB")

BLAU = colors.HexColor("#234E9E")
DUNKEL = colors.HexColor("#142F5E")
ROT = colors.HexColor("#B3261E")
GRAU = colors.HexColor("#55657A")

W, H = A4
M = 18 * mm

body = ParagraphStyle("b", fontName="Seg", fontSize=11, leading=15.5, textColor=colors.HexColor("#1B2638"))
step = ParagraphStyle("st", parent=body, fontSize=11.5, leading=16)

c = canvas.Canvas(OUT, pagesize=A4)
c.setTitle("Anleitung: Balu's Training auf dem Handy")
c.setAuthor("TVG Frauen")


def kopf(titel, unter=None):
    c.setFillColor(DUNKEL)
    c.rect(0, H - 30 * mm, W, 30 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("SegB", 20)
    c.drawString(M, H - 16 * mm, titel)
    if unter:
        c.setFont("Seg", 10.5)
        c.setFillColor(colors.HexColor("#B9C8E3"))
        c.drawString(M, H - 23 * mm, unter)


def fuss(n):
    c.setFont("Seg", 8.5)
    c.setFillColor(GRAU)
    c.drawString(M, 10 * mm, "Balu's Training · TVG Frauen")
    c.drawRightString(W - M, 10 * mm, f"Seite {n} von {SEITEN}")


def ueberschrift(text, x, y, groesse=14):
    c.setFillColor(DUNKEL)
    c.setFont("SegB", groesse)
    c.drawString(x, y, text)


def absatz(text, x, y, breite, stil=body):
    p = Paragraph(text, stil)
    _, h = p.wrap(breite, 1000)
    p.drawOn(c, x, y - h)
    return y - h


def schritte(liste, x, y, breite):
    for i, t in enumerate(liste, 1):
        c.setFillColor(BLAU)
        c.circle(x + 4 * mm, y - 3.2 * mm, 4 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("SegB", 11)
        c.drawCentredString(x + 4 * mm, y - 5 * mm, str(i))
        y = absatz(t, x + 11 * mm, y, breite - 11 * mm, step) - 5 * mm
    return y


def bild(name, x, y_oben, breite):
    pfad = os.path.join(DOCS, name)
    im = Image.open(pfad)
    h = breite * im.height / im.width
    c.drawImage(pfad, x, y_oben - h, breite, h)
    c.setStrokeColor(colors.HexColor("#C9D3E2"))
    c.setLineWidth(0.8)
    c.rect(x, y_oben - h, breite, h, stroke=1, fill=0)
    return h


def bildunterschrift(text, x_mitte, y):
    c.setFont("Seg", 8.5)
    c.setFillColor(GRAU)
    c.drawCentredString(x_mitte, y, text)


def qrcode(x, y, groesse):
    w = qr.QrCodeWidget(URL)
    b = w.getBounds()
    d = Drawing(groesse, groesse, transform=[groesse / (b[2] - b[0]), 0, 0, groesse / (b[3] - b[1]), 0, 0])
    d.add(w)
    renderPDF.draw(d, c, x, y)


def anmelde_bild(y_oben):
    breite = 62 * mm
    h = bild("login.png", W - M - breite, y_oben, breite)
    bildunterschrift("So sieht die Anmeldung aus", W - M - breite / 2, y_oben - h - 4 * mm)


# ---------------------------------------------------------------- Seite 1 ----
kopf("Balu's Training auf dem Handy", "Anleitung für Android und iPhone")

bx, by, bw, bh = M, H - 78 * mm, W - 2 * M, 40 * mm
c.setFillColor(colors.HexColor("#FDECEA"))
c.setStrokeColor(ROT)
c.setLineWidth(1.2)
c.roundRect(bx, by, bw, bh, 3 * mm, stroke=1, fill=1)
c.setFillColor(ROT)
c.setFont("SegB", 13)
c.drawString(bx + 6 * mm, by + bh - 9 * mm, "Wichtig: Die App ist noch nicht im Alltag im Einsatz")
absatz("Wir nutzen sie zunächst nur für die <b>Videoanalyse</b>: Hier siehst du die Spiele und die "
       "Szenen, in denen du vorkommst.<br/><b>Zu- und Absagen zum Training laufen "
       "weiter über SpielerPlus.</b> Bitte sag in der App nichts zu oder ab.",
       bx + 6 * mm, by + bh - 13 * mm, bw - 12 * mm)

y = by - 12 * mm
ueberschrift("Was du brauchst", M, y)
y = absatz("• Ein Handy mit Internet (WLAN oder Mobilfunk)<br/>"
           "• Deinen <b>Namen</b> und deine <b>PIN</b>, die du vom Trainer bekommen hast<br/>"
           "• Auf dem iPhone den Browser <b>Safari</b>, auf Android den Browser <b>Chrome</b>",
           M, y - 3 * mm, W - 2 * M - 50 * mm)

qrcode(W - M - 36 * mm, y - 8 * mm, 36 * mm)
bildunterschrift("Mit der Handykamera scannen", W - M - 18 * mm, y - 12 * mm)

y = y - 22 * mm
ueberschrift("Die Adresse der App", M, y)
y = absatz(f"<font name='SegB' size='13' color='#234E9E'>{URL}</font>", M, y - 3 * mm, W - 2 * M)
y = absatz("Du kannst die Adresse direkt im Browser eingeben oder den Code oben scannen. "
           "Danach legst du die App wie unten beschrieben als Symbol auf deinen Startbildschirm, "
           "dann öffnet sie sich wie jede andere App.", M, y - 3 * mm, W - 2 * M)

y -= 10 * mm
ueberschrift("Der Ablauf in drei Schritten", M, y)
y = schritte([
    "<b>Adresse öffnen</b> (Seite 2 für Android, Seite 3 für iPhone)",
    "<b>Auf den Startbildschirm legen</b>, damit du die App mit einem Tippen findest",
    "<b>Mit Namen und PIN anmelden</b>. Das musst du nur einmal tun, du bleibst danach angemeldet",
], M, y - 4 * mm, W - 2 * M)
absatz("Was du in der App findest, steht auf Seite 4.", M, y - 2 * mm, W - 2 * M)
fuss(1)
c.showPage()

# ---------------------------------------------------------------- Seite 2 ----
kopf("Android", "Mit dem Browser Chrome")
y = H - 42 * mm
y = schritte([
    f"Öffne <b>Chrome</b> und gib die Adresse ein:<br/><font name='SegB' color='#234E9E'>{URL}</font>",
    "Tippe oben rechts auf die <b>drei Punkte</b> (Menü).",
    "Wähle <b>„App installieren“</b>. Bei manchen Handys heißt der Punkt "
    "<b>„Zum Startbildschirm hinzufügen“</b>.",
    "Bestätige mit <b>„Installieren“</b> bzw. <b>„Hinzufügen“</b>. Das Symbol liegt jetzt auf deinem Startbildschirm.",
    "Öffne die App über das Symbol und <b>melde dich an</b> (Name und PIN).",
], M, y, 105 * mm)
anmelde_bild(H - 40 * mm)

y = min(y, H - 130 * mm) - 6 * mm
ueberschrift("Wenn etwas nicht klappt", M, y, 13)
absatz("• <b>Kein „App installieren“ im Menü?</b> Dann bist du nicht in Chrome (z. B. in einer anderen "
       "App geöffnet). Kopiere die Adresse und öffne sie direkt in Chrome.<br/>"
       "• <b>Du siehst die Adressleiste weiter?</b> Dann hast du nur ein Lesezeichen gesetzt. "
       "Das funktioniert auch, die App läuft dann aber im Browserfenster.<br/>"
       "• Es klappt gar nicht? Melde dich beim Trainer, dann schauen wir gemeinsam.",
       M, y - 3 * mm, W - 2 * M)
fuss(2)
c.showPage()

# ---------------------------------------------------------------- Seite 3 ----
kopf("iPhone", "Mit dem Browser Safari (nicht Chrome)")
y = H - 42 * mm
y = schritte([
    f"Öffne <b>Safari</b> und gib die Adresse ein:<br/><font name='SegB' color='#234E9E'>{URL}</font>",
    "Tippe unten auf das <b>Teilen-Symbol</b> (Quadrat mit Pfeil nach oben).",
    "Scrolle in der Liste etwas nach unten und wähle <b>„Zum Home-Bildschirm“</b>.",
    "Tippe oben rechts auf <b>„Hinzufügen“</b>. Das Symbol liegt jetzt auf deinem Home-Bildschirm.",
    "Öffne die App über das Symbol und <b>melde dich an</b> (Name und PIN).",
], M, y, 105 * mm)
anmelde_bild(H - 40 * mm)

y = min(y, H - 130 * mm) - 6 * mm
ueberschrift("Wenn etwas nicht klappt", M, y, 13)
absatz("• <b>Kein „Zum Home-Bildschirm“ in der Liste?</b> Dann bist du nicht in Safari (z. B. in einer anderen "
       "App geöffnet). Kopiere die Adresse und öffne sie direkt in Safari.<br/>"
       "• Es klappt gar nicht? Melde dich beim Trainer, dann schauen wir gemeinsam.",
       M, y - 3 * mm, W - 2 * M)
fuss(3)
c.showPage()

# ---------------------------------------------------------------- Seite 4 ----
kopf("Das findest du in der App", "Nach der Anmeldung siehst du unten vier Reiter")
y = H - 40 * mm
y = absatz("<b>Home</b>: die Startseite.<br/>"
           "<b>Ich</b>: dein Profil mit Beteiligung, Laufchallenge und einer kurzen <b>Spielstatistik</b>. "
           "Unter <b>„Videos“</b> stehen die Spiele, zum Beispiel HSG Oberkochen. Tippe ein Spiel an, "
           "dann siehst du die <b>Videoanalyse</b>: oben „Ganzes Spiel ansehen“, darunter deine Szenen als kurze Clips.<br/>"
           "<b>Training</b>: die Termine. Zu- und Absagen bitte weiter in <b>SpielerPlus</b>.<br/>"
           "<b>Taktik</b>: das Playbook mit den Spielzügen.",
           M, y, W - 2 * M)

bw_ = 52 * mm
luecke = (W - 2 * M - 3 * bw_) / 2
oben = y - 8 * mm
h1 = bild("ich-videos.png", M, oben, bw_)
bild("ich-analyse.png", M + bw_ + luecke, oben, bw_)
h3 = bild("ich-statistik.png", M + 2 * (bw_ + luecke), oben, bw_)
bildunterschrift("Ich → Videos", M + bw_ / 2, oben - h1 - 4 * mm)
bildunterschrift("Tipp auf das Spiel: Videoanalyse", M + bw_ + luecke + bw_ / 2, oben - h1 - 4 * mm)
bildunterschrift("Ich → Mein Profil: Statistik", M + 2 * (bw_ + luecke) + bw_ / 2, oben - h3 - 4 * mm)
absatz("Die Statistik im Profil zeigt je Spiel kurz deine Zahlen und darunter die Summe. "
       "Ein Tipp auf ein Spiel führt zur Videoanalyse.",
       M + 2 * (bw_ + luecke), oben - h3 - 9 * mm, bw_,
       ParagraphStyle("k", parent=body, fontSize=9, leading=12, textColor=GRAU))

yh = oben - h1 - 14 * mm
ueberschrift("Häufige Fragen", M, yh, 13)
absatz("• <b>Der Reiter „Ich“ fehlt?</b> Tippe oben rechts auf <b>„synchron“</b>. Die App gleicht sich dann mit "
       "dem Server ab. Hilft das nicht, melde dich beim Trainer.<br/>"
       "• <b>„Keine Szenen für dich“?</b> Dann wurden in diesem Spiel keine Aktionen von dir erfasst. "
       "Das ganze Spiel kannst du trotzdem ansehen.<br/>"
       "• <b>PIN vergessen oder drei Fehlversuche?</b> Nach drei falschen Eingaben sperrt sich die PIN. "
       "Der Trainer gibt dir eine neue.<br/>"
       "• <b>Kein Netz in der Halle?</b> Die App startet auch ohne Netz, Videos brauchen aber Internet.",
       M, yh - 3 * mm, W - 2 * M)
fuss(4)
c.showPage()
c.save()
print("ok", OUT)
