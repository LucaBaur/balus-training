"""Nutzungsdaten, Geraete, Fehlerberichte und die Spielzug-Uebersicht."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from .kommentare import _kommentar_zahlen
from .zeit import _berlin, _utc_z


# ---------------------------------------------------------------- Nutzung ----
#  Siehe Tabelle 'nutzung'. Gespeichert wird fuer jedes Konto; ausgewertet
#  werden nur die Spielerinnen-Konten (Trainer testen die App staendig selbst).

NUTZUNG_TYPEN = ("besuch", "bereich", "video", "gespielt", "verweil")   # gespielt = Video zu >= 60 % angesehen
NUTZUNG_MAX_DAUER_S = 30 * 60      # laenger am Stueck ist ein vergessener Tab, keine Nutzung
NUTZUNG_BESUCH_PAUSE_MIN = 30      # mehrere Besuche innerhalb dieser Zeit zaehlen einmal
NUTZUNG_MAX_PRO_ANFRAGE = 50


def nutzung_speichern(conn: sqlite3.Connection, benutzer_id: int,
                      ereignisse: list[dict]) -> int:
    """Speichert Ereignisse ({typ, ziel, info}); Unbekanntes wird verworfen.
    Ein 'besuch' innerhalb der Pause nach dem letzten Besuch zaehlt nicht
    (die App meldet beim Zurueckkehren oft kurz hintereinander). Gibt die
    Anzahl gespeicherter Ereignisse zurueck."""
    gespeichert = 0
    besuch_schon_da = bool(conn.execute(
        "SELECT 1 FROM nutzung WHERE benutzer_id = ? AND typ = 'besuch' "
        "AND zeit > datetime('now', ?)",
        (benutzer_id, f"-{NUTZUNG_BESUCH_PAUSE_MIN} minutes")).fetchone())
    for e in ereignisse[:NUTZUNG_MAX_PRO_ANFRAGE]:
        typ = e.get("typ")
        if typ not in NUTZUNG_TYPEN:
            continue
        if typ == "besuch":
            if besuch_schon_da:
                continue
            besuch_schon_da = True
        ziel = (str(e["ziel"])[:60] if e.get("ziel") else None)
        info = (str(e["info"])[:120] if e.get("info") else None)
        dauer = None
        if typ == "verweil":                  # ohne Ziel oder mit unplausibler Dauer wertlos
            dauer = e.get("dauer_s")
            dauer = int(round(dauer)) if isinstance(dauer, (int, float)) else None
            if not ziel or dauer is None or not 1 <= dauer <= NUTZUNG_MAX_DAUER_S:
                continue
        conn.execute("INSERT INTO nutzung (benutzer_id, typ, ziel, info, dauer_s) VALUES (?, ?, ?, ?, ?)",
                     (benutzer_id, typ, ziel, info, dauer))
        gespeichert += 1
    conn.commit()
    return gespeichert


def geraet_speichern(conn: sqlite3.Connection, benutzer_id: int, g: dict) -> None:
    """Merkt sich ein Geraet des Kontos (oder frischt 'zuletzt'/App-Version auf)."""
    def t(k: str, n: int) -> str:
        return str(g.get(k) or "").strip()[:n]
    conn.execute(
        "INSERT INTO geraet (benutzer_id, os, browser, modus, bildschirm, modell, app_version, sw) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(benutzer_id, os, browser, modus, bildschirm, modell) "
        "DO UPDATE SET zuletzt = datetime('now'), app_version = excluded.app_version, "
        "              sw = excluded.sw",
        (benutzer_id, t("os", 30), t("browser", 30), t("modus", 20), t("bildschirm", 20),
         t("modell", 40), t("app_version", 20), 1 if g.get("sw") else 0))
    conn.commit()


FEHLER_MAX_PRO_STUNDE = 20     # Schutz davor, dass eine Fehlerschleife die DB flutet


def fehler_speichern(conn: sqlite3.Connection, benutzer_id: int, f: dict) -> bool:
    """Speichert einen Fehlerbericht; False, wenn leer oder das Stundenlimit erreicht ist."""
    meldung = str(f.get("meldung") or "").strip()[:300]
    if not meldung:
        return False
    n = conn.execute("SELECT COUNT(*) FROM fehler WHERE benutzer_id = ? "
                     "AND zeit > datetime('now', '-1 hour')", (benutzer_id,)).fetchone()[0]
    if n >= FEHLER_MAX_PRO_STUNDE:
        return False

    def t(k: str, n: int) -> str | None:
        return (str(f[k]).strip()[:n] or None) if f.get(k) else None
    conn.execute(
        "INSERT INTO fehler (benutzer_id, quelle, meldung, ort, app_version, geraet) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (benutzer_id, t("quelle", 20), meldung, t("ort", 60), t("app_version", 20),
         t("geraet", 120)))
    conn.commit()
    return True


def nutzung_auswertung(conn: sqlite3.Connection, tage: int = 30) -> dict:
    """Je Spielerinnen-Konto: zuletzt aktiv, Besuche/aktive Tage/Videos der
    letzten `tage` Tage, haeufigste Bereiche und angesehene Videos."""
    jetzt = datetime.now(timezone.utc)
    grenze = jetzt - timedelta(days=tage)
    tz = _berlin()

    def lies(z: str) -> datetime:
        return datetime.strptime(z, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

    konten = conn.execute(
        "SELECT id, name, spieler_id FROM benutzer WHERE rolle = 'spieler' AND aktiv = 1 "
        "AND (spieler_id IS NULL OR spieler_id IN (SELECT id FROM spieler WHERE aktiv = 1)) ORDER BY name"   # ohne Helferinnen
    ).fetchall()
    rows: dict[int, list] = {k["id"]: [] for k in konten}
    for r in conn.execute("SELECT benutzer_id, zeit, typ, ziel, info, dauer_s FROM nutzung ORDER BY zeit"):
        if r["benutzer_id"] in rows:
            rows[r["benutzer_id"]].append(r)
    erste = conn.execute("SELECT MIN(zeit) AS z FROM nutzung").fetchone()["z"]
    geraete: dict[int, list] = {k["id"]: [] for k in konten}
    for g in conn.execute("SELECT * FROM geraet ORDER BY zuletzt DESC"):
        if g["benutzer_id"] in geraete:
            geraete[g["benutzer_id"]].append({
                "os": g["os"], "browser": g["browser"], "modus": g["modus"],
                "bildschirm": g["bildschirm"], "modell": g["modell"],
                "app_version": g["app_version"], "sw": bool(g["sw"]),
                "zuletzt": _utc_z(g["zuletzt"])})

    # Szenen und wer sie komplett gesehen hat - fuer IMMER, nicht nur im 30-Tage-Fenster:
    # ein vor 40 Tagen angeschauter Spielzug darf nicht als "nicht gesehen" erscheinen.
    katalog = _szenen_katalog(conn)
    gesehen = _szenen_gesehen((b, r["zeit"], r["typ"], r["ziel"]) for b, zeilen in rows.items() for r in zeilen)

    ausgabe = []
    for k in konten:
        ev = rows[k["id"]]
        neu = [r for r in ev if lies(r["zeit"]) >= grenze]
        bereiche: dict[str, int] = {}
        sekunden: dict[str, int] = {}       # ziel -> Summe der 'verweil'-Ereignisse
        for r in neu:
            if r["typ"] == "verweil" and r["ziel"] and r["dauer_s"]:
                sekunden[r["ziel"]] = sekunden.get(r["ziel"], 0) + r["dauer_s"]
            elif r["typ"] == "bereich" and r["ziel"]:
                bereiche[r["ziel"]] = bereiche.get(r["ziel"], 0) + 1
        nicht_gesehen = []
        for s in katalog:                    # nur Spielzuege mit Clip, an denen sie beteiligt ist
            if s["art"] != "zug" or s["clip_id"] is None or k["spieler_id"] not in s["spieler_ids"]:
                continue
            g = gesehen.get(s["clip_id"], {}).get(k["id"])
            if g and g["gespielt"]:
                continue
            nicht_gesehen.append({"id": s["id"], "analyse_id": s["analyse_id"], "spiel": s["spiel"],
                                  "label": s["label"], "name": s["name"], "ampel": s["ampel"],
                                  "zeit": s["zeit"], "t": s["t"], "geoeffnet": bool(g)})
        ausgabe.append({
            "benutzer_id": k["id"], "name": k["name"],
            "zuletzt": (ev[-1]["zeit"].replace(" ", "T") + "Z") if ev else None,
            "besuche": sum(1 for r in neu if r["typ"] == "besuch"),
            "tage": len({lies(r["zeit"]).astimezone(tz).date() for r in neu}),
            "videos_gesehen": sum(1 for r in neu if r["typ"] == "video"),
            "sekunden_gesamt": sum(sekunden.values()),
            "bereiche": [{"ziel": z, "anzahl": n, "sekunden": sekunden.get(z, 0)} for z, n in
                         sorted(bereiche.items(), key=lambda x: -x[1])[:6]],
            "nicht_gesehen": sorted(nicht_gesehen, key=lambda n: (-n["analyse_id"], n["t"] or 0)),
            "offen": len(nicht_gesehen),
            "geraete": geraete[k["id"]],
        })
    return {"tage": tage, "seit": (erste.replace(" ", "T") + "Z") if erste else None,
            "konten": ausgabe, "fehler": _fehler_gruppiert(conn, grenze)}


NUTZUNG_EREIGNIS_NAMEN = {"tor": "Tor", "fehlwurf": "Fehlwurf", "ballverlust": "Ballverlust",
                          "strafe": "Zeitstrafe", "siebenmeter": "7-Meter", "parade": "Parade"}


def _spielzeit(t: float) -> str:
    """Sekunden im Video als m:ss bzw. h:mm:ss (wie analyseZeit in app.js)."""
    t = max(0, int(t))
    h, m, s = t // 3600, t % 3600 // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _spiel_name(gegner: str, datum: str | None) -> str:
    """'TVG – Gegner · 14.09.' - das Datum trennt zwei Spiele gegen denselben Gegner."""
    tag = f" · {datum[8:10]}.{datum[5:7]}." if datum and len(datum) >= 10 else ""
    return f"TVG – {gegner}{tag}"


def _szenen_katalog(conn: sqlite3.Connection) -> list[dict]:
    """Alle Szenen aller Spiele (Spielzuege UND Ereignisse), je Kennung (szene_key) EINE.

    ID = "S<Spiel>-<Kennung>" (z. B. "S1-z3"). Die Kennung vergibt die Desktop-App und bleibt
    bei einem erneuten Daten-Upload erhalten - anders als spiel_zug.id, die dabei neu vergeben
    wird. Ohne Kennung gilt als Ersatz die Startsekunde ("S1-t723"). Teilen sich ein Spielzug
    und ein Ereignis eine Kennung, hat der Spielzug beim Namen Vorrang (wie beim Clip); die
    Beteiligten beider werden zusammengefasst, genau wie in szene_clip_darf.
    'clip_id' ist None, wenn es (noch) keinen Videoausschnitt gibt - dann laesst sich nicht
    messen, wer ihn gesehen hat."""
    spiele = {r["id"]: (_spiel_name(r["gegner"], r["datum"]), r["datum"])
              for r in conn.execute("SELECT id, gegner, datum FROM spiel_analyse")}
    clips = {(r["analyse_id"], r["szene_key"]): r["id"]
             for r in conn.execute("SELECT id, analyse_id, szene_key FROM spiel_szene_clip")}
    mitspieler: dict[int, set[int]] = {}
    for r in conn.execute("SELECT zug_id, spieler_id FROM spiel_zug_spieler"):
        mitspieler.setdefault(r["zug_id"], set()).add(r["spieler_id"])
    szenen: dict[tuple[int, str], dict] = {}

    def eintrag(aid: int, key: str | None, start: float, **felder) -> dict:
        ident = key or f"t{int(start)}"                  # ohne Kennung: Startsekunde als Ersatz
        s = szenen.get((aid, ident))
        if s is None:                                    # der zuerst angelegte Eintrag behaelt seine Felder
            name_spiel, datum = spiele.get(aid, (None, None))
            s = szenen[(aid, ident)] = {
                "id": f"S{aid}-{ident}", "analyse_id": aid, "key": key or None,
                "clip_id": clips.get((aid, key)) if key else None,
                "spiel": name_spiel, "datum": datum, "spieler_ids": set(), **felder}
        return s

    for z in conn.execute("SELECT id, analyse_id, name, ampel, t_start, t_ende, szene_key, kommentar "
                          "FROM spiel_zug ORDER BY analyse_id, t_start"):
        s = eintrag(z["analyse_id"], z["szene_key"], z["t_start"], art="zug", name=z["name"],
                    label="Spielzug " + z["name"], ampel=z["ampel"], t=z["t_start"],
                    kommentar=z["kommentar"] or "",
                    zeit=f"{_spielzeit(z['t_start'])}–{_spielzeit(z['t_ende'])}")
        s["spieler_ids"] |= mitspieler.get(z["id"], set())
    for e in conn.execute("SELECT analyse_id, typ, t, detail, spieler_id, assist_id, szene_key "
                          "FROM spiel_event ORDER BY analyse_id, t"):
        name = NUTZUNG_EREIGNIS_NAMEN.get(e["typ"], e["typ"])
        s = eintrag(e["analyse_id"], e["szene_key"], e["t"], art="ereignis", name=name,
                    label=name + (" · " + e["detail"] if e["detail"] else ""), ampel=None,
                    t=e["t"], zeit=_spielzeit(e["t"]))
        s["spieler_ids"] |= {x for x in (e["spieler_id"], e["assist_id"]) if x}
    return sorted(szenen.values(), key=lambda s: (-s["analyse_id"], s["t"]))


def _szenen_gesehen(zeilen) -> dict[int, dict[int, dict]]:
    """clip_id -> benutzer_id -> {anzahl (geoeffnet), gespielt (komplett angeschaut), zuletzt}.
    `zeilen`: (benutzer_id, zeit, typ, ziel) aus 'nutzung'. Bewusst OHNE Zeitfenster."""
    aus: dict[int, dict[int, dict]] = {}
    for benutzer_id, zeit, typ, ziel in zeilen:
        if typ not in ("video", "gespielt") or not ziel or not ziel.startswith("szene:"):
            continue
        if not ziel[6:].isdigit():
            continue
        g = aus.setdefault(int(ziel[6:]), {}).setdefault(
            benutzer_id, {"anzahl": 0, "gespielt": 0, "zuletzt": zeit})
        g["anzahl" if typ == "video" else "gespielt"] += 1
        g["zuletzt"] = max(g["zuletzt"], zeit)
    return aus


def szenen_uebersicht(conn: sqlite3.Connection) -> dict:
    """Trainer-Sicht (Team -> Videos): je Spiel alle Szenen mit ID, wer sie komplett gesehen
    hat ('gesehen': alle, die sie geoeffnet haben, mit 'gespielt' > 0 = komplett) und wer sie
    sehen soll, aber noch nicht komplett gesehen hat ('fehlt'; None = kein Video, nicht messbar).
    Sehen sollen nur die Beteiligten - eine Spielerin bekommt ohnehin nur ihre eigenen Szenen."""
    konten = conn.execute(
        "SELECT id, name, spieler_id FROM benutzer WHERE rolle = 'spieler' AND aktiv = 1").fetchall()
    namen = {k["id"]: k["name"] for k in konten}
    konto_von_spieler = {k["spieler_id"]: k["id"] for k in konten if k["spieler_id"]}
    gesehen = _szenen_gesehen(
        (r["benutzer_id"], r["zeit"], r["typ"], r["ziel"]) for r in conn.execute(
            "SELECT benutzer_id, zeit, typ, ziel FROM nutzung "
            "WHERE typ IN ('video', 'gespielt') AND ziel LIKE 'szene:%' ORDER BY zeit")
        if r["benutzer_id"] in namen)
    kommentare = _kommentar_zahlen(conn)
    gruppen: dict[int, dict] = {}
    for s in _szenen_katalog(conn):
        beteiligt = sorted((konto_von_spieler[sp] for sp in s["spieler_ids"] if sp in konto_von_spieler),
                           key=lambda b: namen[b])
        g = gesehen.get(s["clip_id"], {}) if s["clip_id"] is not None else {}
        gruppe = gruppen.setdefault(s["analyse_id"], {
            "analyse_id": s["analyse_id"], "spiel": s["spiel"], "datum": s["datum"], "szenen": []})
        gruppe["szenen"].append({
            "id": s["id"], "key": s["key"], "analyse_id": s["analyse_id"], "clip_id": s["clip_id"],
            "spiel": s["spiel"], "art": s["art"], "name": s["name"], "label": s["label"], "ampel": s["ampel"],
            "zeit": s["zeit"], "t": s["t"], "kein_video": s["clip_id"] is None,
            "kommentar": s.get("kommentar") or "",       # Erst-Kommentar des Trainers aus der Spielanalyse
            "kommentare": kommentare.get(f"szene:{s['clip_id']}", 0) if s["clip_id"] is not None else 0,
            "beteiligt": [namen[b] for b in beteiligt],
            "gesehen": sorted(({"name": namen[b], "anzahl": v["anzahl"], "gespielt": v["gespielt"],
                                "zuletzt": _utc_z(v["zuletzt"])} for b, v in g.items() if b in namen),
                              key=lambda v: v["zuletzt"], reverse=True),
            "fehlt": None if s["clip_id"] is None else
                     [namen[b] for b in beteiligt if not g.get(b, {}).get("gespielt")],
        })
    return {"spiele": sorted(gruppen.values(), key=lambda x: (x["datum"] or "", x["analyse_id"]),
                             reverse=True)}


def _fehler_gruppiert(conn: sqlite3.Connection, grenze: datetime) -> list[dict]:
    """Gleiche Fehlermeldungen zusammengefasst: Anzahl, wer, welche Geraete,
    welche App-Versionen - die neuesten zuerst."""
    rows = conn.execute(
        "SELECT f.zeit, f.quelle, f.meldung, f.ort, f.app_version, f.geraet, b.name "
        "FROM fehler f JOIN benutzer b ON b.id = f.benutzer_id "
        "WHERE f.zeit >= ? ORDER BY f.zeit",
        (grenze.strftime("%Y-%m-%d %H:%M:%S"),)).fetchall()
    gruppen: dict[str, dict] = {}
    for r in rows:
        g = gruppen.setdefault(r["meldung"], {
            "meldung": r["meldung"], "quelle": r["quelle"], "anzahl": 0, "zuletzt": None,
            "namen": [], "geraete": [], "versionen": [], "orte": []})
        g["anzahl"] += 1
        g["zuletzt"] = r["zeit"]
        for feld, wert in (("namen", r["name"]), ("geraete", r["geraet"]),
                           ("versionen", r["app_version"]), ("orte", r["ort"])):
            if wert and wert not in g[feld]:
                g[feld].append(wert)
    aus = sorted(gruppen.values(), key=lambda g: g["zuletzt"], reverse=True)[:30]
    for g in aus:
        g["zuletzt"] = _utc_z(g["zuletzt"])
        g["geraete"] = g["geraete"][:4]
    return aus
