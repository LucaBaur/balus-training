# Balu's Training: nächste Schritte

Stand: 2026-11-03, nach Durchsicht von v0.64. Das ist eine Ideenliste mit
Reihenfolge, kein Versprechen. Erledigtes bitte hier abhaken und im
[CHANGELOG](CHANGELOG.md) eintragen.

Leitgedanke: Die App hat zwei Seiten. Spielerinnen sollen schnell antworten und
etwas lernen, der Trainer soll sofort sehen, was ihn braucht. Aktuell ist sie
vom Trainer her gewachsen.

## 1. Zwei Startseiten (umgesetzt in v0.65.0)

- [x] **Spielerinnen-Home:** nächstes Training mit großem Zu-/Absage-Knopf,
      nächstes Spiel mit Abfahrt, „Neu für dich“ (Clip, Feedback), Tabellenplatz.
      Navigation auf vier Punkte kürzen (Home, Termine, Videos, Playbook),
      „Ich“ und To-Dos hinter das Profil-Symbol.
- [x] **Trainer-Home als Aktionsliste:** zu wenige Zusagen, Offene erinnern,
      To-Dos mit offenem Feedback, unbeantwortete Video-Fragen, offene
      Nachbereitung. Dazu Positions-Lücken beim nächsten Termin (z. B. niemand im
      Kreis) und der Video-Fortschritt je Spielzug.

## 2. Gezielte Push-Nachrichten

Push gibt es schon (Erinnerung, Kommentare, To-Do-Feedback). Es fehlen:

- [x] Neuer Clip oder neue Analyse für dich
- [x] Abfahrtszeit am Vortag und am Spieltag
- [x] Termin abgesagt (Termin geändert fehlt: es gibt keinen Bearbeiten-Weg)
- [x] Trainer: Zusagen unter Mindestzahl, sobald sie unterschritten wird
- [x] Je Spielerin abschaltbar nach Art (Termine / Videos / To-Dos)
- [x] iPhone: Hinweis und Kurzanleitung „Zum Home-Bildschirm hinzufügen“, sonst
      kommt dort kein Push an

## 3. Dark Mode

- [x] Farben in CSS-Variablen bündeln (`:root`), dann `prefers-color-scheme: dark`
      ergänzen, optional Umschalter im Profil
- [x] Aufstellungsfeld, Ampelfarben und Diagramme separat prüfen — v0.77.2,
      Kontrasttest `tests/kontrast.test.mjs`; Wappen-Rand im Dunkelmodus und
      Siegchance-Balken (Court/Ocker) bewusst offen gelassen
- [x] `theme-color` im Manifest und in `index.html` mitziehen

## 4. Spielzüge sichtbar machen

Das Playbook ist heute nur Text (Markdown). Ein Spielzug ist visuell.

- [x] Spielfeld mit Positionen und Laufwegen in Schritten, Spielerin tippt
      „weiter“; Daten je Schritt als JSON an der Playbook-Seite — v0.76.0,
      als Baum mit Abwehr-Reaktionen (`spielzug_schritt`)
- [x] Editor für den Trainer (Spieler ziehen, Pfeile setzen), zuerst nur
      Betrachter-Ansicht, Bearbeiten später — v0.77.0 (Pfeile fehlen noch,
      Undo und Schritt duplizieren auch)
- [x] Verknüpfung mit Szenen-Clips: unter dem Diagramm „So sah es im Spiel aus“
      — v0.76.0, ein Clip je Lösung
- [ ] Editor-Feinschliff: Undo, Schritt duplizieren, Ansicht für Spielerinnen
      offline vorab laden
- [ ] Abwehrformationen 5:1 und 3:2:1 (bisher nur 6:0)
- [ ] „Verstanden“-Haken oder Kurzquiz je Spielzug, Trainer sieht, wer ihn kann
- [ ] Mögliche Quelle der Laufwege: Projekt Handball-Vision

## 5. Weitere Ideen

- [ ] Saisonübersicht je Spielerin für den Trainer (Beteiligung, Statistik,
      To-Do-Fortschritt, gesehene Videos an einem Ort)
- [ ] Fahrgemeinschaften für Auswärtsspiele (wer fährt, freie Plätze)
- [ ] Kalender-Abo (iCal) für Termine
- [ ] SpielerPlus ablösen: Einladungen für Neue, Weg für Spielerinnen ohne Push
- [ ] Barrierefreiheit: Beschriftungen für Bedienelemente, Kontraste prüfen,
      Fokus per Tastatur
- [x] `app.js` (über 5000 Zeilen) in ES-Module aufteilen (Termine, Videos,
      Playbook, Trainer), ohne sichtbare Änderung — v0.70.3, `static/main.js` + `core/` + `features/`
- [ ] Nutzertest mit drei Spielerinnen: je eine Aufgabe („Sag fürs nächste Spiel
      ab“, „Finde den Spielzug Kreisel“), beobachten, wo es hakt

## 6. Sicherheit und Betrieb (Befunde vom 2026-11-03)

Eigene Liste, weil sie vor neuen Funktionen kommt. Details und Entscheidungen
stehen in der Sitzung, hier nur die Aufgaben:

- [x] Login-Sperre zeitlich begrenzen (statt dauerhaft) und pro IP drosseln,
      damit niemand Konten gezielt aussperren kann — v0.77.3 (`daten/login.py`),
      deployt am 2026-11-18. Der Funnel setzt `X-Forwarded-For` (geprüft: die echte
      Adresse landet in `login_versuche.ip`).
      Offen dazu: Zeitunterschied „Name unbekannt“ (schnell) gegen „PIN falsch“
      (PBKDF2) verrät noch, ob es den Namen gibt
- [ ] Security-Header ergänzen (CSP, `X-Frame-Options`, `Referrer-Policy`)
- [ ] `.session_secret` auf Rechte 600 setzen (liegt am Server mit 644)
- [ ] Dienst nur auf `127.0.0.1` lauschen lassen, wenn Funnel davorsitzt
- [x] Tägliches Backup der `elo.db` (`sqlite3 .backup`), mit mehreren Ständen —
      v0.77.3 (`backup.py`), Cron 03:10 Berlin seit 2026-11-18, Ablage `~/backups/elo`,
      Status im HA-Dashboard „Scripte“ (`balu_backup`). Offen: Kopie auf den PC (der Server bleibt sonst die
      einzige Stelle), `media/` (3,9 GB Videos) und Portrait-Uploads sind nicht dabei
- [x] Sitzungen widerrufbar machen (z. B. Zähler am Benutzer im Cookie) — v0.78.0,
      deployt am 2026-11-18 (`benutzer.sitzung_version`, Knopf „Auf allen Geräten
      abmelden“, neue PIN beendet alte Sitzungen)
