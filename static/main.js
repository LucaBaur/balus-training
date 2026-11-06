import { ladeAemter, ladeListen } from "./features/aemter.js";
import { ladeAufstellung } from "./features/aufstellung.js";
import { starteCoach } from "./features/coach.js";
import { ladeSpieler, ladeTrainings } from "./features/einteilung.js";
import { ladeHome } from "./features/home.js";
import { ladeIch } from "./features/ich.js";
import { ladeKader, restoreAnytypeStatus } from "./features/kader.js";
import { ladeKasse } from "./features/kasse.js";
import { pruefeAnmeldung } from "./core/konto.js";
import { ladeLiga } from "./features/liga.js";
import { ladeMitteilungen } from "./features/mitteilungen.js";
import { ladeNutzung } from "./features/nutzung.js";
import { ladeRangliste } from "./features/spieler.js";
import { ladeStatistikSpiele } from "./features/statistik-spiele.js";
import { ladeStatus } from "./core/statuspunkt.js";
import { ladeTrainingsListe } from "./features/termine.js";
import { ladeTodo, ladeTodoTeam } from "./features/todos.js";
import { ladeVideos } from "./features/videos.js";
import { ladeWiki } from "./features/wiki.js";
import { gehe, setzeInit } from "./core/router.js";
import { aktBenutzer } from "./core/konto.js";
// Wichtig auch ohne den Namen: menue.js haengt beim Laden die Klick-Handler des Profilmenues
// (Kreis oben rechts) und der Darstellungs-Umschalter an. Ohne diesen Import wuerde es nie geladen.
import { setzeDarstellung } from "./core/menue.js";

// ================================================================ Navigation ==
//  Zwei Ebenen: unten die Reiter (#tableiste), oben die Unterpunkte des aktiven
//  Reiters (#subnav). Aufbau und Namen stehen als reine Daten in nav.js (NavKonfig);
//  hier steht nur, was beim Öffnen eines Unterpunkts geladen wird.
//
//  ROLLEN: Die Rolle filtert hier NUR die Sichtbarkeit - das ist KEINE
//  Sicherheitsgrenze. Rollen erzwingt der Server bei jeder Anfrage.
setzeInit({
  "home/home": ladeHome, "home/liga": ladeLiga,
  "ich/ich": ladeIch, "ich/todo": ladeTodo,
  "konto/mitteilungen": ladeMitteilungen,
  "training/trainings": ladeTrainingsListe, "training/aufstellung": ladeAufstellung,
  "training/teams": () => { ladeSpieler().catch(() => {}); ladeTrainings().catch(() => {}); },
  "training/uebungen": () => ladeWiki("uebung", "Übungen"),
  "training/coach": starteCoach,
  "videos/videos": ladeVideos,
  "team/rangliste": ladeRangliste, "team/kader": ladeKader,
  "team/statistik": () => ladeWiki("statistik", "Statistik"),
  "team/videos": ladeVideos, "team/nutzung": ladeNutzung, "team/todos": ladeTodoTeam,
  "taktik/playbook": () => ladeWiki("playbook", "Playbook"),
  "taktik/gegner": () => ladeWiki("gegner", "Gegnercheck"),
  "saison/orga": () => ladeWiki(["saison", "orga"], "Saison & Orga"),
  "saison/statspiele": ladeStatistikSpiele,
  "saison/aemter": ladeAemter, "saison/listen": ladeListen, "saison/kasse": ladeKasse,
  "mannschaft/aemter": ladeAemter, "mannschaft/listen": ladeListen, "mannschaft/kasse": ladeKasse,
  "saison/notizen": () => ladeWiki(["notiz", "besprechung"], "Notizen"),
});
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).catch(() => {});
  let neuladen = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (neuladen) return;
    neuladen = true;
    location.reload();          // bei neuem Service Worker automatisch frisch laden
  });
}
ladeStatus("App startet…", 60);
restoreAnytypeStatus();
ladeStatus("Anmeldung prüfen…", 85);
// Rolle kommt vom Server: /api/me -> appStarten() (angemeldet) bzw. zeigeLogin().
pruefeAnmeldung();

// Kleine, bewusste Schnittstelle fuer docs/anleitung-funktionen/aufnahmen.py (Browser-Automation) und die Konsole.
window.gehe = gehe;
window.setzeDarstellung = setzeDarstellung;
Object.defineProperty(window, "aktBenutzer", { get: () => aktBenutzer, configurable: true });

