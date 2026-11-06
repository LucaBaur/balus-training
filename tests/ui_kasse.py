"""Ende-zu-Ende-Test der Mannschaftskasse im echten Browser (Chrome) gegen die Demo-Instanz.

Spielt den Ablauf durch, den kein anderer Test zusammen prueft (Formular, Token, Rollensicht):
  Trainer bucht eine Strafe und eine Teilzahlung -> Spielerin Lena sieht ihre Schuld, aber kein
  Buchungsformular -> Trainer storniert -> Kassenstand stimmt wieder.

    py tests/ui_kasse.py

Voraussetzung wie tests/ui_smoke.py (playwright + Chrome). Nicht Teil von deploy.sh.
"""
from __future__ import annotations

import re
import sys

from playwright.sync_api import sync_playwright

import ui_smoke as u

ergebnisse: list[str] = []


def pruefe(bedingung: bool, text: str):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        ergebnisse.append(text)


def inhalt(page) -> str:
    return page.inner_text("#kasse-inhalt").replace("\xa0", " ")


def kasse_oeffnen(page, ober: str):
    page.click(f'#tableiste button[data-ober="{ober}"]')
    page.wait_for_timeout(400)
    page.click('#subnav button:text-is("Kasse")')
    page.wait_for_selector(".kasse-stand", timeout=8000)
    page.wait_for_timeout(300)


def stand(text: str) -> str:
    """Die ersten Zeichen nach der Beschriftung „Kassenstand“ (die Seite zeigt sie per CSS in Grossbuchstaben)."""
    return re.split("kassenstand", text, maxsplit=1, flags=re.I)[1][:30]


def toast_text(page) -> str:
    return page.inner_text("#toast")


def formular_fuellen(page, betrag: str, text: str, spielerin: str | None = None):
    if not page.eval_on_selector(".kasse-neu", "e => e.open"):
        page.click(".kasse-neu summary")
    if spielerin:
        wert = page.evaluate("(n) => { const o = [...document.querySelectorAll('[data-k=spieler] option')]"
                             ".find(o => o.textContent.startsWith(n)); return o ? o.value : ''; }", spielerin)
        page.select_option('[data-k="spieler"]', wert)
    page.fill('[data-k="betrag"]', betrag)
    page.fill('[data-k="text"]', text)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    server = u.demo_starten()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)

            # ---- Trainer -------------------------------------------------------------------------------
            t = u.anmelden(browser, "Trainer", "1111")
            t.on("dialog", lambda d: d.accept())                     # „Wirklich stornieren?“
            kasse_oeffnen(t, "saison")
            pruefe("0,00 €" in inhalt(t) and "Noch keine Buchungen" in inhalt(t), "Trainer: leere Kasse, Stand 0,00 €")
            pruefe(t.query_selector(".kasse-neu") is not None, "Trainer sieht das Buchungsformular")

            t.click(".kasse-neu summary")
            t.select_option('[data-k="art"]', "ausgabe"); t.wait_for_timeout(200)
            pruefe(t.eval_on_selector(".kasse-neu", "e => e.open") and t.query_selector('[data-k="spieler"]') is None,
                   "Art wechseln: Formular bleibt offen, das Feld „Spielerin“ verschwindet bei Ausgaben")
            t.select_option('[data-k="art"]', "forderung"); t.wait_for_timeout(200)
            pruefe(t.query_selector('[data-k="spieler"]') is not None, "…und kommt bei Strafen zurück")
            t.select_option('[data-k="katalog"]', "treffpunkt_spaet"); t.wait_for_timeout(200)
            pruefe(t.input_value('[data-k="betrag"]') == "3,00" and "Spieltreffpunkt" in t.input_value('[data-k="text"]'),
                   "Strafenkatalog: Posten „je Minute“ füllt Text und Betrag vor")
            t.fill('[data-k="anzahl"]', "4"); t.wait_for_timeout(300)
            pruefe(t.input_value('[data-k="betrag"]') == "12,00" and "4 Min" in t.input_value('[data-k="text"]'),
                   "…Anzahl 4 ergibt 12,00 €")
            t.check('[data-k="trainer"]'); t.wait_for_timeout(300)
            pruefe(t.input_value('[data-k="betrag"]') == "24,00" and "Trainer" in t.input_value('[data-k="text"]'),
                   "…Haken „Trainer“ verdoppelt auf 24,00 €")
            t.select_option('[data-k="katalog"]', "bier_verschuettet"); t.wait_for_timeout(300)
            pruefe(t.input_value('[data-k="betrag"]') == "" and "Kasten" in inhalt(t),
                   "Kasten-Posten: Betrag bleibt leer, Hinweis zur Kasten-Umrechnung erscheint")
            t.select_option('[data-k="katalog"]', ""); t.fill('[data-k="text"]', ""); t.fill('[data-k="betrag"]', "")
            formular_fuellen(t, "abc", "Zu spät", "Lena")
            t.click("[data-kasse-buchen]"); t.wait_for_timeout(400)
            pruefe("Betrag" in toast_text(t) and "Noch keine Buchungen" in inhalt(t), "Unsinn im Betragsfeld: Hinweis, nichts gebucht")

            t.fill('[data-k="betrag"]', "5,00")
            t.click("[data-kasse-buchen]"); t.wait_for_selector(".kasse-zeile", timeout=8000); t.wait_for_timeout(300)
            s = inhalt(t)
            pruefe("Zu spät" in s and "5,00 €" in s and "Strafe / Beitrag" in s, "Strafe 5,00 € für Lena ist gebucht und steht in der Liste")
            pruefe("0,00 €" in stand(s), "Eine Forderung ändert den Kassenstand nicht (noch kein Geld)")
            pruefe("Lena" in s and "schuldet 5,00 €" in s, "Die Liste der offenen Strafen nennt Lena mit 5,00 €")

            t.click("[data-kasse-zahlt]"); t.wait_for_timeout(300)
            pruefe(t.input_value('[data-k="betrag"]') == "5,00" and t.input_value('[data-k="art"]') == "einzahlung"
                   and t.eval_on_selector(".kasse-neu", "e => e.open"),
                   "„Zahlung eintragen“ klappt das Formular auf und füllt Einzahlung und offenen Betrag vor")
            t.fill('[data-k="betrag"]', "2,00")
            t.click("[data-kasse-buchen]"); t.wait_for_timeout(900)
            s = inhalt(t)
            pruefe("2,00 €" in stand(s), "Teilzahlung 2,00 €: Kassenstand 2,00 €")
            pruefe("schuldet 3,00 €" in s, "…und Lena schuldet noch 3,00 €")

            # ---- Lena ----------------------------------------------------------------------------------
            l = u.anmelden(browser, "Lena", "2222")
            kasse_oeffnen(l, "mannschaft")
            s = inhalt(l)
            pruefe("Du schuldest der Kasse 3,00 €" in s, "Lena: „Du schuldest der Kasse 3,00 €“")
            pruefe(l.query_selector(".kasse-neu") is None and l.query_selector("[data-kasse-buchen]") is None,
                   "Lena sieht kein Buchungsformular")
            pruefe(l.query_selector("[data-kasse-storno]") is None and l.query_selector("[data-kasse-zahlt]") is None,
                   "Lena sieht weder Storno- noch „Zahlung eintragen“-Knöpfe")
            pruefe("Offene Strafen" in s and "Lena (du)" in s and "schuldet 3,00 €" in s,
                   "Lena sieht die Liste der offenen Strafen, sich selbst als „(du)“ markiert")
            pruefe("2,00 €" in stand(s), "Lena sieht denselben Kassenstand (2,00 €)")

            pruefe(l.query_selector(".kasse-katalog") is not None, "Lena sieht den Abschnitt „Strafenkatalog“")
            l.click(".kasse-katalog summary"); l.wait_for_timeout(200)
            k = l.inner_text(".kasse-katalog").replace(" ", " ")
            pruefe("Glatte Rote Karte" in k and "45,00 €" in k and "3,00 € je Min" in k and "Kasten" in k,
                   "…mit Posten, Preisen, „je Min“ und Kasten-Posten")

            # ---- Helferin: ehemalige Spielerin mit Amt sieht keine Zu-/Absage ---------------------------------
            def zusage_knoepfe(seite):
                seite.click('#tableiste button[data-ober="home"]'); seite.wait_for_timeout(1200)
                return (seite.eval_on_selector_all(".hero-rsvp button", "bs => bs.length"),
                        "Antwort fehlt noch" in seite.inner_text("#home-offen"))
            normal = zusage_knoepfe(l)
            pruefe(normal[0] > 0, "Kontrolle: Lena (im Kader) sieht auf Home die Zu-/Absage-Knöpfe")

            def als_helferin(route):
                antwort = route.fetch()
                daten = antwort.json(); daten["im_kader"] = False
                route.fulfill(response=antwort, json=daten)
            l.route("**/api/me", als_helferin)
            l.reload(); l.wait_for_selector("#ladebalken", state="detached", timeout=20000); l.wait_for_timeout(1500)
            h = zusage_knoepfe(l)
            pruefe(h[0] == 0 and not h[1], "Helferin (im_kader = false): keine Zu-/Absage-Knöpfe und keine „Antwort fehlt noch“-Karte")
            l.unroute("**/api/me")

            # ---- Trainer storniert ------------------------------------------------------------------
            t.click("[data-kasse-storno]:visible >> nth=0"); t.wait_for_timeout(900)
            s = inhalt(t)
            pruefe(t.query_selector(".kasse-zeile.storniert") is not None, "Stornierte Buchung bleibt sichtbar, durchgestrichen")
            pruefe("0,00 €" in stand(s) and "schuldet 5,00 €" in s,
                   "Nach dem Storno der Einzahlung: Stand 0,00 €, Lena schuldet wieder 5,00 €")
            browser.close()
    finally:
        if server:
            server.kill()

    for f in dict.fromkeys(u.fehler):
        print("  JS-/Netzfehler:", f)
    gesamt = len(ergebnisse) + len(u.fehler)
    print(f"\n{'alles ok' if not gesamt else str(gesamt) + ' Problem(e)'}")
    sys.exit(1 if gesamt else 0)


if __name__ == "__main__":
    main()
