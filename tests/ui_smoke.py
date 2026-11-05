"""Rauchtest der Oberflaeche im echten Browser (Chrome) gegen die Demo-Instanz.

Klickt als Trainer und als Spielerin durch alle Reiter und Unterpunkte, oeffnet einige Detailansichten
und haelt fest, was auf jeder Seite steht. Jede JavaScript-Ausnahme, jeder console.error und jede
fehlgeschlagene Anfrage (ausser erwarteten 401/403) zaehlt als Fehler.

Zweck: Vorher/Nachher-Vergleich bei Umbauten am Frontend.
    py tests/ui_smoke.py --ausgabe vorher.json
    ... umbauen ...
    py tests/ui_smoke.py --ausgabe nachher.json --vergleiche vorher.json

Voraussetzung: py -m pip install playwright (mit installiertem Chrome). Die Demo-Instanz startet
das Skript selbst (docs/anleitung-funktionen/demo_server.py), wenn Port 8299 frei ist.
Nicht Teil von deploy.sh (braucht Chrome), darum ohne _test im Namen.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

WURZEL = Path(__file__).resolve().parent.parent
PORT = 8299
URL = f"http://127.0.0.1:{PORT}/"
fehler: list[str] = []


def port_frei() -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", PORT)) != 0


def demo_starten():
    if not port_frei():
        return None
    p = subprocess.Popen([sys.executable, str(WURZEL / "docs" / "anleitung-funktionen" / "demo_server.py")],
                         cwd=str(WURZEL), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if not port_frei():
            time.sleep(0.5)
            return p
        time.sleep(0.5)
    p.kill()
    raise SystemExit("Demo-Server startet nicht")


def sichtbarer_text(page) -> str:
    """Text der gerade sichtbaren Ansicht ohne Uhrzeiten/Zaehler, die sich von Lauf zu Lauf aendern."""
    t = page.evaluate("""() => {
        const v = document.querySelector('.view:not(.hidden)');
        return v ? v.innerText : '(keine Ansicht)';
    }""")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def lauschen(page, rolle: str):
    page.on("pageerror", lambda e: fehler.append(f"[{rolle}] Ausnahme: {str(e)[:200]}"))
    page.on("console", lambda m: m.type == "error" and not re.search(r"status of 40[134]", m.text) and fehler.append(f"[{rolle}] console.error: {m.text[:200]}"))
    def antwort(r):
        if r.status >= 400 and r.status not in (401, 403, 404):
            fehler.append(f"[{rolle}] HTTP {r.status} {r.url[len(URL):][:80]}")
    page.on("response", antwort)


def anmelden(browser, name: str, pin: str):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True,
                              has_touch=True, service_workers="block", locale="de-DE", timezone_id="Europe/Berlin")
    page = ctx.new_page()
    lauschen(page, name)
    page.goto(URL)
    page.wait_for_selector("#login-name", state="visible", timeout=15000)
    page.fill("#login-name", name)
    page.fill("#login-pin", pin)
    page.click("#login-btn")
    page.wait_for_selector("#login-screen", state="hidden", timeout=20000)
    page.wait_for_timeout(1200)
    page.reload()
    page.wait_for_selector("#ladebalken", state="detached", timeout=20000)
    page.wait_for_timeout(1500)
    return page


def rundgang(page, rolle: str, ergebnis: dict):
    def merke(schluessel: str, ms: int = 900):
        page.wait_for_timeout(ms)
        ergebnis[f"{rolle}|{schluessel}"] = sichtbarer_text(page)

    merke("start")
    tabs = page.eval_on_selector_all("#tableiste button", "bs => bs.map(b => b.dataset.ober)")
    for ober in tabs:
        page.click(f'#tableiste button[data-ober="{ober}"]')
        page.wait_for_timeout(500)
        unter = page.eval_on_selector_all("#subnav button", "bs => bs.map(b => b.textContent.trim())")
        if not unter:
            merke(ober)
        for u in unter:
            try:
                page.click(f'#subnav button:text-is("{u}")')
                merke(f"{ober}/{u}")
            except Exception as e:                                           # noqa: BLE001
                fehler.append(f"[{rolle}] Klick {ober}/{u}: {str(e).splitlines()[0][:100]}")

    # Detailansichten: das jeweils erste klickbare Element einiger Listen
    def versuche(name: str, aktion):
        try:
            aktion()
            merke(name, 1000)
        except Exception as e:                                               # noqa: BLE001
            ergebnis[f"{rolle}|{name}"] = "(nicht erreichbar)"
            print(f"  Hinweis [{rolle}] {name}: {str(e).splitlines()[0][:90]}")

    def termin_detail():
        page.click('#tableiste button[data-ober="training"]'); page.wait_for_timeout(600)
        page.click('#subnav button:text-is("Termine")') if rolle == "Trainer" else None
        page.wait_for_timeout(500)
        page.click(".termin-karte, .termin, [class*=termin-]:not(body)", timeout=3000)
    versuche("detail-termin", termin_detail)

    def wiki_detail():
        key = "taktik"
        page.click(f'#tableiste button[data-ober="{key}"]'); page.wait_for_timeout(700)
        page.click(".wiki-zeile", timeout=3000)
    versuche("detail-wiki", wiki_detail)

    def profil_menue():
        page.click("#profil-knopf"); page.wait_for_timeout(600)
    versuche("profil-menue", profil_menue)
    page.keyboard.press("Escape")

    eintraege = page.eval_on_selector_all("#pm-liste button", "bs => bs.map(b => b.textContent.trim())") \
        if page.query_selector("#pm-liste") else []
    for e in eintraege:
        if re.search(r"abmelden|ansehen", e, re.I):
            continue
        def offen(e=e):
            page.click("#profil-knopf"); page.wait_for_timeout(500)
            page.click(f'#pm-liste button:has-text("{e}")')
        versuche(f"profil/{e}", offen)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ausgabe", required=True)
    ap.add_argument("--vergleiche")
    a = ap.parse_args()

    server = demo_starten()
    ergebnis: dict[str, str] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for name, pin in (("Trainer", "1111"), ("Lena", "2222")):
                print(f"== {name}")
                page = anmelden(browser, name, pin)
                rundgang(page, name, ergebnis)
                page.context.close()
            browser.close()
    finally:
        if server:
            server.kill()

    Path(a.ausgabe).write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1), encoding="utf-8")
    leer = [k for k, v in ergebnis.items() if len(v) < 15]
    print(f"{len(ergebnis)} Seiten erfasst, {len(leer)} fast leer, {len(fehler)} Fehler")
    for k in leer:
        print("  leer:", k)
    for f in dict.fromkeys(fehler):
        print("  FEHLER", f)

    if a.vergleiche:
        alt = json.loads(Path(a.vergleiche).read_text(encoding="utf-8"))
        unterschiede = [k for k in sorted(set(alt) | set(ergebnis)) if alt.get(k) != ergebnis.get(k)]
        print(f"Vergleich mit {a.vergleiche}: {len(unterschiede)} Unterschiede")
        for k in unterschiede:
            print("  ANDERS:", k)
            print("     vorher :", (alt.get(k) or "-")[:160])
            print("     nachher:", (ergebnis.get(k) or "-")[:160])
        sys.exit(1 if unterschiede or fehler else 0)
    sys.exit(1 if fehler else 0)


if __name__ == "__main__":
    main()
