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
- [ ] Aufstellungsfeld, Ampelfarben und Diagramme separat prüfen
- [x] `theme-color` im Manifest und in `index.html` mitziehen

## 4. Spielzüge sichtbar machen

Das Playbook ist heute nur Text (Markdown). Ein Spielzug ist visuell.

- [ ] Spielfeld mit Positionen und Laufwegen in Schritten, Spielerin tippt
      „weiter“; Daten je Schritt als JSON an der Playbook-Seite
- [ ] Editor für den Trainer (Spieler ziehen, Pfeile setzen), zuerst nur
      Betrachter-Ansicht, Bearbeiten später
- [ ] Verknüpfung mit Szenen-Clips: unter dem Diagramm „So sah es im Spiel aus“
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
- [ ] `app.js` (über 5000 Zeilen) in ES-Module aufteilen (Termine, Videos,
      Playbook, Trainer), ohne sichtbare Änderung
- [ ] Nutzertest mit drei Spielerinnen: je eine Aufgabe („Sag fürs nächste Spiel
      ab“, „Finde den Spielzug Kreisel“), beobachten, wo es hakt

## 6. Sicherheit und Betrieb (Befunde vom 2026-11-03)

Eigene Liste, weil sie vor neuen Funktionen kommt. Details und Entscheidungen
stehen in der Sitzung, hier nur die Aufgaben:

- [ ] Login-Sperre zeitlich begrenzen (statt dauerhaft) und pro IP drosseln,
      damit niemand Konten gezielt aussperren kann
- [ ] Security-Header ergänzen (CSP, `X-Frame-Options`, `Referrer-Policy`)
- [ ] `.session_secret` auf Rechte 600 setzen (liegt am Server mit 644)
- [ ] Dienst nur auf `127.0.0.1` lauschen lassen, wenn Funnel davorsitzt
- [ ] Tägliches Backup der `elo.db` (`sqlite3 .backup`), mit mehreren Ständen
- [ ] Sitzungen widerrufbar machen (z. B. Zähler am Benutzer im Cookie)
