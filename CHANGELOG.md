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

## v0.46.0 — 2026-09-03

**„Ansicht als" für das Trainerteam.** Auf der Startseite gibt es neben dem
Namen eine Auswahl „Ansehen als: <Spielerin>". Damit siehst du die App genau so,
wie diese Spielerin sie sieht – ihre Termine, ihr Playbook, ihre Videos, ihre
Startseite. Oben läuft ein Streifen mit „zurück zu <dein Name>".

Der Modus ist **nur zum Anschauen**: solange du als jemand anderes unterwegs
bist, sind alle Eingaben gesperrt (Zu-/Absagen, Playbook bearbeiten usw.). Zum
Eintragen erst über den Streifen oder die Auswahl zurück auf dein Trainerkonto.

Umschalten braucht eine Verbindung; die Rolle wird bei jedem Aufruf serverseitig
geprüft, ein „als"-Zugriff lässt sich nicht selbst basteln.

---

## v0.45.0 — 2026-09-03

**Neuer Bereich „Videos" unter „Ich".** Jede Spielerin sieht dort die Szenen aus
Spielaufzeichnungen, die ihr zugeordnet wurden, und kann sie im Player ansehen
(vor- und zurückspulen inklusive). Eine Spielerin sieht nur ihre eigenen Clips.

Für das Trainerteam gibt es den Bereich zusätzlich unter „Team". Dort sind alle
Clips sichtbar; pro Clip lässt sich einstellen, **welche Spielerinnen ihn sehen**,
und ein Clip lässt sich löschen.

Geschnitten und beschriftet (Pfeile, Kreise, Text, Standbilder) werden die Szenen
am PC mit dem eigenen Werkzeug **Balu-Videoschnitt**; von dort wird der fertige
Clip hochgeladen. Die App speichert und zeigt nur das fertige Video – der
Homeserver rechnet nichts.

---

## v0.44.0 — 2026-08-10

**Test- und Ligaspiele sind jetzt eigene Termine.** Unter „Termine" legt das
Trainerteam über **„+ Neuer Termin“** wahlweise ein Training, ein Testspiel oder
ein Ligaspiel an. Bei einem Spiel kommen dazu:

- **Gegner** (Pflicht — ohne Gegner nimmt der Server das Spiel nicht an)
- **Heimspiel oder auswärts**
- **Abfahrtszeit**, die nur bei Auswärtsspielen abgefragt wird
- **Anwurf** (das Uhrzeit-Feld) und Ort

Der Titel schreibt sich selbst: „Ligaspiel bei TSV Blaustein“ bzw. „Testspiel
gegen SG Ulm“.

**Die nächsten drei Spiele stehen auf der Startseite**, gleich unter dem
nächsten Training. Bei einem Auswärtsspiel steht rechts groß die **Abfahrt**,
daheim der Anwurf — die Uhrzeit, nach der man sich richten muss, ohne
Nachschlagen. Ein Tipp auf die Karte führt direkt in den Termin.

**In der Terminliste sind die Arten an der Farbe zu unterscheiden:** Trainings
bleiben die weiße Karte, **Testspiele sind ockerfarben**, **Ligaspiele blau**,
dazu jeweils ein Kennzeichen „TESTSPIEL · DAHEIM“ bzw. „LIGASPIEL · AUSWÄRTS“.
Der farbige Balken links bedeutet weiterhin die Zusagenlage (knapp/kritisch).

Zu- und Absagen laufen bei Spielen genau wie beim Training — dieselbe Liste,
dieselben Erinnerungen.

**Zwei Dinge, die im Hintergrund sauber bleiben:**

- Ein Spiel und ein Training können am **selben Tag** stehen. Der
  SpielerPlus-/Anytype-Import und der Wochenplan fassen nur noch Trainings an,
  ein Spiel wird nie überschrieben.
- Die **Trainingsbeteiligung** im „Ich“-Reiter zählt weiterhin nur Trainings.
  Spiele verwässern die Quote nicht.

Bestehende Termine sind unverändert Trainings — an der Datenbank musste dazu
nichts von Hand geändert werden.

---

## v0.43.0 — 2026-08-10

**Neuer Reiter „Ich“ — die eigene Seite.** Jede Spielerin hat jetzt unten in der
Leiste einen eigenen Punkt (zwischen Home und Training). Dort steht auf einen
Blick, was sie selbst betrifft:

- das **Portrait** im Wappen, groß, mit dem Namen daneben
- **Angriffs- und Abwehrposition** (und „Torhüterin“, wo hinterlegt)
- die **Trainingsbeteiligung**: Quote groß, dazu ein Balken und die Zahlen —
  wie viele Trainings zugesagt, abgesagt, unsicher
- die **Laufchallenge**: gelaufene Kilometer, Anzahl der Läufe und der Platz

Ist noch nichts hinterlegt — keine Position, keine Trainings erfasst, kein
Laufchallenge-Ergebnis — steht das auch so da, statt dass die Karte fehlt.

Den Reiter sieht, wer eine eigene Spielerin im Kader hat. Trainerinnen, die
selbst mitspielen, bekommen ihn also auch; ein reiner Trainer-Zugang ohne
Spielerprofil nicht.

Die Seite lädt aus demselben Endpunkt wie das Spielerprofil, das der Trainer
sieht — der Server gibt einer Spielerin dort **nur ihr eigenes** Profil heraus.
Einmal mit Netz geöffnet, steht die Seite danach auch offline.

---

## v0.42.1 — 2026-08-10

**Pim ist aus der Datenbank raus.** Mit ihr entfernt wurden ihr Zugang zur App,
ihr Eintrag in der Laufchallenge und vier Trainings-Rückmeldungen. Spiele oder
ELO-Verlauf hatte sie keine, an der Rangliste ändert sich also nichts. Der Kader
umfasst jetzt 19 Spielerinnen. Eine Sicherung der Datenbank von vorher liegt am
Server (`elo.db.bak-20260810-1613-vor-pim`).

**Ein Portrait war falsch zugeordnet:** das Foto gehört zu **Annika Lutz**, nicht
zu Anni Dussler. Es sitzt jetzt bei Annika; Anni hat vorerst wieder ihre
Initialen. Wer die App offen hat, bekommt das mit dem nächsten Start.

---

## v0.42.0 — 2026-08-10

**Echte Portraits statt Initialen.** Die Wappen zeigen jetzt die Fotos vom
Mannschaftsshooting — auf dem Feld in der Aufstellung, auf der Bank, in der
Rangliste und oben im Spielerprofil. Die Form bleibt dieselbe wie vorher, es
sitzt nur ein Gesicht darin statt zweier Buchstaben.

Fotos gibt es aktuell für elf Spielerinnen: Anne, Anni, Franzi O., Franzi P.,
Hanna, Helen, Lilly, Linda, Maike, Rebecca und Svenja. Wer noch keins hat,
bekommt weiterhin die Initialen — es fehlt also nirgends etwas.

**Neu in der Rangliste:** vor jedem Namen steht ein kleines Portrait, dadurch
findet man eine Spielerin schneller als über die Namensspalte allein.

**Im Profil** sitzt das Portrait oben links neben den Positions-Angaben.

Die Bilder gehören zur Offline-Hülle: beim ersten Start legt die App alle
Portraits mit in den Speicher, in der Halle sind die Gesichter also auch ohne
Netz da.

**Für neue Fotos:** Bild nach `portraits/` legen, in `portraits.py` eine Zeile
in `ZUORDNUNG` ergänzen (Dateiname → Name der Spielerin), dann
`py portraits.py --pruefen` laufen lassen — das schneidet automatisch auf Kopf
und Schultern zu und meldet, ob der Name zu einer Spielerin passt. Danach normal
`bash deploy.sh`.

---

## v0.41.1 — 2026-08-09

**Die Aufstellung stand seitenverkehrt.** Halblinks saß auf der linken
Bildschirmhälfte, Linksaußen ebenso — und das ist falsch herum.

Auf dem Feld steht das **Tor unten**, angegriffen wird nach unten. Die
Positionsnamen kommen aber aus Sicht der **Angreiferin**, die zum Tor schaut:
ihre linke Seite liegt auf dem Bildschirm rechts. Halblinks gehört also nach
rechts, Halbrechts nach links — und bei den Außen genauso.

Getauscht sind jetzt **HL ↔ HR** und **LA ↔ RA**. Das gilt für beide Ansichten
gleichzeitig, die Trainingsaufstellung und die Spielaufstellung, weil sich beide
dieselbe Positionstabelle teilen. An den Spielerinnen und ihren hinterlegten
Positionen ändert sich nichts — nur der Platz auf dem Feld stimmt jetzt.

Über der Tabelle im Code steht eine Warnung, damit die Werte niemand später
„geradezieht" und die Aufstellung damit wieder verdreht.

---

## v0.41.0 — 2026-08-09

**Man sieht jetzt, auf wen man noch wartet — und der Trainer kann für andere
eintragen.** Drei Dinge, die zusammengehören.

**1. „Noch keine Rückmeldung" steht bei jedem Termin.** Bisher zeigte ein Termin
nur die, die schon geantwortet hatten. Wer gar nichts angeklickt hatte, tauchte
nirgends auf — man sah „4 Zusagen" und wusste nicht, ob die anderen abgesagt
haben oder einfach noch nicht geschaut haben. Jetzt geht die Liste vom **ganzen
Kader** aus: unter den Zusagen, Unsicheren und Absagen steht die Gruppe „Noch
keine Rückmeldung" mit allen fehlenden Namen. Das gilt in der aufgeklappten
Zeile in der Übersicht genauso wie in der Termin-Ansicht.

**2. Der Trainer trägt für Spielerinnen ein.** Absagen kommen selten in der App
an — sie kommen per WhatsApp, am Telefon oder am Hallenrand. Als Trainer steht
deshalb jetzt hinter **jedem** Namen ein kleines Knopftrio:

> **✓** zusagen · **?** unsicher · **✗** absagen

Der eingefärbte Knopf zeigt den aktuellen Stand. Nochmal auf den aktiven Knopf
tippen setzt die Antwort wieder auf „noch offen" — für den Fall, dass man sich
vertippt. Ein **✎** hinter dem Namen bedeutet „vom Trainer eingetragen, nicht
von ihr selbst".

Ein Grund ist beim Eintragen für andere **nicht** Pflicht (anders als bei der
eigenen Absage). Man kennt ihn oft nicht genau, und eine Pflichteingabe würde
nur erfundene Gründe erzeugen.

Die Push-Erinnerung „bitte zu-/absagen" wurde mit angepasst: sie geht nur noch
an die, für die **gar keine** Antwort vorliegt. Wer schon eingetragen wurde,
wird nicht mehr genervt.

**3. Auf der Startseite steht, was von dir noch fehlt.** Spielerinnen sehen dort
jetzt einen Block **„Deine Antwort fehlt noch"** mit allen kommenden Terminen
ohne eigene Rückmeldung — jeder direkt an Ort und Stelle beantwortbar, ohne
vorher in die Terminliste zu wechseln. Ist alles beantwortet, steht dort ein
kurzes „Für alle kommenden Termine hast du geantwortet." Den alten Hinweissatz
„Zu- und Absagen machst du unter Termine" braucht es damit nicht mehr.

*Hinweis: Dieses Update ändert auch `app.py` und `db.py` am Server.*

---

## v0.40.1 — 2026-08-09

**Der Fehler, der die App am PC lahmgelegt und Zu-/Absagen verschluckt hat, ist
gefunden und behoben.** Er saß nicht im Layout und nicht in der Bedienung,
sondern im Server.

**Was los war.** Der Server holt sich für jede Anfrage eine eigene Verbindung
zur Datenbank. Das Web-Gerüst darunter verteilt eine einzelne Anfrage aber auf
mehrere Arbeits-Threads: die Verbindung wird in einem aufgemacht, in einem
zweiten benutzt und in einem dritten geschlossen. SQLite verbietet das
standardmäßig und bricht dann mit einem Fehler ab — die Anfrage endet mit
„500 Internal Server Error". In den letzten zwei Wochen ist das **196 Mal**
passiert.

Ob es einen trifft, ist reiner Zufall und hängt davon ab, wie viele Anfragen
gleichzeitig unterwegs sind. Deshalb war es **am PC am schlimmsten**: der
Browser dort holt viel mehr parallel, das Handy im Mobilnetz eher nacheinander.
Und deshalb wirkte es so willkürlich:

- **Zu-/Absagen ging nicht.** Beim Tippen auf „Zusagen" oder „Absagen" kam
  statt der Bestätigung eine Fehlermeldung — nicht immer, aber oft genug, dass
  es sich kaputt anfühlte.
- **Am PC hing die App.** Wenn es die Anmelde-Prüfung erwischte, hielt die App
  das für „nicht angemeldet" und warf einen zurück auf den Login. Erwischte es
  die Terminliste, blieb sie leer.

**Was jetzt anders ist.** Der Server erlaubt der Datenbankverbindung
ausdrücklich den Thread-Wechsel innerhalb einer Anfrage. Das ist gefahrlos,
weil jede Anfrage ihre eigene Verbindung hat und sie nacheinander benutzt.
Nachgemessen mit 180 gleichzeitigen Anfragen: **vorher Ausfälle, jetzt alle
grün.**

**Zwei Schutznetze in der App obendrauf**, damit ein Server-Schluckauf nie
wieder wie ein Defekt aussieht:

- Ein Serverfehler beim Start bedeutet **nicht mehr „abgemeldet"**. Wer sich
  einmal angemeldet hat, arbeitet weiter, statt grundlos auf dem Login zu
  landen.
- Die Anmelde-Prüfung beim Start hat jetzt ein **Zeitlimit von 6 Sekunden**.
  Bleibt der Server stumm, geht die App weiter — vorher konnte sie ewig im
  Ladebalken stehen.

*Hinweis: Dieses Update ändert auch `db.py` am Server, nicht nur die App.*

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
