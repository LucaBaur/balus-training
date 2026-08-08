"""Legt die Login-Benutzer an (Phase 4) und erzeugt PINs zum Verteilen.

- 1 Trainer-Konto (Standard: 'Luca').
- Je aktive Spielerin ein Konto (rolle=spieler, verknüpft mit ihrem Kader-
  Eintrag über spieler_id), Login-Name = Kader-Name.

PINs werden zufällig erzeugt (4-stellig) und NUR als Hash gespeichert; der
Klartext erscheint einmalig in dieser Ausgabe -> notieren und verteilen.

CLI:
  py benutzer_setup.py                 # fehlende Konten anlegen + PINs zeigen
  py benutzer_setup.py --trainer Luca  # Trainer-Name setzen
  py benutzer_setup.py --reset         # PINs ALLER Konten neu setzen
  py benutzer_setup.py --reset-name X  # nur X entsperren + neue PIN (bei Sperre)
  py benutzer_setup.py --db pfad.db
"""

from __future__ import annotations

import argparse
import secrets
import sys

import auth
import db


def neue_pin() -> str:
    return f"{secrets.randbelow(10000):04d}"


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trainer", default="Luca", help="Name des Trainer-Kontos")
    ap.add_argument("--reset", action="store_true",
                    help="PINs bestehender Konten neu erzeugen")
    ap.add_argument("--reset-name", help="nur diesen Namen entsperren + neue PIN")
    ap.add_argument("--db")
    args = ap.parse_args()

    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)

    # Einzelnen Benutzer entsperren + neue PIN (z. B. nach 3 Fehlversuchen).
    if args.reset_name:
        b = db.benutzer_nach_name(conn, args.reset_name)
        if not b:
            print(f"Kein Benutzer '{args.reset_name}' gefunden.")
        else:
            pin = neue_pin()
            db.benutzer_pin_setzen(conn, b["id"], auth.hash_pin(pin))
            print(f"\n{b['name']}: neue PIN = {pin}  (entsperrt)\n")
        conn.close()
        return

    # gewünschte Konten: Trainer + aktive Spielerinnen
    ziel = [{"name": args.trainer, "rolle": "trainer", "spieler_id": None}]
    for s in db.aktive_spieler(conn):
        if s["name"].strip() == args.trainer.strip():
            continue  # Namenskollision Trainer/Spielerin vermeiden
        ziel.append({"name": s["name"], "rolle": "spieler", "spieler_id": s["id"]})

    ausgabe = []   # (name, rolle, pin|"vorhanden")
    for z in ziel:
        vorhanden = db.benutzer_nach_name(conn, z["name"])
        if vorhanden and not args.reset:
            ausgabe.append((z["name"], z["rolle"], "· vorhanden ·"))
            continue
        pin = neue_pin()
        if vorhanden:
            db.benutzer_pin_setzen(conn, vorhanden["id"], auth.hash_pin(pin))
        else:
            try:
                db.benutzer_anlegen(conn, z["name"], rolle=z["rolle"],
                                    pin_hash=auth.hash_pin(pin),
                                    spieler_id=z["spieler_id"])
            except Exception as e:
                ausgabe.append((z["name"], z["rolle"], f"FEHLER: {e}"))
                continue
        ausgabe.append((z["name"], z["rolle"], pin))

    print(f"\n{'Name':22} {'Rolle':9} PIN")
    print("-" * 40)
    for name, rolle, pin in sorted(ausgabe, key=lambda x: (x[1] != "trainer", x[0])):
        print(f"{name:22} {rolle:9} {pin}")
    print("\nPINs notieren und verteilen. Erneut anzeigen geht NICHT "
          "(nur der Hash wird gespeichert) – bei Verlust: --reset.")
    conn.close()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
