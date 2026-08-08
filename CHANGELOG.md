# Changelog — Balu's Training

Die Versionsnummer steht **im Kopf der App** (klein neben „Balu's Training") und
kommt aus `APP_VERSION` in `static/app.js`. Wer wissen will, ob ein Gerät den
aktuellen Stand hat, vergleicht die Zahl dort mit der obersten hier.

Schema: **v0.<Funktionsstand>.<Korrektur>** — neue Funktion erhöht die mittlere
Zahl, Fehlerbehebungen und Design-Feinschliff die letzte.

## Bei jeder neuen Version

1. `APP_VERSION` in `static/app.js` hochzählen.
2. Hier oben einen Abschnitt mit Datum anlegen und **schreiben, was geändert
   wurde** (in der Sprache des Teams, nicht in Commit-Sprache).
3. `CACHE` in `static/sw.js` hochzählen (`elo-vN`) — sonst bekommen die Geräte
   den neuen Stand nicht.
4. Für jede geänderte Datei das `?v=` in `static/index.html` erhöhen.
5. Mit `bash deploy.sh` deployen (testet erst, lädt nur bei grün hoch).

---

## Offen — beim nächsten Mal anschauen

**Am PC hängt sich die App auf.** Gemeldet am 2026-08-08, noch nicht
nachgestellt. Am Handy und am Tablet ist es bisher nicht aufgefallen.

Was ich zum Suchen bräuchte: **auf welchem Bildschirm** es passiert, was zuletzt
angetippt wurde, und welcher Browser. Wenn möglich einmal `F12` drücken, auf
„Console" gehen und abtippen oder abfotografieren, was dort rot steht — damit
ist es meist in Minuten gefunden.

Drei Verdächtige, die ich zuerst prüfen würde:

1. **Team-Einteilung bei vielen Ausgewählten.** „Teams generieren" probiert für
   zwei Teams *alle* Aufteilungen durch. Bei 20 Anwesenden sind das 184 000
   Kombinationen — am Handy wählt man selten so viele, am PC eher. Die Notbremse
   greift erst bei 300 000; darunter kann der Tab für einige Sekunden stehen und
   wirkt eingefroren. Verdacht Nummer eins, und leicht zu entschärfen (Grenze
   senken oder die Rechnung aus dem Hauptfenster auslagern).
2. **Das neue Querformat-Layout** greift ab 760 px Breite im Querformat — also
   an *jedem* PC-Monitor. Wenn dort etwas klemmt, sieht das nur am PC so aus.
3. **Der Service Worker mit altem Cache.** Am PC hängt oft noch eine ältere
   Fassung im Speicher. Einmal `Strg`+`Umschalt`+`R` ausprobieren: hilft das,
   war es nur der Cache und kein Fehler im Programm.

---

## v0.40.0 — 2026-08-08

**Zwei bis vier Teams — Etappe 5 von 5, der Umbau ist durch.** Erwärmungsspiele
laufen mal mit zwei, mal mit vier Teams. Die App kann das jetzt.

**Oben ein Umschalter 2 · 3 · 4.** Die Aufteilung passiert sofort: Torhüterinnen
reihum, danach die Stärksten ins jeweils kleinste und schwächste Team, zum
Schluss Feinschliff durch Tauschen. Zu wenige Spielerinnen für vier Teams? Dann
ist die Vier gesperrt. Die Teams heißen nach ihren **Leibchen** — Blau, Ocker,
Weiß, Grün.

**Antippen schiebt ins nächste Team** (bei zweien also einfach auf die andere
Seite). Bei zwei Teams zeigt die App weiterhin die Siegchance; ab drei einen
Stärkevergleich, weil eine Prozentzahl zwischen vier Teams Zahlenspielerei wäre.

**Beim Ergebnis stehen die Namen.** Je Team ein großer Knopf mit Ø-Stärke,
Anzahl und den Vornamen darunter — beim Eintippen zwischen zwei Spielen sieht
man, wen man da gerade wertet. Dazu ein Knopf für Unentschieden.

**Die ELO-Rechnung für mehrere Teams.** Jede Spielerin wird gegen **jedes andere
Team einzeln** gerechnet, der Schnitt daraus ist ihre Änderung. Gegen das
Siegerteam zählt das als Niederlage; zwei Teams, die beide verloren haben,
spielen gegeneinander unentschieden.

Der Umweg über die Paare ist wichtig: bei drei Teams gibt es einen Sieger und
zwei Verlierer. Hätte man einfach 1 und 0 vergeben, würden in Summe alle
verlieren und die Werte über die Saison langsam absacken. So bleibt die Summe
der Änderungen bei rund null. Ein Rundungsrest (Sieger +10, drei Verlierer je
−3,33 → −3) wird ebenfalls ausgeglichen, sonst wanderten pro Vier-Team-Spiel
gut drei Punkte ins System.

**Eure bisherigen Spiele ändern sich um keinen Punkt.** Bei zwei Teams ist die
neue Formel rechnerisch identisch mit der alten — nachgewiesen an 5000
Zufallsspielen (null Abweichungen) und an der echten Datenbank: die acht
gespeicherten Spiele wurden mit der neuen Rechnung nachgerechnet, alle 85
Verlaufszeilen und alle ELO-Stände kommen auf denselben Wert. Für zwei Teams
wird auch weiterhin einzeln gerundet, damit das so bleibt.

**Spiel-Detail und Korrektur** kommen jetzt mit beliebig vielen Teams klar: die
Teamblöcke und die Korrektur-Knöpfe werden aus dem gespeicherten Spiel gebaut.
Ein Drei-Team-Spiel bekommt drei Knöpfe plus Unentschieden, ein altes
Zwei-Team-Spiel wie gehabt zwei.

Technisch: `spiele` bekommt die Spalte `teams` (JSON-Liste von Listen);
`team_a`/`team_b` werden weiter gefüllt, damit alte Zeilen gültig bleiben, beim
Lesen gewinnt `teams`. Das Ergebnis ist der Buchstabe des Siegerteams (A–D) oder
`U` — für zwei Teams also unverändert A/U/B. Neu: `elo.berechne_spiel_mehrere()`,
`teams.teams_generieren_n()`, `db.spiel_eintragen_n()`, `TeamsLokal.generiereN()`
(die Aufteilung läuft weiter offline im Browser). `/api/teams` nimmt `anzahl`,
`/api/spiel` nimmt `teams`. Vier neue Team-Tests. Datenbank vorher gesichert
(`elo.db.bak-2026-08-08-…-etappe5`).

---

## v0.39.0 — 2026-08-08

**Aufstellung auf dem Spielfeld — Etappe 4 von 5.** Neuer Unterpunkt
„Aufstellung" unter Training, für Trainer **und** Spielerinnen sichtbar. Er
zeigt das Halbfeld — 6-m-Bogen, gestrichelte 9-m-Linie, 7-m-Marke — mit den
Zusagen für das nächste Training darauf.

**Zwei Ansichten, ein Feld.**

- **Training:** *alle* Zusagen stehen auf ihrer Position — alle Halblinken bei
  Halblinks. Über jeder Gruppe steht das Kürzel mit der Anzahl (`HL · 3`).
  Wahlweise als kleine Portraits oder nur als Namen (Umschalter oben).
- **Spiel:** eine Spielerin je Position plus Wechselbank. Als Trainer:
  jemanden von der Bank antippen, dann eine Position — sie tauschen. Ein Tipp
  auf eine besetzte Position setzt die Spielerin zurück auf die Bank.

Unter dem Feld steht, welche Positionen **unbesetzt** sind — die Information,
für die man sonst die Zusagen durchgeht.

**Portraits sitzen im Vereinswappen.** Die Wappenform ist ausgeschnitten und
trägt heute die Initialen; echte Fotos rutschen später in dieselbe Form, ohne
dass sich am Aussehen etwas ändert.

**Positionen im Kader pflegen.** Statt der alten Auswahl „Feld / Tor" gibt es
jetzt sieben antippbare Positionen — **mehrere gleichzeitig sind erlaubt**,
weil das in euren Daten längst so steht („Halblinks/kreis"). Wer „Tor" wählt,
wird automatisch auch für die Team-Aufteilung als Torhüterin geführt; die grobe
Feld/Tor-Angabe zieht mit, man muss sie nicht mehr getrennt pflegen.

**Die alten Angaben werden verstanden**, keine musst du neu eintippen:
„Außen" landet auf **beiden** Flügeln (die Seite steht nirgends), „Rückraum"
auf allen drei Rückraumpositionen, „Halblinks/kreis" auf beiden. Nur
„Allrounder" bleibt offen — die App zählt solche Fälle unter dem Feld auf und
verlinkt direkt in den Kader.

Drei Punkte, bei denen ich ohne deine Antwort entschieden habe — alle leicht zu
ändern:

- **Mehrfachpositionen: ja.** Deine Daten enthalten sie schon.
- **Trikotnummern: vorerst nicht.** Es gibt sie in der Datenbank nicht; die
  Portraits tragen Initialen. Sag Bescheid, wenn du die Nummern willst.
- **Die Spiel-Aufstellung liegt lokal auf dem Gerät**, nicht auf dem Server.
  Sie ist eine Tafel, kein Dokument — auf dem Trainings-Tablet bleibt sie
  stehen, auf deinem Handy ist sie leer. Soll sie geteilt werden, wird eine
  kleine Tabelle daraus.

Technisch: keine Schema-Änderung nötig — `spieler.position_angriff` ist
Freitext und nimmt die Liste mit `/` als Trenner.
`POST /api/spieler/{id}` akzeptiert das Feld jetzt, `db.spieler_aktualisieren()`
setzt `position` daraus ab. Die Teilnahmeliste liefert `position_angriff` mit,
damit die Feld-Ansicht ohne Kader-Zugriff auskommt (Spielerinnen dürfen
`/api/spieler` nicht abrufen). Datenbank vorher gesichert
(`elo.db.bak-2026-08-08-…-etappe4`).

---

## v0.38.0 — 2026-08-08

**Training aufschreiben — Etappe 3 von 5.** Der Trainingsplan besteht ab jetzt
aus **Blöcken**: Titel, Notiz und optional eine Dauer. Aus den Dauern rechnet
die App die Uhrzeiten — du planst in Minuten und siehst trotzdem, wann was
dran ist.

**Die Dauer ist absichtlich freiwillig.** Deine 17 vorhandenen Pläne stehen als
Überschriften mit Stichpunkten da, ganz ohne Minuten. Ein Block ohne Dauer
bekommt einfach keine Uhrzeit, der Rest rechnet weiter. So passt beides in
dieselbe Ansicht: der grob notierte Plan und der auf die Minute geplante.

**Der Editor:** je Block ein Minutenfeld, ein Titel und eine Notizzeile, dazu
↑ ↓ zum Verschieben und ✕ zum Löschen. Oben steht die Bilanz — wie viele
Minuten geplant sind, wann die Einheit nach diesem Plan endet, und wie viele
Blöcke noch ohne Dauer sind. Gespeichert wird **automatisch** (rund eine
Sekunde nach der letzten Eingabe); der Stand steht unter der Bilanz. Das läuft
über dieselbe Outbox wie alles andere, funktioniert also auch ohne Netz.

**Aus der Übungssammlung übernehmen.** Unter dem Editor lassen sich die Übungen
aus dem Wissens-Bereich aufklappen; ein Tipp hängt eine davon als Block an. Die
Sammlung ist damit nicht mehr nur Nachschlagewerk, sondern Baukasten.

**Alte Pläne mitnehmen.** Bei einem Training mit altem Plantext steht jetzt
„In Blöcke übernehmen": jede Überschrift wird ein Block, die Stichpunkte
darunter die Notiz, eine Minutenangabe in der Überschrift wird als Dauer
erkannt. Danach ergänzt du die Zeiten, wo du sie brauchst. Der alte Text bleibt
in der Datenbank stehen, und „Text bearbeiten" gibt es weiterhin.

**Der Coach liefert jetzt Blöcke.** Speichert man einen Coach-Plan an einem
Training, zerlegt der Server ihn direkt in Blöcke — sein Vorschlag landet also
im Editor, wo du ihn nur noch schiebst. Ein von Hand gebauter Plan wird dabei
**nicht** überschrieben. Der Coach-Prompt gibt die Phasen dafür in einer festen
Form aus (`## 1. Einstimmung (10 min)`).

**Der Plan ist Trainersache — auch in den Daten.** Bisher hätte eine
angemeldete Spielerin den Plan über die JSON-Schnittstelle abrufen können, auch
wenn die App ihn nicht anzeigt. Jetzt entfernt der Server Plan, Blöcke und
Inhalt aus der Antwort, sobald jemand ohne Trainerrolle fragt — bei
`/api/trainings/{id}` genauso wie beim nächsten Training auf dem Startbildschirm.

Technisch: neue Tabelle `training_block` (idempotent über das Schema angelegt),
`POST /api/trainings/{tid}/blocks` (ersetzt den ganzen Plan, damit ein
wiederholter Sendeversuch nichts verdoppelt) und
`POST /api/trainings/{tid}/blocks/aus-text`. `trainer.bloecke_aus_markdown()`
zerlegt beide Plansorten. `/api/trainings` liefert zusätzlich `plan_minuten`;
in der Terminliste steht das als `PLAN 85′` — nur für Trainer. Datenbank vorher
gesichert (`elo.db.bak-2026-08-08-1533-etappe3`).

---

## v0.37.0 — 2026-08-08

**Termine-Übersicht — Etappe 2 von 5.** Aus der Trainingsliste wird eine echte
Übersicht: Wer kann wann? Der Punkt ist, eine dünne Einheit zu sehen, **bevor**
man in der Halle steht.

**Jede Zeile zeigt die Zusagen.** Wochentag und Datum links, Thema und Uhrzeit
in der Mitte, rechts groß die Zahl der Zusagen. Darunter ein Balken aus Zusagen
und Absagen. Der farbige Streifen links sagt, ob die Einheit trägt: blau ab neun
Zusagen, ocker bei sechs bis acht, rot bei fünf oder weniger — dann steht statt
„Zusagen" auch „zu wenig" daneben.

**Frühwarnung oben.** Ist eine kommende Einheit unter sechs Zusagen, steht über
der Liste eine Karte: *„DO 20. Aug: nur 3 Zusagen — 9 abgesagt. Früh genug, um
zu verschieben, zusammenzulegen oder abzusagen."* Genau die Information, für die
man sonst die Liste durchzählt.

**Kommende zuerst.** Oben „Kommende Termine" aufsteigend, darunter „Vergangen"
mit den letzten acht. Vorher standen die ältesten Trainings gleichberechtigt
dazwischen.

**Antippen klappt die Namen auf** — Zugesagt, Unsicher, Abgesagt, Keine
Rückmeldung, jeweils mit Anzahl. Bei den Absagen steht der **Grund direkt
daneben**; fehlt er (Altbestand aus Anytype), steht das auch dort.

**Zu- und Absagen direkt in der Übersicht.** Spielerinnen müssen nicht mehr erst
ins Training hinein — die Antwortknöpfe stecken in der aufgeklappten Zeile. Und
statt eines leeren Textfelds gibt es beim Absagen jetzt **Vorschläge zum
Antippen** (Arbeit, Urlaub, Krank, Verletzt, Uni/Schule, Anderer Termin), eigener
Text weiterhin möglich. Ein Grund bleibt Pflicht — der Server nimmt eine Absage
ohne Grund gar nicht erst an.

**Trainer können Termine löschen.** In der aufgeklappten Zeile, zweistufig: der
erste Tipp macht den Knopf scharf („Wirklich löschen?"), der zweite löscht.
Nach vier Sekunden ohne Bestätigung wird er wieder harmlos. Ebenfalls dort:
„Öffnen & Plan" und „Erinnerung senden". Löschen braucht eine Verbindung — die
Änderung geht direkt an den Server, nicht über die Outbox.

Technisch: neuer Endpunkt `POST /api/trainings/{tid}/loeschen` (nur Trainer,
idempotent), `db.training_loeschen()` räumt Teilnahme und Übungs-Zuordnung mit
weg. `/api/trainings` liefert zusätzlich `unsicher` und `kader`, damit die Liste
auch offline vollständig rechnen kann. Der Unterpunkt heißt jetzt „Termine"
statt „Trainings". Vor dem Aufspielen wurde die Datenbank gesichert
(`elo.db.bak-2026-08-08-1521`).

---

## v0.36.0 — 2026-08-08

**Neues Aussehen — Etappe 1 von 5.** Die App trägt jetzt die Vereinsfarben.
Funktional ändert sich nichts, alle Ansichten stehen an derselben Stelle wie
vorher; es geht um Farbe, Kopfzeile, Navigation und die Zurück-Taste. Die
weiteren Etappen (Termine-Übersicht, Trainingsplan, Spielfeld-Ansicht, neuer
Live-Modus) kommen danach.

**Farben kommen aus dem Verein.** Das Wappen gibt das Blau (`#234E9E`), der
Hallenboden die zweite Ebene: Court-Blau für Team A, Torraum-Ocker für Team B.
Das alte Creme-Grün ist raus. Wichtigste Aufräumaktion dabei: **Rot bedeutet ab
jetzt ausschließlich Absage, Fehler oder Löschen** — vorher war dieselbe Farbe
auch Team B und ein negativer ELO-Wert. Ein verlorenes Trainingsspiel wird im
Spiel-Detail deshalb nicht mehr rot hinterlegt, sondern nur noch ruhig grau.

**Kopfzeile mit Wappen.** Oben stehen jetzt das Vereinswappen, die Wortmarke und
rechts die Serververbindung als lesbare Anzeige („synchron" / „sendet" /
„offline") statt des kleinen bunten Punkts, der über der Überschrift schwebte.
Der Punkt war antippbar und ist es weiterhin — das Synchronisieren erzwingt man
wie gehabt durch Antippen. Darunter läuft als wiederkehrendes Zeichen eine
gestrichelte Linie, die 9-m-Linie der Halle.

**Die Zurück-Taste funktioniert.** Das ist die wichtigste Änderung fürs
Trainings-Tablet: Bisher hat die Android-Zurück-Taste die App geschlossen. Jetzt
geht sie eine Ebene zurück — aus einem Training zurück zur Trainingsliste, aus
einer Playbook-Seite zurück zur Übersicht. Erst auf der Startseite schließt
Zurück die App, so wie man es von jeder anderen App kennt. (Aus einem Spiel-
Detail landet man dabei direkt wieder in der Rangliste, nicht auf dem Umweg über
das Spielerinnen-Profil.)

**Querformat.** Dreht man das Tablet quer, wandert die Leiste mit den fünf
Hauptpunkten von unten an die linke Kante. Quer ist Breite genug da, Höhe aber
knapp — so bleibt der Platz dem Inhalt. Hochkant bleibt alles wie gewohnt.

**Anmeldebildschirm und Ladeanzeige** tragen ebenfalls das Wappen statt des
Emoji-Platzhalters.

Technisch: Farben laufen jetzt über benannte Variablen (`--tvg`, `--court`,
`--ocker`, `--warn`), Schriftrollen ebenfalls (`--f-body`, `--f-disp`,
`--f-num`) — dort werden später eigene Schriften eingehängt, ohne den Rest der
Datei anzufassen. `deploy.sh` lädt zusätzlich `manifest.webmanifest` und
`tvg-logo.png` mit hoch.

---

## v0.35.1 — 2026-08-06

**Playbook: „Taktik generell" ist jetzt eine Gruppe wie „Allgemeine Spielzüge".**
Der lange Text mit den 6:0-Grundprinzipien steckt nicht mehr auf einer Seite,
sondern in drei eigenen Unterseiten:

- Aktives Verschieben (mit der Grafik)
- Abstimmung IR/IL und HR/HL
- Unterbrechung des Angriffsspiels

Jede beginnt mit `**Abwehr:** 6:0`, damit der Zusammenhang erhalten bleibt.
Gemacht mit `migrate_taktik.py` (einmalig, direkt auf der Server-Datenbank,
Backup vorher).

**Wiki-Ansicht am PC überarbeitet.**

- Die Seitenliste ist am großen Bildschirm wieder **einspaltig**. Vorher lief
  sie ab 600 px zweispaltig — beim Aufklappen einer Gruppe rutschte die
  Nachbarseite (z. B. „Absprache-Frauen") nach oben. Trainings-Liste, Kader und
  Rangliste bleiben zweispaltig.
- Lesebreite auf 720 px begrenzt, damit die Zeilen auf dem Monitor nicht über
  die ganze Breite zerlaufen.
- Eine Gruppe ist jetzt eine zusammenhängende Karte: Kopf und Unterseiten in
  einem Rahmen, Unterseiten mit senkrechter Führungslinie an der Einrückung.
- Dezenter Hover auf Zeilen und Gruppenkopf — nur mit echter Maus, damit am
  Trainings-Tablet kein Hover-Zustand kleben bleibt.

**Versionsschema umgestellt** von `v35` auf `v0.35.1`; ab hier wird dieser
Changelog geführt.

---

## Vor v0.35.1

Die Versionen wurden nur durchgezählt (zuletzt `v35`), ohne Changelog. Was
damals gebaut wurde, steht in `README.md` und in
`ROADMAP-offline-multiuser.md` — dort ist unter anderem der Offline-Umbau
(IndexedDB, Outbox, Service Worker) mit den zugehörigen Versionssprüngen
dokumentiert.
