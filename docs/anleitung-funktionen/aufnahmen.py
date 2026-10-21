"""Fotografiert die Demo-Instanz im Handy-Format (390 x 844, doppelte Auflösung).

Voraussetzung: demo_server.py läuft (Port 8299). Playwright mit dem installierten Chrome:
    py -m pip install playwright pillow reportlab
Start:   py docs/anleitung-funktionen/aufnahmen.py
Ergebnis: bilder/<nr>-<name>.png (werden von build_anleitung.py in die PDF gesetzt)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HIER = Path(__file__).resolve().parent
BILDER = HIER / "bilder"
URL = "http://127.0.0.1:8299/"
VIEWPORT = {"width": 390, "height": 844}

fehler: list[str] = []


def kontext(browser):
    return browser.new_context(viewport=VIEWPORT, device_scale_factor=2, is_mobile=True,
                               has_touch=True, service_workers="block",
                               locale="de-DE", timezone_id="Europe/Berlin")


def anmelden(browser, name: str, pin: str):
    page = kontext(browser).new_page()
    page.goto(URL)
    page.wait_for_selector("#login-name", state="visible", timeout=15000)
    page.fill("#login-name", name)
    page.fill("#login-pin", pin)
    page.click("#login-btn")
    page.wait_for_selector("#login-screen", state="hidden", timeout=20000)
    page.wait_for_timeout(1500)
    # Nach einem frischen Login bleibt die Verbindungsanzeige auf "offline" (die Abrufe vor dem
    # Login sind mit 401 gescheitert). Ein Neuladen, wie beim nächsten App-Start, setzt sie zurück.
    page.reload()
    page.wait_for_selector("#ladebalken", state="detached", timeout=20000)
    ruhe(page, 1200)
    return page


def ruhe(page, ms: int = 900):
    """Warten, bis die Verbindungsanzeige 'synchron' zeigt (sonst steht 'offline' im Bild).
    Bleibt sie rot, wird der Punkt angetippt - das erzwingt eine neue Prüfung."""
    page.wait_for_timeout(ms)
    for versuch in range(40):
        try:
            if "synchron" in page.inner_text("#sync-text").lower():
                page.wait_for_timeout(250)
                return True
            if versuch in (10, 20, 30):
                page.click("#server-punkt")
        except Exception:
            pass
        page.wait_for_timeout(250)
    print("  WARNUNG: Verbindungspunkt nicht grün")
    return False


def foto(page, name: str, ms: int = 900):
    ruhe(page, ms)
    page.screenshot(path=str(BILDER / f"{name}.png"))
    print("  ok ", name)


def ober(page, key: str):
    page.click(f'#tableiste button[data-ober="{key}"]')
    page.wait_for_timeout(500)


def unter(page, label: str):
    page.click(f'#subnav button:text-is("{label}")')
    page.wait_for_timeout(600)


def szene(name: str):
    """Dekorator: eine Szene darf scheitern, ohne die übrigen zu stoppen."""
    def deko(fn):
        def lauf(*a, **k):
            try:
                fn(*a, **k)
            except Exception as e:  # noqa: BLE001
                fehler.append(name)
                print("  FEHLER", name, "-", str(e).splitlines()[0][:140])
        return lauf
    return deko


def zeile_oeffnen(page, text: str):
    page.click(f'.wiki-zeile:has-text("{text}")')
    page.wait_for_timeout(700)


# ----------------------------------------------------------------------- Trainer
def trainer(browser):
    page = anmelden(browser, "Trainer", "1111")

    @szene("home")
    def _():
        foto(page, "02-home")
    _()

    @szene("ansehen-als")
    def _():
        page.select_option("#ansicht-select", label="Ansehen als: Lena"); page.wait_for_timeout(1500)
        foto(page, "02b-ansehen-als", 800)
        page.select_option("#ansicht-select", index=0); page.wait_for_timeout(1200)
    _()

    @szene("liga")
    def _():
        unter(page, "Liga"); foto(page, "03-liga", 1500)
    _()

    @szene("termine")
    def _():
        ober(page, "training"); unter(page, "Termine")
        foto(page, "04-termine", 1200)
        page.click("#tn-toggle"); page.wait_for_timeout(400)
        foto(page, "05-termin-neu")
        page.click("#tn-toggle"); page.wait_for_timeout(300)
    _()

    @szene("termin-aufgeklappt")
    def _():
        page.locator(".t-kopf").first.click(); page.wait_for_timeout(700)
        foto(page, "06-termin-aufgeklappt")
    _()

    @szene("termin-detail")
    def _():
        page.click('button:text-is("Öffnen & Plan")'); page.wait_for_timeout(1200)
        foto(page, "07-termin-detail")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        foto(page, "08-termin-detail-unten", 500)
    _()

    @szene("plan")
    def _():
        page.click('button:has-text("Plan bearbeiten")'); page.wait_for_timeout(900)
        foto(page, "09-plan")
        page.click('button:text-is("Fertig")'); page.wait_for_timeout(600)
    _()

    @szene("aufstellung")
    def _():
        ober(page, "training"); unter(page, "Aufstellung"); foto(page, "10-aufstellung", 1200)
    _()

    @szene("einteilung")
    def _():
        ober(page, "training"); unter(page, "Einteilung"); page.wait_for_timeout(800)
        page.select_option("#training-auswahl", index=1)      # Zusagen des nächsten Trainings übernehmen
        page.wait_for_timeout(600)
        page.evaluate("window.scrollTo(0, 0)")
        foto(page, "11-einteilung", 400)
        page.click("#btn-generieren"); page.wait_for_timeout(900)
        foto(page, "12-teams", 400)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        foto(page, "12b-teams-ergebnis", 400)
    _()

    @szene("uebungen")
    def _():
        unter(page, "Übungen"); foto(page, "13-uebungen")
    _()

    @szene("coach")
    def _():
        unter(page, "Coach"); foto(page, "14-coach")
    _()

    @szene("rangliste")
    def _():
        ober(page, "team"); unter(page, "Rangliste"); foto(page, "15-rangliste", 1200)
        page.locator(".rang-zeile").first.click(); page.wait_for_timeout(1000)
        foto(page, "15b-spieler-detail", 1000)
    _()

    @szene("kader")
    def _():
        unter(page, "Kader"); foto(page, "16-kader", 1200)
    _()

    @szene("team-statistik")
    def _():
        unter(page, "Statistik"); foto(page, "17-team-statistik")
    _()

    @szene("team-videos")
    def _():
        unter(page, "Videos"); foto(page, "18-team-videos", 1500)
    _()

    @szene("nutzung")
    def _():
        unter(page, "Nutzung"); foto(page, "19-nutzung", 1800)
    _()

    @szene("playbook")
    def _():
        ober(page, "taktik"); unter(page, "Playbook"); foto(page, "20-playbook")
        zeile_oeffnen(page, "Kreisel"); foto(page, "21-playbook-seite")
        page.locator('button:has-text("Bearbeiten"):visible').first.click(); page.wait_for_timeout(700)
        foto(page, "21b-seite-bearbeiten")
    _()

    @szene("gegner")
    def _():
        ober(page, "taktik"); unter(page, "Gegner"); foto(page, "22-gegner")
    _()

    @szene("saison")
    def _():
        ober(page, "saison"); unter(page, "Orga"); foto(page, "23-orga")
        unter(page, "Statistik Spiele"); foto(page, "24-statistik-spiele", 1500)
        unter(page, "Notizen"); foto(page, "25-notizen")
    _()


# --------------------------------------------------------------------- Spielerin
def spielerin(browser):
    page = anmelden(browser, "Lena", "2222")

    @szene("spielerin-home")
    def _():
        foto(page, "30-spielerin-home")
    _()

    @szene("spielerin-termin")
    def _():
        ober(page, "training"); unter(page, "Termine"); page.wait_for_timeout(800)
        page.locator(".t-kopf").first.click(); page.wait_for_timeout(700)
        foto(page, "31-spielerin-termine")
        page.locator(".rsvp-nein:visible").first.click(); page.wait_for_timeout(700)
        foto(page, "32-absage-grund", 400)
    _()

    @szene("profil")
    def _():
        ober(page, "ich"); unter(page, "Mein Profil"); foto(page, "33-profil", 1500)
    _()

    @szene("videos")
    def _():
        unter(page, "Videos"); foto(page, "34-videos", 1500)
        page.locator("#view-videos :text('HSG Beispielstadt'):visible").first.click(); page.wait_for_timeout(1500)
        foto(page, "35-analyse", 800)
    _()


if __name__ == "__main__":
    BILDER.mkdir(exist_ok=True)
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        # Anmeldebildschirm vor dem Login
        seite = kontext(browser).new_page()
        seite.goto(URL)
        seite.wait_for_selector("#login-name", state="visible", timeout=15000)
        seite.wait_for_timeout(600)
        seite.fill("#login-name", "Lena")
        seite.screenshot(path=str(BILDER / "01-login.png"))
        print("  ok  01-login")
        trainer(browser)
        spielerin(browser)
        browser.close()
    print(f"\nfertig in {time.time() - t0:.0f} s; Szenen mit Fehler: {fehler or 'keine'}")
    sys.exit(1 if fehler else 0)
