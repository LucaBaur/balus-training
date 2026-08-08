# Spieler-ELO

ELO-System für die Trainingsspiele des Frauenteams (TVG). Jede Spielerin hat
einen individuellen Spielstärke-Wert; daraus lassen sich per Knopfdruck faire
Teams zusammenstellen. Ergebnisse werden im Training am Handy eingetippt, die
ELOs werden nach Anytype zurückgeschrieben.

> Läuft komplett auf dem Homeserver — **keine LLM/API, keine laufenden Kosten.**

Die aktuelle Version steht im Kopf der App und in
**[CHANGELOG.md](CHANGELOG.md)** — dort gehört zu **jeder** neuen Version ein
Eintrag, was geändert wurde (samt Checkliste für den Versions-Bump).

## Aufbau

| Datei / Ordner    | Zweck                                                       |
|-------------------|-------------------------------------------------------------|
| `elo.py`          | ELO-Berechnung (individuell gegen Gegnerteam-Schnitt)       |
| `teams.py`        | Faire Team-Aufteilung (min. ELO-Differenz, Torhüter-Pflicht)|
| `db.py`           | SQLite-Datenhaltung (Spieler, Spiele, ELO-Verlauf)          |
| `app.py`          | FastAPI-Backend (JSON-Endpunkte + liefert die PWA aus)      |
| `static/`         | PWA (index.html, app.js, style.css, manifest, sw, Icons)    |
| `make_icons.py`   | Erzeugt die PWA-Icons                                        |
| `demo.py`         | End-to-End-Test des Kerns ohne Server                       |
| *(geplant)*       | Anytype-Sync, Import der Spielerinnen, Deployment            |

## Starten (lokal zum Ausprobieren)

```bash
pip install -r requirements.txt
python make_icons.py          # einmalig, erzeugt die Icons
uvicorn app:app --host 0.0.0.0 --port 8200
```

Dann im Browser `http://localhost:8200` öffnen. Am Homeserver läuft es später
unter `http://192.168.8.125:8200` bzw. über Tailscale von unterwegs.

### Endpunkte

| Methode | Pfad             | Zweck                                    |
|---------|------------------|------------------------------------------|
| GET     | `/api/spieler`   | Aktive Spielerinnen                      |
| POST    | `/api/spieler`   | Spielerin anlegen (name, stufe, position)|
| POST    | `/api/teams`     | Faire Teams aus Anwesenheitsliste        |
| POST    | `/api/spiel`     | Ergebnis eintragen, ELO aktualisieren    |
| POST    | `/api/undo`      | Letztes Spiel rückgängig                 |
| GET     | `/api/rangliste` | Rangliste                                |
| GET     | `/api/seiten`    | Wiki-Seiten (optional `?kategorie=`)     |
| POST    | `/api/seiten`    | Seite anlegen (titel, kategorie, parent_id) |
| POST    | `/api/seiten/{id}` | Titel/Inhalt setzen                    |
| POST    | `/api/seiten/{id}/loeschen` | Seite löschen                 |
| POST    | `/api/trainings/{tid}/loeschen` | Termin löschen (Trainer)  |
| POST    | `/api/trainings/{tid}/blocks` | Trainingsplan als Blöcke setzen (Trainer) |
| POST    | `/api/trainings/{tid}/blocks/aus-text` | Alten Plantext in Blöcke zerlegen |

Die **Angriffsposition** steht als Freitext in `spieler.position_angriff`, bei
mehreren mit `/` getrennt (`Halblinks/Kreis`). Sieben Positionen: Tor,
Linksaußen, Halblinks, Mitte, Halbrechts, Rechtsaußen, Kreis. Altbestände aus
Anytype werden beim Anzeigen gedeutet — „Außen" heißt beide Flügel, „Rückraum"
alle drei Rückraumpositionen. Enthält der Wert „Tor", setzt der Server die grobe
`position` automatisch auf `Tor` (die Team-Aufteilung braucht das).

Der **Trainingsplan** liegt als `training_block` (Reihenfolge, optionale
`dauer_min`, Titel, Notiz) am Training. Er ist **Trainer-only**: `/api/trainings/{id}`
und `/api/naechstes-training` entfernen Plan, Blöcke und Inhalt aus der Antwort,
wenn die Rolle nicht `trainer` ist.

Die Schreib-Endpunkte für Seiten sind **Trainer-only**; Spielerinnen sehen
lesend ausschließlich `kategorie=playbook`.

## Playbook / Wiki

Die Seiten (`seiten`-Tabelle) bilden einen **Baum**: eine Seite mit `parent_id`
erscheint eingerückt unter ihrer Gruppe, beliebig tief (das Frontend deckelt bei
`WIKI_MAX_TIEFE`). Die Reihenfolge kommt aus `sortierung`, bei Gleichstand
alphabetisch. Eine Seite mit Unterseiten wird automatisch zur aufklappbaren
Gruppe; ob eine Gruppe zu ist, merkt sich die App in `localStorage`.

```
Taktik generell
Absprache-Frauen
Allgemeine Spielzüge
  ├ Jugo · Kreisel · Goran · Auftakt · X?
  └ Jugo-Lövgren · Iso halb · 4        (jeweils **Gegen:** 6:0)
Überzahl
Unterzahl
Offensive Abwehr                       (enthält „Gegen 5:1")
```

Die Übungs-Kategorien (2te Welle, Innenblock, Abschlussspiele, Konterspiele,
Taktikschulung) liegen unter `kategorie='uebung'`, nicht im Playbook.

Gepflegt wird alles **in der App** (Trainer: „＋ Neue Seite" in der Liste — mit
Auswahl, unter welche Seite sie soll — sowie „✏️ Bearbeiten" / „🗑 Löschen" auf
der Seite). Bearbeiten läuft über die Outbox, funktioniert also auch offline;
Anlegen und Löschen brauchen eine Verbindung, weil der Server die ID vergibt.

`import_anytype.py` überschreibt bei bestehenden Seiten die **Kategorie nicht
mehr** — die App ist die Wahrheit für die Struktur. `KATEGORIE_REGELN` greift
nur noch für neu importierte Seiten.

### Migrationsskripte (einmalig, 2026-07-23)

| Skript                  | Was es gemacht hat |
|-------------------------|--------------------|
| `migrate_playbook.py`   | Übungs-Kategorien aus dem Playbook zu den Übungen, Sammelseite „Playbook" in Allgemein/Überzahl/Unterzahl aufgeteilt, Original als `kategorie='archiv'` weggelegt |
| `migrate_spielzuege.py` | „Allgemein" → „Allgemeine Spielzüge", je Spielzug eine Unterseite, Abschnitt „Gegen 5:1" nach „Offensive Abwehr", oberste Ebene sortiert |

Beide sind idempotent, aber **`migrate_playbook.py` ist gesperrt** (verlangt
`--ich-weiss-was-ich-tue`): es stellt eine Zielstruktur her und würde Seiten
wiederherstellen, die inzwischen in der App gelöscht wurden. Strukturänderungen
gehören ab jetzt in die App, nicht in ein Skript.

## ELO-Modell

- **Individuell:** Jede Spielerin wird behandelt, als hätte sie 1-gegen-1 gegen
  den ELO-Durchschnitt des Gegnerteams gespielt.
  `E = 1 / (1 + 10^((Gegnerschnitt − ELO) / 400))`, `Δ = K · (S − E)`.
- **Zwei bis vier Teams:** bei mehr als zwei Teams wird gegen *jedes* andere
  Team einzeln gerechnet und gemittelt: `Δ = K · Σ(S_j − E_j) / (Teams − 1)`.
  Gegen den Sieger ist `S = 0`, als Sieger `S = 1`, zwischen zwei Verlierern
  `S = 0.5`. So bleibt die Summe der Änderungen bei ~0 (sonst sackten alle
  Werte ab, weil es je Spiel nur einen Sieger, aber mehrere Verlierer gibt).
  Bei zwei Teams ist das rechnerisch die Formel darüber — bestehende Spiele
  ändern sich nicht.
- **Start per Stufe (Seeding):** stark = 1150, mittel = 1000, schwach = 850 —
  damit die Teams von Beginn an fair sind.
- **K-Faktor:** 40 in den ersten 10 Spielen (schnelle Kalibrierung), danach 20.
- Der `elo_verlauf` speichert jedes Delta → Ergebnis kann rückgängig gemacht
  oder neu berechnet werden.

## Team-Aufteilung

Zwei möglichst gleich starke Teams (Größen unterscheiden sich um höchstens eine
Spielerin). Sind mindestens zwei Torhüterinnen anwesend, bekommt jedes Team eine.

## Anytype-Anbindung

- `python anytype_sync.py --pruefe` — Verbindung + Eigenschaften prüfen
- `python anytype_sync.py --import` — Spielerinnen aus Anytype importieren
- `python anytype_sync.py --sync` — aktuelle ELOs nach Anytype schreiben

Config in der `.env` (siehe `.env.example`): `Api_key`, `ANYTYPE_SPACE_ID`,
`ANYTYPE_API_BASE` (Homeserver: `http://127.0.0.1:31012/v1`), `ANYTYPE_ELO_KEY`
(Default `elo`). In der App erledigen die Buttons im Tab „Kader" Import und Sync.

## Deployment (Homeserver)

Läuft auf **192.168.8.125** unter `~/elo/` als systemd-**User**-Dienst
`elo.service` (Interpreter: `~/anytype-sync/.venv/bin/python`, Port **8200**).
Die `.env` liegt nur auf dem Server (nicht im Repo).

```bash
# Dienst steuern (auf dem Server; bei SSH ohne Login: XDG_RUNTIME_DIR setzen)
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user status|restart|stop elo.service

# Neu deployen (vom PC aus, im Ordner „Handball Frauen"):
tar czf - --exclude='__pycache__' --exclude='elo.db' --exclude='.env' -C . Spieler-ELO \
  | ssh luca@192.168.8.125 "tar xzf - -C ~/elo --strip-components=1 && \
    export XDG_RUNTIME_DIR=/run/user/\$(id -u) && systemctl --user restart elo.service"
```

## Zugriff in der Halle (Tailscale)

Der Server ist im Heimnetz unter `http://192.168.8.125:8200` erreichbar. Für
unterwegs **Tailscale** (kostenlos):

1. **Server:** `curl -fsSL https://tailscale.com/install.sh | sh` und
   `sudo tailscale up` (Auth-Link im Browser öffnen, einloggen). Tailnet-IP mit
   `tailscale ip -4` anzeigen (z. B. `100.x.y.z`).
2. **Handy:** Tailscale-App installieren, gleicher Login.
3. Im Handy-Browser `http://100.x.y.z:8200` öffnen → **Zum Startbildschirm
   hinzufügen**. Fertig — App-Icon, funktioniert auch über Mobilfunk.

## Test

```bash
python demo.py
```
