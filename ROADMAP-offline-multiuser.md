# Balu's Training — Ausbau: Offline · Server-Wahrheit · Spieler-App

Dieser Ausbau ist **Teil der bestehenden App** — lokaler Ordner
**`Balu's Trainings App`** (früher `Spieler-ELO`), deployt nach `~/elo` am
Server. **Kein** neues Projekt, kein Parallelordner, kein zweiter Deploy-Weg.
Der Server-Pfad bleibt `~/elo` (nur der lokale Ordner wurde umbenannt).

Bezug (Memory): `spieler-elo-projekt`, `trainings-bot-projekt`,
`idee3-uebungssammlung`.

## Ziel (vom User priorisiert)

1. **Offline am Handy** — mit keiner/schlechter Verbindung normal weiterarbeiten.
2. **Daten liegen am Server** (SQLite = Wahrheit), Handy hält einen **Spiegel**.
3. **Anytype ablösen** — Trainings, Teilnahme (Zu-/Absagen) und Trainingspläne
   wandern in die App (SQLite). Ziel des Users: **bald nur noch die App**
   (Server + Handy), Anytype wird nicht mehr gebraucht — höchstens als
   optionaler Export/Archiv daneben, nicht mehr als Datenquelle.
4. **App für Spielerinnen** mit eingeschränktem Zugriff (Zu-/Absagen).
   - Zu-/Absagen macht **vorerst weiter SpielerPlus**, später die App.
   - → Phase 4 ist die letzte, sicherheitskritische Stufe, erst nach 1–3.

## Architektur-Leitbild

```
        Server (Homeserver ~/elo)                 Handy / PC (PWA)
   ┌───────────────────────────────┐        ┌────────────────────────────┐
   │ FastAPI (app.py)              │  HTTPS │ Service Worker (App-Hülle)  │
   │ SQLite elo.db  = WAHRHEIT     │◄──────►│ IndexedDB      = SPIEGEL    │
   │ Anytype-Sync (nachts)         │ Tailsc.│ Outbox (offene Schreibvorg.)│
   └───────────────────────────────┘        └────────────────────────────┘
      Anytype: bis Phase 3 Datenquelle,        Lesen: immer aus IndexedDB
      danach abgelöst (nur noch opt. Export)
                                                Schreiben: lokal + Outbox → Sync
```

- **Server bleibt die Wahrheit.** Das Handy erfindet keine Daten, es spiegelt.
- **Lesen** kommt immer sofort aus IndexedDB (funktioniert im Funkloch).
- **Schreiben** wird lokal angewendet **und** in eine Outbox gelegt; sobald
  Netz da ist, wird die Outbox an den Server geschickt (Idempotenz-Token, schon
  vorhanden für Spiele → keine Doppel-Einträge).
- Einhängepunkt im Frontend: die **eine** `api()`-Funktion in `app.js` (Z. 23).

## Nicht offline möglich (ehrlich)

- **Coach-Chat / Sprach-Transkription** (Groq) und **SpielerPlus-Zusagen**
  brauchen Internet. Bereits erzeugte Pläne sind offline lesbar; neue erzeugen
  nur online.

---

## Phase 1 — Offline-Fundament  (Priorität 1+2)

Neue Frontend-Module (Gerüst liegt bereits):
- `static/local-db.js` — IndexedDB-Spiegel (Stores: spieler, spiele, rangliste,
  trainings, meta, **outbox**). Get/Put/GetAll-Helfer.
- `static/sync.js` — `apiOffline()` als Ersatz-Wrapper um `api()`:
  GET → Netz, sonst Spiegel; Mutation → lokal + Outbox, dann flushen.
  `flushOutbox()`, online/offline-Listener.

Aufgaben:
- [x] `sw.js`: `local-db.js`/`sync.js` in `HUELLE` aufnehmen, `CACHE` hochzählen
      (elo-v14, Assets v=13).
- [x] `index.html`: beide Skripte **vor** `app.js` laden.
- [x] **Rangliste offline** (erster Endpunkt): `ladeRangliste()` nutzt
      `Sync.apiOffline("/api/rangliste")`, `GET_SPIEGEL` gefüllt → Antwort wird
      gespiegelt, offline aus IndexedDB gelesen.
- [ ] Weitere GET-Aufrufe umstellen (Kader `/api/spieler`, Trainings, Spieler-
      Detail `/api/spieler/{id}/spiele`).
- [ ] Mutationen (Spiel eintragen/korrigieren) über Outbox + optimistische
      lokale Anwendung.
- [ ] „X offene Änderungen"-Anzeige in der UI (Event `outbox:aenderung`).
- [ ] Test: Flugmodus → Rangliste lesen; dann weitere Endpunkte; wieder online →
      Outbox synchronisiert, keine Duplikate.

Stand 2026-07-16: Offline-Kern steht (deployt, v17). Rangliste, Kader,
Spieler-Detail offline lesbar.

**Architektur-Entscheidungen aus dem Debugging:**
- Service Worker ist **cache-first** (nicht mehr network-first) → App startet
  offline/bei schlechtem Netz sofort, kein Splash-Hang durch Fetch-Timeout.
  Versionen kommen über CACHE-Bump + controllerchange-Reload trotzdem an.
- Datenschicht: **generischer GET-Cache pro Pfad** (IndexedDB-Store `responses`,
  DB_VERSION 2) statt typisierter Stores → JEDER einmal online geladene GET ist
  offline verfügbar (auch `/api/spieler/{id}/spiele`).
- UI lädt **stale-while-revalidate**: `Sync.spiegelRoh(pfad)` sofort anzeigen,
  dann `Sync.frischHolen(pfad)` (online, 4 s Timeout) nachziehen.
- Sichtbarer Ladebalken (`#ladebalken`) + Versionsnummer (`#version`) im Kopf.
- Detail offline nur, wenn die Spielerin einmal online geöffnet wurde.
- **`apiOffline` ist cache-first** (v18): liegt der Pfad im Cache, sofort liefern,
  ohne auf `navigator.onLine` zu vertrauen (das lügt im Flugmodus = true) →
  kein 4-s-Timeout mehr beim Detail-Klick.
- **Tests vor Deploy:** `tests/offline.test.mjs` + `tests/teams.test.mjs` +
  `deploy.sh` (Syntax + Tests + scp). Immer `bash deploy.sh` statt direktem scp.

Stand 2026-07-16 (v19): Phase 1 Lesen+Schreiben offline komplett.
- **Serverstatus-Punkt** rechts oben (`#server-punkt`): rot=offline,
  gelb=synchronisiert gerade, grün=synchron. Echter Ping auf **`/api/ping`**
  (neuer Backend-Endpunkt), alle 15 s + bei Netzwechsel; navigator.onLine wird
  bewusst NICHT vertraut.
- **Vollständiges Vorab-Laden** (`Sync.prefetchAlles`): sobald Server erreichbar,
  werden Rangliste, Kader, Trainings UND alle Spieler-Details geladen → nichts
  mehr manuell anklicken vor dem Offline-Gehen.
- **Team-Einteilung offline**: `teams.py` nach `static/teams-local.js` portiert
  (gleiche Regel, Brute-Force bis ~300k Kombis, sonst gierig). `/api/teams`
  (Server) wird von der App nicht mehr genutzt.
- **Ergebnis-Eintrag offline** via Outbox (`Sync.senden`): geht immer erst in die
  Outbox, wird gesendet sobald Server da; Token = Idempotenz. Flushes sind
  **serialisiert** (Promise-Kette), nicht per Guard — sonst verschluckt ein
  laufender Flush einen frischen Eintrag (Test deckte das auf).
- Noch server-online: Coach, Anytype-Sync, Spiel korrigieren/löschen, Undo,
  Spielerin anlegen/ändern.

Stand v20: Status wird jetzt **dynamisch** aktualisiert (ohne Neuladen).
- Ping auch bei `visibilitychange`/`focus` (Rückkehr zur App nach Flugmodus) +
  Intervall auf 10 s; `online`-Event allein war unzuverlässig.
- **Status-Punkt ist antippbar** → `Sync.jetztSynchronisieren()` (prüfen + Outbox
  senden) für manuelle Kontrolle am Handy.
- **Badge** (`#sync-badge`) neben dem Punkt zeigt die Zahl offener Änderungen.
- Test 7 in offline.test.mjs deckt den Ablauf offline→online→gesendet ab.

**Wichtige Lektion (v14):** Der Start-Tab „Training" hatte `zeigeView()` HINTER
einem `await api("/api/spieler")` → offline schlug der Aufruf fehl, die Ansicht
wurde nie gezeigt → **App hing beim Start weiß**. Fix: Ansicht sofort zeigen,
Laden im Hintergrund (`.catch`), und `/api/spieler` über `apiOffline` spiegeln.
Merke: **Boot-Pfad darf nie auf einem ungespiegelten Netzaufruf blockieren.**
Sichtbare Versionsnummer im Kopf (`#version`, aktuell v14) zum Prüfen am Gerät.

## Phase 2 — Server als saubere Wahrheit + PC-Nutzung

- [x] Konfliktregel dokumentiert (siehe „Konfliktregel" unten): Server gewinnt
      bei GET; Schreiben läuft über die Outbox mit Idempotenz-Token, wird erst
      nach erfolgreichem Push entfernt.
- [x] PC: nichts Neues nötig — `https://homeserver.tailnet.ts.net` bzw.
      `http://homeserver:8200` im Browser „installieren".
- [x] **Responsive Breitbild (v22):** additive Media Queries in `style.css`
      (ab 760px 2-spaltig, ab 1100px 3-spaltig) für aufgeklappten Z Fold + PC;
      Handy-Layout unberührt. `style.css` jetzt auch in `deploy.sh`.

### Konfliktregel (Server = Wahrheit)

Grundsatz: **Der Server (SQLite `elo.db`) ist die einzige Wahrheit, das Handy
hält nur einen Spiegel.** Es gibt bewusst keine bidirektionale Merge-Logik im
Frontend — das wäre für ein 1-Admin-Setup Overengineering. Stattdessen zwei
klare Richtungen:

**Lesen (GET) — Server überschreibt den Spiegel.**
- Angezeigt wird immer zuerst der lokale Spiegel (`Sync.apiOffline`, cache-first
  aus IndexedDB-Store `responses`) → sofort sichtbar, auch im Funkloch.
- Ist der Server erreichbar, holt `frischHolen()` im Hintergrund den frischen
  Stand und **ersetzt den Cache bedingungslos** (`LocalDB.put("responses", …)`,
  `sync.js:82`). Ein veralteter lokaler GET verliert also immer gegen den Server.
- Folge: Was ein anderes Gerät / der nächtliche Anytype-Sync am Server ändert,
  gewinnt beim nächsten Prefetch/Refresh. Das Handy „erfindet" keine Lesedaten.

**Schreiben (Mutation) — Outbox + Idempotenz-Token, kein Silent-Drop.**
- Jede Mutation geht **zuerst** persistent in die Outbox (`senden()`,
  `sync.js:137`) mit einem einmaligen `token`. Erst nach erfolgreichem
  Server-POST wird der Eintrag entfernt (`_flushEinmal()`, `sync.js:161`) —
  nie vorher, also **kein Verlust bei Verbindungsabbruch**.
- Doppelte Zustellung (wackeliges Netz, paralleler Flush) ist unschädlich: der
  Server erkennt den Token und trägt **nicht doppelt** ein. Abgesichert durch
  einen partiellen Unique-Index `ux_spiele_token` + Doppel-Check und
  `IntegrityError`-Fallback in `db.spiel_eintragen()` (`db.py:79`, `db.py:221`).
- Flushes sind **serialisiert** (Promise-Kette `_flushKette`), nicht per Guard —
  sonst verschluckt ein laufender Flush einen frisch eingereihten Eintrag.
- Bei einer **Server-Fehlerantwort** (HTTP-Status gesetzt, `err.http`) bleibt der
  Eintrag in der Outbox und blockiert die Reihenfolge (`break`), statt still
  verworfen zu werden → sichtbar über Badge + `sync:fehler`-Event.

**Was hier bewusst NICHT gelöst ist:** Zwei Geräte, die *dieselbe* Ressource
gleichzeitig ändern (echter Schreib-Schreib-Konflikt). Für Spiele ist das
unkritisch — jeder Eintrag ist ein eigener, additiver Datensatz (neues Spiel +
ELO-Delta), kein Überschreiben. Erst wenn Phase 4 (mehrere Schreiber, Spieler-
App) kommt, braucht es ggf. eine feinere Regel (z. B. server-seitiges „letzter gewinnt" pro
Feld oder Versionsnummern). Bis dahin gilt: **additiv schreiben, Server
serialisiert, Token dedupliziert.**

## Phase 3 — Anytype ablösen (App wird alleinige Wahrheit)

**Ziel:** Alles, wofür heute noch Anytype gebraucht wird, in die App holen —
danach läuft der Trainingsbetrieb komplett auf Server-SQLite + Handy-Spiegel,
ohne offene Desktop-App und ohne Bot-Konto.

### Was heute im Anytype-Space „Frauen TVG" liegt (Ist-Aufnahme 2026-07-17)

Space live inspiziert (17 Typen; die 12 leeren Anytype-Systemtypen wie Audio/
Bookmark/Note/Task ignoriert). Inhaltstragend:

| Anytype-Typ    | Objekte | Inhalt                                                    | Ziel-Tabelle |
|----------------|---------|-----------------------------------------------------------|--------------|
| **Spieler**    | 20      | Pos. Angriff **+ Abwehr**, Trainingsbeteiligung, Absprache, Urlaub, Stärken, Schwächen, SpielerPlus-ID | `spieler` (erweitert) |
| **Training**   | 14      | Datum, Inhalt, Anwesend, Abgesagt, SpielerPlus-Event-ID   | `trainings` + `training_teilnahme` |
| **Besprechung**| 2       | Meeting-Notizen                                           | `seiten` (kategorie=besprechung) |
| **Page**       | 36      | Wiki: Playbook, Gegnercheck, Taktik, Saison-Vorbereitung/-Orga, Trainingslager, Übungs-Kategorien (Aufwärmspiele, Wurf, Kraft, Konter, Abschluss, Technik, Taktik, Ausdauer…), Statistik, To-Dos, Ideen | `seiten` (+ `uebungen`, wo es echte Übungen sind) |
| **Collection** | 1       | „Spielerinnen"-Sammlung                                    | (entfällt / `seiten`) |

Rein gespiegelt, kein Datenverlust bei Abschaltung:

| Funktion              | Heute            | Status für Ablösung              |
|-----------------------|------------------|----------------------------------|
| Spielerinnen (Wahrheit)| SQLite          | ✅ nativ (`POST /api/spieler`)    |
| ELO-Rückschrieb `elo` | → Anytype        | ✅ nur Spiegel → **entfällt**     |
| ELO-Verlauf-Graph     | → Anytype (PNG)  | ⚠️ in App zeigen statt einbetten |
| Trainingsplan (Coach) | Anytype-Body     | → `trainings.plan_markdown`      |

Betroffene App-Endpunkte, die auf `anytype_sync` zeigen und ersetzt/entfernt
werden: `/api/anytype/trainings`, `/api/anytype/sync`, `/api/anytype/import`,
`/api/trainer/anytype`.

### Cross-Projekt: woher kommt die Teilnahme ohne Anytype?

Heute liest **SpielerPlus-Anytype-Sync** (separates Projekt) die Zu-/Absagen aus
SpielerPlus und schreibt sie in Anytype-Trainings. Fällt Anytype weg, muss diese
Kette in die App zeigen. **Offene Grundsatzentscheidung (mit User klären):**
- **(A)** SpielerPlus-Auslesen (`spielerplus.py`) in die App/den Server ziehen →
  ein Cron am Server schreibt Teilnahme direkt in die neue SQLite-Tabelle.
  *Sauberste Endstufe, ein System weniger.*
- **(B)** Der bestehende Sync-Job schreibt statt nach Anytype an einen neuen
  App-Endpunkt (`POST /api/trainings/teilnahme`). *Kleinerer erster Schritt,
  zwei Projekte bleiben.*
→ Empfehlung: mittelfristig **(A)**, als ersten Schritt evtl. **(B)**.

### Schritte

- [x] **Schema (2026-07-17):** in `db.py` angelegt + idempotente Migration,
      getestet (frische DB + Migrationspfad, FK-Cascade, Dedupe-Indexe):
      - `spieler` erweitert um position_abwehr, staerken, schwaechen, absprache,
        urlaub, trainingsbeteiligung, notizen.
      - `trainings` (datum, titel, uhrzeit, ort, inhalt, plan_markdown,
        spielerplus_event_id, anytype_id) — unique auf event_id & anytype_id.
      - `training_teilnahme` (training_id, spieler_id, status, quelle), CASCADE.
      - `uebungen` (name, kategorie, phase, beschreibung, markdown,
        zuletzt_gemacht, anytype_id) — für Idee 3.
      - `training_uebung` (Join, reihenfolge) — Statistik + „lang nicht gemacht".
      - `seiten` (titel, kategorie, parent_id-Hierarchie, markdown, tags,
        anytype_id, anytype_typ) — Wiki für Playbook/Gegner/Saison/Statistik/
        Besprechung.
      Noch NICHT deployt (reines Backend-Schema, kommt mit Import+Endpunkten).
- [x] **Import (2026-07-17):** `import_anytype.py` spiegelt Spieler (20),
      Trainings + Teilnahme (14 / 205 Einträge) und Wiki-Seiten (39) nach SQLite.
      Idempotent über `anytype_id` (2. Lauf = nur „aktualisiert", keine Dubletten),
      volle Bodies via `get_object`, `--dry-run`. Getestet in Temp-DB. Anytype
      bleibt unangetastet = Fallback. Läuft noch NICHT gegen Produktion (~/elo).
      ⚠️ **Bild-Caveat:** 6 Seiten enthalten Anytype-interne Bild-URLs
      (`127.0.0.1:47800/image/…`) — die brechen bei Abschaltung. Bilder vor dem
      Aus herunterladen/umziehen (eigener Schritt vor „Anytype-Abschaltung").
      ⚠️ Übungen liegen als Freitext in Seiten (kategorie=uebung); strukturierte
      `uebungen`-Extraktion (Idee 3, LLM) ist ein späterer Schritt.
- [x] **Native Lese-Endpunkte (2026-07-17):** `GET /api/trainings`,
      `/api/trainings/{id}` (Detail m. Teilnahme+Plan), `/api/naechstes-training`
      (Home), `/api/seiten?kategorie=`, `/api/seiten/{id}` in app.py +
      db-Funktionen (`trainings_liste`, `training_detail`, `naechstes_training`,
      `seiten_liste`, `seite_detail`, `training_plan_setzen`). db-Layer lokal
      getestet; HTTP-Verifikation erst am Server (FastAPI lokal nicht
      installiert). Alte `/api/anytype/*` bleiben als Fallback.
- [x] **Schreib-Endpunkt Plan (2026-07-17, app v26):** `POST /api/trainings/
      {id}/plan` → `trainings.plan_markdown`. Frontend: Plan-Editor im
      Training-Detail (Trainer-only, Markdown-Textarea), Speichern über
      `Sync.senden` (Outbox, offline-fähig), GET-Cache optimistisch gepatcht
      (Detail + `hat_plan`). Round-Trip am Server verifiziert. Teilnahme-
      Bearbeitung bleibt Phase 4 (Zu-/Absage durch Spielerinnen).
- [x] **Deployt (2026-07-17):** elo.db gesichert → Backend (app.py/db.py/
      import_anytype.py) nach ~/elo → Import gegen Produktion (idempotent) →
      `systemctl --user restart elo.service` → `deploy.sh` (Frontend). HTTP-Check
      am Server grün. Service-Python = `~/anytype-sync/.venv/bin/python`.
      Merke: `deploy.sh` deployt NUR static/ — Backend immer separat scp+restart.
- [ ] **Teilnahme-Quelle** gemäß Entscheidung A/B verdrahten (SpielerPlus →
      SQLite). Bestehende `SP_*`-Credentials/Logik wiederverwenden.
- [x] **Coach-Plan nativ (2026-07-17):** Coach hängt Pläne über
      `/api/trainings/{id}/plan` bzw. neuen `POST /api/trainings` (Anlegen/
      Wiederverwenden am Datum) an — nicht mehr in den Anytype-Body. Kaderzahl/
      Torhüter kommen aus `db.kader_info` (SQLite-Teilnahme, kein Anytype).
      Frontend-Coach nutzt `/api/trainings` statt `/api/anytype/trainings`;
      `/api/trainer/anytype` wird vom Frontend nicht mehr aufgerufen.
      Verifiziert (kader_info, Anlegen/Dedupe, Rolle 403). Noch offen für die
      finale Anytype-Abschaltung: `/api/anytype/*` ganz entfernen, Team-
      Einteilungs-Dropdown auf native Trainings, ELO-Rückschrieb + Cronjobs aus.
- [ ] **ELO-Verlauf** in der App anzeigen (Graph-PNG oder Inline-Chart je
      Spielerin) statt Einbettung in Anytype; `embed_graphs`/`schreibe_elos`
      und die Anytype-Cronjobs am Server außer Betrieb nehmen.
- [x] **Frontend-Shell (2026-07-17):** Home + zweistufige Navigation
      (Überpunkte Home/Training/Team/Taktik/Saison unten, Unterpunkte in
      `#subnav`), NAV-Config treibt beides. Rollen-Umschalter (Trainer/Spieler,
      kosmetisch — KEINE Sicherheitsgrenze bis Phase 4); Spieler sieht nur Home,
      Trainings, Playbook. Neue Views: Home-Dashboard (nächstes Training +
      Schnellzugriff), Trainings-Liste + -Detail (Teilnahme-Chips, Plan),
      generisches Wiki (Playbook/Gegner/Übungen/Statistik/Saison/Notizen) mit
      Leichtgewicht-Markdown-Renderer (`mdLite`, Anytype-Bild-URLs entfernt).
      Alle über `Sync.apiOffline`; Prefetch um Trainings + Seiten(-Details)
      erweitert. Version-Bump: app v23, style v15, sync v9, Cache elo-v24.
      Verifiziert: node --check, Offline-Tests 8/8, Team-Tests 5/5, ID-Abgleich.
      Bestehende Views (Anwesenheit/Teams/Rangliste/Kader/Coach/Spieler-Detail)
      unverändert eingehängt. NOCH NICHT deployt/visuell geprüft.
- [ ] **Anytype-Abschaltung:** `/api/anytype/*` entfernen oder hinter optionalem
      Export verstecken; Bot-Konto/`anytype.service` am Server stoppen, sobald
      alles nativ läuft. HA-Sensoren der abgeschalteten Jobs aufräumen
      (`ha_dashboard.py`).
- [ ] **Tests:** Offline-Lesen Trainings, Teilnahme-Schreiben via Outbox,
      Migrations-Skript (Anytype → SQLite, keine Duplikate). Deploy via
      `deploy.sh`, Version/Cache hochzählen.

### User-Feedback Runde 1 (2026-07-17)

Erledigt + deployt (app v24 / style v16 / Cache elo-v25):
- [x] **Positions-Tabelle im Training** wurde nicht angezeigt → `mdLite` kann jetzt
      GFM-Tabellen (+ `<br>`-Strip). Der Trainings-Body „Zusagen nach Position"
      rendert als echte Tabelle.
- [x] **Spieler-Profil unter Kader:** Kader-Kopf ist klickbar → Detailansicht
      zeigt jetzt zusätzlich Position (Angriff/Abwehr), Trainings-Anwesenheit
      (da X/Y, Quote %) und ELO-Verlauf als Inline-SVG-Sparkline. `spieler_detail`
      um Positionsfelder + `training`-Block erweitert. Zurück-Ziel je Herkunft
      (Rangliste vs. Kader).

Noch offen aus dem Feedback:
- [→ Phase 4] **Absagen mit Begründung.** Entscheidung User (2026-07-17):
      NICHT über SpielerPlus (das soll langfristig ganz wegfallen). Der Grund
      entsteht künftig in der App, wenn die Spielerinnen selbst zu-/absagen →
      komplett auf **Phase 4** verschoben (dann Spalte `training_teilnahme.grund`
      + Eingabe in der Spieler-App, Anzeige für Trainer + Spieler).
- [x] **Laufchallenge im Spieler-Profil (2026-07-17, deployt app v25).**
      `import_laufchallenge.py` liest `data.json` (→ Server als
      `~/elo/laufchallenge_data.json`), aggregiert km/Läufe pro Spielerin wie im
      Original (nur Lauf-Aktivitäten, Radfahren etc. separat), Rang nach km.
      Namens-Mapping automatisch (exakt/Vorname/Initial) — **18/18 zugeordnet,
      keine Unklarheiten** (Kader nutzt teils Kurznamen); manuelle Korrektur via
      `MANUELL`-Dict im Skript. Neue Tabelle `laufchallenge`, `spieler_detail`
      um `laufchallenge`-Block erweitert, im Profil angezeigt (km/Läufe/Platz).

**Beziehung zu [[idee3-uebungssammlung]]:** Die geplante Übungssammlung sollte
gleich **nativ in SQLite** entstehen (nicht mehr in Anytype) — passt in dieses
Datenmodell (Trainings → Übungen). Beim Bau von Phase 3 mitdenken.

**Wichtig:** Erst Schema + Import + native Lese-Endpunkte (nichts kaputt machen,
Anytype bleibt Fallback), dann Schreiben umstellen, **zuletzt** Anytype
abschalten. Nie Anytype abschalten, bevor die Daten nachweislich in SQLite sind.

---

## Phase 4 — Spieler-App (Zu-/Absagen)  — SICHERHEITSKRITISCH

Voraussetzung: Phase 1–3 stehen. Erst wenn SpielerPlus abgelöst werden soll.

Bausteine:
- [x] **Öffentlich erreichbar (2026-07-17): Tailscale Funnel AN.**
      `https://homeserver.tailnet.ts.net/` → App (nur diese eine, Rest privat).
      Über die öffentliche URL verifiziert: Shell 200, ohne Login 401, Login 200.
      Abschalten: `tailscale funnel --https=443 off`.
- [x] **Login (2026-07-17): Name+PIN.** `auth.py` (PIN als pbkdf2-Hash,
      signiertes HMAC-Session-Cookie, HttpOnly/SameSite=Lax), `benutzer`-Tabelle,
      `/api/login /logout /me`. `benutzer_setup.py` legt Trainer + je Spielerin
      ein Konto an (PIN 4-stellig, Trainer verteilt).
- [x] **Rollen server-seitig erzwungen (2026-07-17):** Dependencies
      `require_user`/`require_trainer` an ALLEN Endpunkten. Getestet: ohne Login
      401, Spielerin 403 auf rangliste/kader/gegner/coach, Trainer alles. Coach
      (Groq) ist Trainer-only (User-Wunsch). UI-Rollen-Filter ist nur Kosmetik.
- [x] **Login-Sperre (2026-07-17):** 3 Fehlversuche je Name → PIN wird GESPERRT
      (pin_hash=NULL, Spalte `benutzer.fehlversuche`). Danach kein Login bis der
      Trainer neu setzt: `benutzer_setup.py --reset-name <Name>` (neue PIN).
      Macht Raten sinnlos. Getestet inkl. Entsperrung.
- [x] **Zu-/Absage in der App (2026-07-17, app v32):** Spielerin setzt eigenen
      Status (Zusagen/Unsicher/Absagen) je Training; **Grund PFLICHT bei Absage**
      (`training_teilnahme.grund`, für Trainer + Spielerinnen sichtbar).
      `POST /api/trainings/{id}/teilnahme` (spieler_id aus Session, nie Body).
      import_anytype überschreibt app-Antworten nicht mehr (INSERT OR IGNORE).
- [x] **Web-Push (2026-07-17):** VAPID-Keys (`~/elo/.vapid_*`), `pywebpush` im
      venv, `push_abo`-Tabelle, `push.py`, `/api/push/vapid|subscribe|unsubscribe|
      test`, Service-Worker push/notificationclick, Frontend-Opt-in (Home).
      Trainer: `POST /api/trainings/{id}/erinnern` → Push an alle, die noch nicht
      in der App geantwortet haben. Plumbing verifiziert; echte Zustellung testet
      der User am Handy (Home → „Benachrichtigungen aktivieren" → „Test").
- [ ] DSGVO: nur nötige Daten, löschbar, HTTPS (Funnel-Zertifikat).

Siehe Abschnitt „Sicherheitsrisiken" unten — Phase 4 öffnet den Server ins
Internet und ist der gefährlichste Schritt.

---

## Sicherheitsrisiken Phase 4 (Server öffentlich machen)

Heute ist die App **tailnet-only** = praktisch unsichtbar. Öffentlich zu gehen
verändert das Risiko grundlegend:

1. **Angriffsfläche 0 → Internet.** Jeder Endpunkt muss feindliche Eingaben
   annehmen. → Nur **eine** App via Funnel exponieren, Rest privat lassen.
2. **Auth ist der Knackpunkt.** Ohne echte Anmeldung kann jeder lesen/schreiben.
3. **Rollen server-seitig.** Spielerin darf keine Admin-Endpunkte erreichen
   (Team-Gen, fremde Daten, Anytype-Sync). Prüfung im Backend, nicht im UI.
4. **Mehrmandant-Server.** Auf der Kiste laufen HA, Portainer, Anytype-Headless,
   Sync-Jobs. Ein Loch in der App wäre ein Sprungbrett dorthin → App als
   **unprivilegierter** systemd-User-Dienst (ist schon so), kein sudo, sonst
   nichts nach außen.
5. **Secrets in `.env`** (Groq/HA/Anytype/SpielerPlus). Nie in Antworten
   ausgeben; `chmod 600` (ist so). SSRF/Code-Exec-Lücken vermeiden.
6. **Missbrauch/Kosten.** Öffentlicher Coach-Endpunkt → jemand feuert auf deinen
   Groq-Key. → Auth + Rate-Limit auf teuren Endpunkten.
7. **DSGVO.** Namen + Anwesenheit sind personenbezogen; öffentlich = du bist
   verantwortlich. Datensparsam, löschbar, verschlüsselt (HTTPS).
