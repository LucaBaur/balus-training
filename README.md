# Balu's Training

*Offline-first PWA for a handball team: attendance, training plans, video clips,
and fair team-balancing via an individual ELO rating. FastAPI + SQLite backend,
vanilla-JS service-worker frontend with an offline outbox, deployed as a systemd
user service. No external APIs.*

---

Früher `Spieler-ELO`. ELO-System für die Trainingsspiele des Frauenteams.
Jede Spielerin hat einen individuellen Spielstärke-Wert; daraus lassen sich per
Knopfdruck faire Teams zusammenstellen. Ergebnisse werden im Training am Handy
eingetippt, die ELOs werden nach Anytype zurückgeschrieben.

> Läuft komplett auf dem Homeserver — **keine LLM/API, keine laufenden Kosten.**

## Screenshots

<!-- docs/screenshot-*.png — werden nach dem lokalen Lauf mit Demo-Daten ergänzt -->

| Startseite | Faire Teams | Trainingsplan |
|---|---|---|
| ![Startseite](docs/screenshot-start.png) | ![Faire Teams](docs/screenshot-teams.png) | ![Trainingsplan](docs/screenshot-plan.png) |

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
| `portraits/`      | Original-Fotos der Spielerinnen (groß, unverändert)         |
| `static/portraits/` | Zugeschnittene Portraits für die App + `index.json`        |
| `portraits.py`    | Baut aus den Originalen die Bilder für die App              |
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
unter `http://homeserver:8200` bzw. über Tailscale von unterwegs.

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
| POST    | `/api/trainings/{tid}/teilnahme` | Eigene Zu-/Absage (Grund bei Absage Pflicht) |
| POST    | `/api/trainings/{tid}/teilnahme/{spieler_id}` | Trainer trägt für eine Spielerin ein; `status: "offen"` setzt zurück |
| POST    | `/api/trainings/{tid}/loeschen` | Termin löschen (Trainer)  |
| POST    | `/api/trainings/{tid}/blocks` | Trainingsplan als Blöcke setzen (Trainer) |
| POST    | `/api/trainings/{tid}/blocks/aus-text` | Alten Plantext in Blöcke zerlegen |
| GET     | `/api/clips`     | Szenen-Videos (Spielerin: nur eigene, Trainer: alle) |
| GET     | `/api/clips/{id}/video` | Videodatei streamen (Range-fähig, Zugriff geprüft) |
| POST    | `/api/clips`     | Clip anlegen (Trainer; multipart: `video` + `meta`-JSON) |
| POST    | `/api/clips/{id}` | Titel/Notiz/Datum bzw. `spieler_ids` ändern (Trainer) |
| POST    | `/api/clips/{id}/loeschen` | Clip + Datei löschen (Trainer) |

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

## Termine: Trainings, Testspiele, Ligaspiele

Alle Termine stehen in **einer** Tabelle (`trainings`) und unterscheiden sich
über die Spalte `art`:

| `art`       | Bedeutung | zusätzliche Felder                        |
|-------------|-----------|-------------------------------------------|
| `training`  | Normalfall (Default, auch für den Altbestand) | –                     |
| `testspiel` | Testspiel | `gegner`, `heim` (1/0), `abfahrt`          |
| `ligaspiel` | Ligaspiel | dito                                       |

`uhrzeit` ist bei Spielen der **Anwurf**, `abfahrt` die gemeinsame Abfahrt und
wird nur bei **Auswärtsspielen** gespeichert (der Server verwirft sie bei
Heimspielen). Ein Spiel ohne `gegner` wird mit 400 abgelehnt.

Warum eine gemeinsame Tabelle: Teilnahme, Erinnerungen, Termin-Detail und die
Offline-Spiegelung gelten für Spiele genauso wie für Trainings — getrennte
Tabellen hätten jede dieser Stellen verdoppelt.

**Wichtig beim Anfassen dieser Stellen:** alles, was ein Training „am Datum"
sucht (`db.training_anlegen`, `db.naechstes_training`, `trainings_termine.py`,
der Anytype-Import), filtert auf `art = 'training'`. Sonst überschreibt der
nächtliche Import ein Spiel, das am selben Tag steht. Ebenso zählt die
Trainingsquote (`db.spieler_detail`) nur `art = 'training'`.

In der App: Trainings sind weiße Karten, Testspiele ocker, Ligaspiele blau; die
nächsten drei Spiele stehen fest auf der Startseite (bei Auswärtsspielen mit
der Abfahrtszeit).

## Portraits

Die Wappen in der App (Aufstellung, Bank, Rangliste, Profil) zeigen Fotos der
Spielerinnen; wer keins hat, bekommt weiterhin die Initialen.

- **Originale** liegen in `portraits/`, ein Bild je Spielerin, beliebig groß.
- **`portraits.py`** schneidet daraus automatisch einen Kopf-Schulter-Ausschnitt
  im Wappen-Format 5:6 (460×552, JPEG) und legt ihn in `static/portraits/` ab.
  Der Zuschnitt findet die Person über den hellen Studio-Hintergrund und
  positioniert danach einen fest großen Ausschnitt — dadurch ist der Zoom über
  alle Bilder gleich.
- **Zugeordnet wird über den Namen**, nicht über die Datenbank-ID:
  `static/portraits/index.json` bildet den Namens-Slug (`Franzi O.` →
  `franzi-o`) auf die Datei ab; `app.js` bildet denselben Slug.

Neues Foto einpflegen:

```bash
# 1. Bild nach portraits/ legen (z. B. portraits/Sarah.jpg)
# 2. in portraits.py eine Zeile in ZUORDNUNG ergaenzen: "Sarah": "Sarah"
py portraits.py --pruefen     # baut die Bilder + gleicht die Namen mit dem Kader ab
bash deploy.sh                # laedt static/portraits mit hoch
```

Sitzt ein Ausschnitt daneben, hilft `FEIN` in `portraits.py`:
`"Sarah": (0.0, -0.05, 0.9)` = etwas höher und näher dran.

Die Fotos gehören **nicht** ins Repository (siehe `.gitignore`) — sie liegen
lokal und auf dem Homeserver. Der Service Worker cacht sie beim Start mit,
damit die Gesichter in der Halle auch offline da sind.

## Szenen-Videos

Einzelne Spielszenen aus einer Aufzeichnung, zugeordnet zu einzelnen
Spielerinnen. Geschnitten und beschriftet (Pfeile, Kreise, Text, Standbilder)
werden sie am PC mit dem Schwesterprojekt **`Balu-Videoschnitt`**; von dort lädt
das Werkzeug den fertigen Clip per `POST /api/clips` hoch (angemeldet als
Trainerin).

- Die MP4-Dateien liegen unter `media/clips/` — **nicht** im Repository (`.gitignore`),
  wie die Portraits. Der Ordner wird beim Start automatisch angelegt.
- Ausgeliefert wird ein Clip nur über `GET /api/clips/{id}/video` mit Rollen- und
  Zuordnungsprüfung, **nicht** über den `StaticFiles`-Mount. Range-Anfragen
  bedient Starlette selbst, damit der Player springen kann.
- Tabellen: `video_clip` (Titel, Notiz, Dateiname, Aufnahmedatum, Dauer) und
  `video_clip_spieler` (n:m — eine Szene kann mehrere Spielerinnen betreffen).
- Der Service Worker cacht Clips **nicht** (zu groß); `/api/…` ist von der
  Offline-Hülle ohnehin ausgenommen.

## Anytype-Anbindung

- `python anytype_sync.py --pruefe` — Verbindung + Eigenschaften prüfen
- `python anytype_sync.py --import` — Spielerinnen aus Anytype importieren
- `python anytype_sync.py --sync` — aktuelle ELOs nach Anytype schreiben

Config in der `.env` (siehe `.env.example`): `Api_key`, `ANYTYPE_SPACE_ID`,
`ANYTYPE_API_BASE` (Homeserver: `http://127.0.0.1:31012/v1`), `ANYTYPE_ELO_KEY`
(Default `elo`). In der App erledigen die Buttons im Tab „Kader" Import und Sync.

## Deployment (Homeserver)

Läuft auf **homeserver** unter `~/elo/` als systemd-**User**-Dienst
`elo.service` (Interpreter: `~/anytype-sync/.venv/bin/python`, Port **8200**).
Die `.env` liegt nur auf dem Server (nicht im Repo).

```bash
# Dienst steuern (auf dem Server; bei SSH ohne Login: XDG_RUNTIME_DIR setzen)
export XDG_RUNTIME_DIR=/run/user/$(id -u)
systemctl --user status|restart|stop elo.service

# Neu deployen (vom PC aus, im Ordner „Coding"):
tar czf - --exclude='__pycache__' --exclude='elo.db' --exclude='.env' \
  --exclude='media' -C . Balu-Training \
  | ssh you@homeserver "tar xzf - -C ~/elo --strip-components=1 && \
    export XDG_RUNTIME_DIR=/run/user/\$(id -u) && systemctl --user restart elo.service"
```

`bash deploy.sh` fasst nur die `static/`-Dateien an — für Änderungen an `app.py`
oder `db.py` (etwa die Szenen-Videos) den vollen `tar`-Weg oben nehmen. Der
Medienordner entsteht beim Start von selbst; falls nicht, einmalig
`mkdir -p ~/elo/media/clips` auf dem Server.

## Zugriff in der Halle (Tailscale)

Der Server ist im Heimnetz unter `http://homeserver:8200` erreichbar. Für
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
