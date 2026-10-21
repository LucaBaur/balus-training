"""Baut Anleitung-Funktionen.pdf: alle Funktionen der App, gezeigt auf dem Handy.

Ablauf (aus dem Projektordner):
    py docs/anleitung-funktionen/demo_server.py      # Demo-Instanz mit erfundenen Daten
    py docs/anleitung-funktionen/aufnahmen.py        # Screenshots nach bilder/
    py docs/anleitung-funktionen/pdf_bauen.py        # PDF zusammensetzen

Die Bilder zeigen eine Testinstanz mit erfundenen Namen, keine echten Spielerdaten.
Benötigt: pip install pillow reportlab. Die Schrift Segoe UI ist unter Windows vorhanden,
sonst nimmt das Skript Helvetica.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

HIER = Path(__file__).resolve().parent
BILDER = HIER / "bilder"
OUT = HIER / "Anleitung-Funktionen.pdf"
TMP = Path(tempfile.mkdtemp(prefix="balu_rahmen_"))

# --------------------------------------------------------------------- Schrift
FONT, FONT_B = "Helvetica", "Helvetica-Bold"
try:
    pdfmetrics.registerFont(TTFont("Seg", r"C:\Windows\Fonts\segoeui.ttf"))
    pdfmetrics.registerFont(TTFont("SegB", r"C:\Windows\Fonts\segoeuib.ttf"))
    pdfmetrics.registerFontFamily("Seg", normal="Seg", bold="SegB")
    FONT, FONT_B = "Seg", "SegB"
except Exception:  # noqa: BLE001
    pass

BLAU = colors.HexColor("#234E9E")
DUNKEL = colors.HexColor("#142F5E")
GRAU = colors.HexColor("#55657A")
HELL = colors.HexColor("#EDF3F9")
OCKER = colors.HexColor("#B7791F")
TEXT = colors.HexColor("#1B2638")

W, H = A4
M = 14 * mm

body = ParagraphStyle("b", fontName=FONT, fontSize=10.5, leading=14.5, textColor=TEXT)
klein = ParagraphStyle("k", parent=body, fontSize=9.8, leading=13.4)
fett = ParagraphStyle("f", parent=body, fontName=FONT_B, fontSize=10.5, leading=13.5, textColor=DUNKEL)


# ----------------------------------------------------------------- Handy-Rahmen
def handy(name: str) -> Path:
    """Screenshot in ein Handy-Gehäuse setzen (abgerundet, Schatten) -> JPEG auf Weiß."""
    ziel = TMP / (name + ".jpg")
    if ziel.exists():
        return ziel
    bild = Image.open(BILDER / f"{name}.png").convert("RGB")
    sw, sh = bild.size
    rand, schatten = 22, 46
    ow, oh = sw + 2 * rand, sh + 2 * rand
    leinwand = Image.new("RGBA", (ow + 2 * schatten, oh + 2 * schatten), (255, 255, 255, 0))

    sch = Image.new("RGBA", leinwand.size, (0, 0, 0, 0))
    ImageDraw.Draw(sch).rounded_rectangle(
        (schatten, schatten + 14, schatten + ow, schatten + oh + 14), 96, fill=(20, 40, 80, 120))
    leinwand.alpha_composite(sch.filter(ImageFilter.GaussianBlur(20)))

    ImageDraw.Draw(leinwand).rounded_rectangle(
        (schatten, schatten, schatten + ow, schatten + oh), 96, fill=(17, 21, 28, 255))
    maske = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(maske).rounded_rectangle((0, 0, sw, sh), 74, fill=255)
    leinwand.paste(bild, (schatten + rand, schatten + rand), maske)

    weiss = Image.new("RGB", leinwand.size, "white")
    weiss.paste(leinwand, mask=leinwand.split()[3])
    weiss.save(ziel, quality=88)
    return ziel


# ------------------------------------------------------------------- Seitenbau
c = None
seite = 0
GESAMT = 0


def neue_seite():
    global seite
    if seite:
        fuss(GESAMT)
        c.showPage()
    seite += 1


def kopf(titel: str, wer: str | None = None):
    c.setFillColor(DUNKEL)
    c.rect(0, H - 24 * mm, W, 24 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(FONT_B, 19)
    c.drawString(M, H - 15 * mm, titel)
    if wer:
        c.setFont(FONT_B, 9)
        tw = c.stringWidth(wer, FONT_B, 9)
        c.setFillColor(colors.HexColor("#B9C8E3"))
        c.roundRect(W - M - tw - 8 * mm, H - 17.5 * mm, tw + 8 * mm, 7 * mm, 3.5 * mm, stroke=0, fill=1)
        c.setFillColor(DUNKEL)
        c.drawString(W - M - tw - 4 * mm, H - 15.1 * mm, wer)


def fuss(gesamt: int):
    c.setFont(FONT, 8.5)
    c.setFillColor(GRAU)
    c.drawString(M, 9 * mm, "Balu's Training · TVG Frauen · Anleitung")
    c.drawRightString(W - M, 9 * mm, f"Seite {seite} von {gesamt}")


def absatz(text: str, x: float, y: float, breite: float, stil=body) -> float:
    p = Paragraph(text, stil)
    _, h = p.wrap(breite, 1000)
    p.drawOn(c, x, y - h)
    return y - h


def bildseite(titel: str, wer: str, einleitung: str, bilder: list[tuple[str, str, str]]):
    """Eine Seite: Einleitung oben, darunter 2 oder 3 Handys mit Nummer, Titel und Text."""
    neue_seite()
    kopf(titel, wer)
    # Block (Einleitung + Handys + Bildtexte) senkrecht in die freie Fläche setzen
    intro_h = Paragraph(einleitung, body).wrap(W - 2 * M, 1000)[1]
    pw = Image.open(handy(bilder[0][0])).size
    block = intro_h + 10 * mm + 61 * mm * pw[1] / pw[0] + 4 * mm + 38 * mm
    frei = (H - 24 * mm - 16 * mm) - block
    y = absatz(einleitung, M, H - 33 * mm - max(frei, 0) * 0.35, W - 2 * M)
    n = len(bilder)
    spalte = (W - 2 * M) / 3
    breite_handy = 61 * mm
    x0 = M + (3 - n) * spalte / 2
    top = y - 10 * mm
    for i, (name, kopfzeile, text) in enumerate(bilder):
        pfad = handy(name)
        iw, ih = Image.open(pfad).size
        hoehe = breite_handy * ih / iw
        cx = x0 + spalte * i + spalte / 2
        c.drawImage(str(pfad), cx - breite_handy / 2, top - hoehe, breite_handy, hoehe)
        by = top - hoehe - 4 * mm
        c.setFillColor(BLAU)
        c.circle(x0 + spalte * i + 5.2 * mm, by - 2.2 * mm, 3.2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(FONT_B, 9.5)
        c.drawCentredString(x0 + spalte * i + 5.2 * mm, by - 3.5 * mm, str(i + 1))
        tx = x0 + spalte * i + 10.5 * mm
        tb = spalte - 12 * mm
        yy = absatz(kopfzeile, tx, by + 0.6 * mm, tb, fett)
        absatz(text, tx, yy - 1 * mm, tb, klein)


def textseite(titel: str, wer: str, bloecke: list[tuple[str, str]]):
    neue_seite()
    kopf(titel, wer)
    y = H - 34 * mm
    for ueber, text in bloecke:
        y = absatz(ueber, M, y, W - 2 * M, fett) - 1.5 * mm
        y = absatz(text, M, y, W - 2 * M) - 6 * mm


# -------------------------------------------------------------------- Inhalt
def titelseite():
    neue_seite()
    c.setFillColor(DUNKEL)
    c.rect(0, H - 58 * mm, W, 58 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(FONT_B, 30)
    c.drawString(M, H - 28 * mm, "Balu's Training")
    c.setFont(FONT, 14)
    c.setFillColor(colors.HexColor("#B9C8E3"))
    c.drawString(M, H - 38 * mm, "Alle Funktionen der App, so wie sie auf dem Handy aussehen")
    c.setFont(FONT, 10)
    c.drawString(M, H - 49 * mm, "TVG Frauen · Stand: Version 0.55")

    y = absatz(
        "Balu's Training ist die App fürs Team: Zu- und Absagen fürs Training, der Trainingsplan, "
        "das Playbook, die Videoanalyse der Spiele und faire Teams für die Trainingsspiele. "
        "Du brauchst sie auf dem Handy, installiert wird sie wie eine normale App "
        "(siehe <b>Anleitung-Videos.pdf</b>). Diese Anleitung zeigt jeden Bereich Schritt für Schritt.",
        M, H - 68 * mm, W - 2 * M)

    pfad = handy("02-home")
    iw, ih = Image.open(pfad).size
    bw = 66 * mm
    bh = bw * ih / iw
    c.drawImage(str(pfad), W - M - bw + 4 * mm, y - 6 * mm - bh, bw, bh)

    zeilen = [
        ("Home", "Nächstes Training, nächste Spiele, Liga-Tabelle", "alle"),
        ("Ich", "Dein Profil, deine Statistik, Videos", "alle mit Profil"),
        ("Training", "Termine, Zu- und Absagen, Plan, Aufstellung, Teams", "alle, Plan und Teams nur Trainer"),
        ("Team", "Rangliste, Kader, Statistik, Nutzung", "nur Trainer"),
        ("Taktik", "Playbook, Gegnercheck", "alle, Gegner nur Trainer"),
        ("Saison", "Orga, Statistik der Spiele, Notizen", "nur Trainer"),
    ]
    yy = y - 8 * mm
    tb = W - 2 * M - bw - 4 * mm
    absatz("Die sechs Bereiche unten in der App", M, yy, tb, fett)
    yy -= 8 * mm
    for name, was, wer in zeilen:
        yy = absatz(f"<b>{name}</b><br/>{was}", M, yy, tb, klein) - 0.8 * mm
        yy = absatz(f"<font color='#55657A'>{wer}</font>", M, yy, tb, klein) - 3.6 * mm
    absatz("<b>Wer sieht was?</b> Trainer sehen alles. Spielerinnen sehen ihre eigenen Sachen, das Playbook "
           "und die Termine. Spielerinnen sehen keine ELO-Werte und keine Rangliste.",
           M, yy - 4 * mm, tb, klein)
    c.setFont(FONT, 8.5)
    c.setFillColor(GRAU)
    c.drawString(M, 14 * mm, "Alle Bilder zeigen eine Testinstanz mit erfundenen Namen.")


def baue():
    titelseite()

    bildseite("Anmelden und zurechtfinden", "Alle",
              "Du meldest dich mit deinem Namen und der PIN an, die du vom Trainerteam bekommen hast. "
              "Danach bleibst du angemeldet. Unten wechselst du zwischen den Bereichen, "
              "oben unter dem Wappen zwischen den Seiten des Bereichs.",
              [("01-login", "Anmelden", "Name und PIN eingeben. Dein Zugang gehört zu deinem Spielerprofil, "
                "du siehst nur, was für dich bestimmt ist."),
               ("02-home", "Home", "Das nächste Training und die nächsten Spiele. Der Punkt oben rechts zeigt, "
                "ob die App mit dem Server verbunden ist. Ohne Netz bleibt sie benutzbar."),
               ("03-liga", "Liga", "Tabelle und Spielplan der Bezirksoberliga. Die Daten kommen vom Verband, "
                "unser Team ist hervorgehoben.")])

    bildseite("Termine", "Alle, Anlegen nur Trainer",
              "Unter <b>Training → Termine</b> stehen alle kommenden Trainings, Testspiele und Ligaspiele. "
              "Trainings sind weiß, Spiele farbig. Der Balken zeigt die Zusagen. "
              "Die Trainings am Montag und Donnerstag legt die App selbst an, du musst nichts eintragen.",
              [("04-termine", "Terminliste", "Rechts steht die Zahl der Zusagen. Die Warnung oben erscheint, "
                "wenn bei einem Termin weniger als sechs zugesagt haben."),
               ("06-termin-aufgeklappt", "Aufklappen", "Ein Tipp auf den Termin zeigt, wer zu- und abgesagt hat. "
                "Trainer tragen hier für andere ein: Haken = zusagen, Fragezeichen = unsicher, Kreuz = absagen."),
               ("05-termin-neu", "Neuer Termin", "Trainer legen Trainings, Testspiele und Ligaspiele von Hand an. "
                "Bei Spielen kommen Gegner, Heim oder Auswärts und die Abfahrt dazu.")])

    bildseite("Training vorbereiten", "Trainer",
              "Mit <b>Öffnen &amp; Plan</b> in einem Termin kommst du in die Detailansicht. "
              "Dort siehst du auf einen Blick, wer kommt, schickst Erinnerungen und schreibst den Trainingsplan.",
              [("07-termin-detail", "Wer kommt?", "Alle Spielerinnen nach Antwort sortiert. Ein kleiner Stift "
                "zeigt, dass du die Antwort selbst eingetragen hast."),
               ("08-termin-detail-unten", "Erinnern und aktualisieren", "„Erinnerung an Offene senden“ schickt eine "
                "Mitteilung an alle ohne Antwort. „Aus SpielerPlus aktualisieren“ holt den neuesten Stand sofort."),
               ("09-plan", "Plan schreiben", "Der Plan besteht aus Blöcken mit Titel, Notiz und Dauer. "
                "Mit den Pfeilen sortierst du sie um. Spielerinnen sehen den Plan nicht.")])

    bildseite("Zu- und Absagen", "Spielerinnen",
              "Zu- und Absage gehören zu den wichtigsten Dingen in der App. Antworten kannst du auf der Startseite "
              "oder im Termin. Die Antwort sehen alle, damit der Trainer planen kann.",
              [("30-spielerin-home", "Auf der Startseite", "Wo deine Antwort noch fehlt, steht sie unter "
                "„Deine Antwort fehlt noch“ mit drei Knöpfen."),
               ("31-spielerin-termine", "Im Termin", "Oben deine Antwort, darunter alle anderen nach "
                "Zusage, Unsicher, Absage und noch keine Rückmeldung."),
               ("32-absage-grund", "Absagen mit Grund", "Bei einer Absage wählst du einen Grund oder schreibst "
                "einen eigenen. Ohne Grund geht die Absage nicht raus.")])

    bildseite("Aufstellung und Teams", "Trainer",
              "Aus den Zusagen entsteht die Aufstellung auf dem Spielfeld. Für Trainingsspiele "
              "teilt die App die Anwesenden in möglichst gleich starke Teams.",
              [("10-aufstellung", "Aufstellung", "Alle Zusagen stehen auf ihrer Position. So siehst du sofort, "
                "wo es dünn wird. Oben wechselst du zwischen Training und Spiel und zwischen Portraits und Namen."),
               ("11-einteilung", "Wer ist da?", "Hake die Anwesenden an. Die ELO-Werte siehst nur du als Trainer."),
               ("12-teams", "Teams bilden", "Mit 2, 3 oder 4 Teams. Die Spielstärke wird gleich verteilt, "
                "Torhüterinnen werden aufgeteilt. Antippen schiebt eine Spielerin ins nächste Team.")])

    bildseite("Ergebnis, Übungen und Coach", "Trainer",
              "Nach dem Spiel trägst du das Ergebnis ein. Beim Planen helfen dir die Übungssammlung "
              "und der Coach, der aus deiner Beschreibung einen Plan vorschlägt.",
              [("12b-teams-ergebnis", "Ergebnis eintragen", "Tippe auf das Team, das gewonnen hat, oder auf "
                "Unentschieden. Die ELO-Werte ändern sich, ein Spiel lässt sich rückgängig machen."),
               ("13-uebungen", "Übungen", "Die Sammlung eurer Übungen. Beim Planen übernimmst du sie als Block."),
               ("14-coach", "Coach", "Beschreibe das Training, getippt oder per Sprachnachricht. Der Coach fragt "
                "nach, wenn etwas fehlt, und hängt den Plan auf Wunsch direkt ans Training.")])

    bildseite("Mein Profil und Videos", "Spielerinnen",
              "Unter <b>Ich</b> findest du alles zu dir selbst. Du siehst nur deine eigenen Zahlen und deine eigenen Szenen.",
              [("33-profil", "Mein Profil", "Deine Trainingsbeteiligung, die Laufchallenge und deine Statistik "
                "aus den analysierten Spielen."),
               ("34-videos", "Videos", "Oben die Spiele mit Videoanalyse, darunter einzelne Szenen als kurze Clips."),
               ("35-analyse", "Videoanalyse", "Deine Tore, Fehlwürfe und Vorlagen im Spiel. Spielzüge sind mit einer "
                "Ampel bewertet. Ein Tipp auf eine Szene spielt den Clip ab.")])

    bildseite("Team: Rangliste und Kader", "Trainer",
              "Der Bereich <b>Team</b> ist nur für das Trainerteam. Spielerinnen sehen weder ELO-Werte noch die Rangliste.",
              [("15-rangliste", "Rangliste", "Alle Spielerinnen nach ELO. Ein Tipp öffnet den Verlauf."),
               ("15b-spieler-detail", "Verlauf einer Spielerin", "Bilanz, Siegesserie, Höchststand, "
                "Trainingsbeteiligung und alle Spiele mit ihrer ELO-Änderung."),
               ("16-kader", "Kader", "Spielerinnen anlegen, Stärkestufe und Positionen pflegen oder "
                "jemanden auf inaktiv setzen. Mehrere Positionen sind möglich.")])

    bildseite("Team: Statistik, Videos und Nutzung", "Trainer",
              "Weitere Seiten im Bereich Team: eigene Statistik-Notizen, Szenen-Clips und die Übersicht, "
              "wer die App nutzt.",
              [("17-team-statistik", "Statistik", "Freie Seiten für Auswertungen, die ihr festhalten wollt."),
               ("18-team-videos", "Videos", "Einzelne Szenen als kurze Clips, jeweils einer oder mehreren "
                "Spielerinnen zugeordnet. Sie werden am PC geschnitten und hochgeladen."),
               ("19-nutzung", "Nutzung", "Wer war wann in der App, mit welchem Gerät und welcher Version. "
                "Fehler werden gesammelt. IP-Adresse und Standort werden nicht gespeichert.")])

    bildseite("Taktik: Playbook", "Alle, Bearbeiten nur Trainer",
              "Das Playbook ist euer Wissen zu Spielzügen, Überzahl, Unterzahl und Abwehr. "
              "Die Seiten sind als Baum geordnet, alle Spielerinnen können sie lesen.",
              [("20-playbook", "Playbook", "Eine Gruppe wie „Allgemeine Spielzüge“ klappt auf. "
                "Die Zahl zeigt, wie viele Unterseiten dazugehören."),
               ("21-playbook-seite", "Seite lesen", "Zum Spielzug steht, gegen welche Abwehr er gedacht ist, "
                "und die Schritte nacheinander."),
               ("21b-seite-bearbeiten", "Bearbeiten", "Trainer ändern den Text direkt in der App. "
                "Das geht auch ohne Netz, die Änderung wird danach nachgesendet.")])

    bildseite("Gegnercheck, Orga und Notizen", "Trainer",
              "Drei weitere Sammlungen für das Trainerteam. Die Seiten funktionieren wie im Playbook: "
              "anlegen, bearbeiten, löschen.",
              [("22-gegner", "Gegnercheck", "Eine Seite je Gegner: wie sie verteidigen und worauf ihr achten sollt. "
                "Unter Taktik → Gegner."),
               ("23-orga", "Saison und Orga", "Hallenzeiten, Termine und alles, was die Saison betrifft. "
                "Unter Saison → Orga."),
               ("25-notizen", "Notizen", "Besprechungen und Notizen des Trainerteams. Unter Saison → Notizen.")])

    bildseite("Spielstatistik und Ansehen als", "Trainer",
              "Für jedes analysierte Spiel gibt es eine Auswertung. Und du kannst die App so ansehen, "
              "wie sie eine bestimmte Spielerin sieht.",
              [("24-statistik-spiele", "Statistik Spiele", "Angriffs- und Wurfeffektivität, die Spielzüge "
                "mit Anteil gut, mittel und schlecht, dazu jede Spielerin einzeln und nach Position."),
               ("02b-ansehen-als", "Ansehen als", "Oben auf Home wählst du „Ansehen als: Name“. Ein Balken erinnert dich "
                "daran. Mit „zurück zu Trainer“ bist du wieder du.")])

    textseite("Wie die Zu- und Absagen zusammenkommen", "Trainer", [
        ("Wer kann antworten?",
         "Jede Spielerin kann in der App selbst zu- oder absagen. Als Trainer kannst du außerdem für andere eintragen, "
         "zum Beispiel wenn jemand am Telefon oder per Nachricht absagt. Diese Einträge sind mit einem kleinen Stift markiert."),
        ("Was holt die App aus SpielerPlus?",
         "Solange das Team SpielerPlus noch nutzt, holt der Server die Zu- und Absagen von dort. "
         "Das passiert jeden Morgen und an Trainingstagen um 12:00, 16:00 und 18:30 Uhr. "
         "Mit „Aus SpielerPlus aktualisieren“ im Termin geht es auch sofort."),
        ("Was gilt, wenn sich Angaben widersprechen?",
         "Die App gewinnt. Was eine Spielerin selbst in der App antwortet oder was du als Trainer einträgst, "
         "überschreibt SpielerPlus nie. SpielerPlus füllt nur Lücken und aktualisiert Antworten, "
         "die selbst von dort stammen. Die Daten gehen nur in eine Richtung: von SpielerPlus in die App."),
        ("Wann entstehen die Trainings?",
         "Jeden Morgen legt die App die Trainings der nächsten 14 Tage selbst an: "
         "Montag 20:00 Uhr in Gerhausen und Donnerstag 20:15 Uhr in Blaubeuren. "
         "Änderungen an Titel, Uhrzeit oder Ort, die du von Hand machst, bleiben stehen."),
        ("Und wenn etwas nicht stimmt?",
         "Fehlt eine Spielerin in der Liste oder stimmt eine Antwort nicht, trag sie im Termin selbst ein. "
         "Die Version der App steht oben rechts neben dem Verbindungspunkt. Was sich in welcher Version geändert hat, "
         "steht im Changelog."),
    ])


def lauf(ziel) -> int:
    """Eine komplette Runde. Die erste zählt nur die Seiten (für 'Seite x von y')."""
    global c, seite
    c = canvas.Canvas(ziel, pagesize=A4)
    c.setTitle("Balu's Training – Anleitung: alle Funktionen")
    c.setAuthor("TVG Frauen")
    seite = 0
    baue()
    fuss(GESAMT)
    c.save()
    return seite


if __name__ == "__main__":
    import io
    GESAMT = lauf(io.BytesIO())
    lauf(str(OUT))
    print(f"{OUT.name}: {seite} Seiten, {OUT.stat().st_size / 1e6:.1f} MB")
