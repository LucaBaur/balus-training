"use strict";

// ============================================================================
//  nav.js — Navigation als reine Daten (ohne Oberfläche), nach Rolle getrennt.
//
//  Spielerin: vier Reiter (Home, Termine, Videos, Playbook). Ihr Profil, die
//  To-Dos und die Mitteilungen liegen hinter dem Kreis oben rechts und sind
//  trotzdem über gehe("ich", …) erreichbar (`ohneTab`).
//  Trainer: Home, Training, Team, Taktik, Saison wie bisher.
//
//  Gleiche Schlüssel dürfen für beide Rollen vorkommen (training, taktik, home);
//  wer was sieht, entscheidet `rollen`. Was beim Öffnen passiert (`init`), kennt
//  nur app.js — hier stehen nur Namen, damit sich das testen lässt.
//  Das ist KEINE Sicherheitsgrenze: Rechte erzwingt der Server.
// ============================================================================

(function () {
  const BEIDE = ["trainer", "spieler"];
  const u = (key, label, view, extra) => ({ key, label, view, ...(extra || {}) });

  const NAV = [
    { key: "home", label: "Home", icon: "home", rollen: ["trainer"], unter: [
      u("home", "Übersicht", "view-home"),
      u("liga", "Liga", "view-liga"),
    ]},
    { key: "home", label: "Home", icon: "home", rollen: ["spieler"], unter: [
      u("home", "Übersicht", "view-home"),
      u("liga", "Liga", "view-liga", { versteckt: true }),     // über die Tabellen-Karte erreichbar
    ]},
    // Profil hinter dem Kreis oben rechts. Auch Trainerinnen, die selbst mitspielen, haben es.
    { key: "ich", label: "Ich", icon: "user", rollen: BEIDE, nurMitProfil: true, ohneTab: true, unter: [
      u("ich", "Mein Profil", "view-ich"),
      u("todo", "To-Dos", "view-todo"),
    ]},
    { key: "konto", label: "Konto", icon: "user", rollen: BEIDE, ohneTab: true, unter: [
      u("mitteilungen", "Mitteilungen", "view-mitteilungen"),
    ]},
    { key: "training", label: "Training", icon: "clipboard", rollen: ["trainer"], unter: [
      u("trainings", "Termine", "view-trainings"),
      u("aufstellung", "Aufstellung", "view-aufstellung"),
      u("teams", "Einteilung", "view-anwesenheit"),
      u("uebungen", "Übungen", "view-wiki"),
      u("coach", "Coach", "view-coach"),
    ]},
    { key: "training", label: "Termine", icon: "calendar", rollen: ["spieler"], unter: [
      u("trainings", "Termine", "view-trainings"),
      u("aufstellung", "Aufstellung", "view-aufstellung"),
    ]},
    { key: "videos", label: "Videos", icon: "video", rollen: ["spieler"], nurMitProfil: true, unter: [
      u("videos", "Videos", "view-videos"),
    ]},
    { key: "team", label: "Team", icon: "users", rollen: ["trainer"], unter: [
      u("rangliste", "Rangliste", "view-rangliste"),
      u("kader", "Kader", "view-kader"),
      u("statistik", "Statistik", "view-wiki"),
      u("videos", "Videos", "view-videos"),
      u("nutzung", "Nutzung", "view-nutzung"),
      u("todos", "To-Dos", "view-todo-team"),
    ]},
    { key: "taktik", label: "Taktik", icon: "target", rollen: ["trainer"], unter: [
      u("playbook", "Playbook", "view-wiki"),
      u("gegner", "Gegner", "view-wiki"),
    ]},
    { key: "taktik", label: "Playbook", icon: "target", rollen: ["spieler"], unter: [
      u("playbook", "Playbook", "view-wiki"),
    ]},
    { key: "saison", label: "Saison", icon: "trophy", rollen: ["trainer"], unter: [
      u("orga", "Orga", "view-wiki"),
      u("statspiele", "Statistik Spiele", "view-statspiele"),
      u("notizen", "Notizen", "view-wiki"),
      u("aemter", "Ämter", "view-aemter"),
      u("listen", "Listen", "view-listen"),
      u("kasse", "Kasse", "view-kasse"),
    ]},
    // Ämter der Mannschaft. Spielerinnen haben dafür einen eigenen Reiter, der Trainer erreicht
    // dieselben Seiten unter Saison (sechs Reiter wären zu viel).
    { key: "mannschaft", label: "Mannschaft", icon: "users", rollen: ["spieler"], nurMitProfil: true, unter: [
      u("aemter", "Ämter", "view-aemter"),
      u("listen", "Listen", "view-listen"),
      u("kasse", "Kasse", "view-kasse"),
    ]},
  ];

  const sichtbar = (o, rolle, hatProfil) =>
    o.rollen.includes(rolle) && (!o.nurMitProfil || !!hatProfil);

  // Alle Überpunkte, die diese Rolle erreichen darf (mit oder ohne Reiter).
  const oberFuer = (rolle, hatProfil) => NAV.filter((o) => sichtbar(o, rolle, hatProfil));

  // Die Reiter der unteren Leiste.
  const tabs = (rolle, hatProfil) => oberFuer(rolle, hatProfil).filter((o) => !o.ohneTab);

  // Die Unterleiste unter dem Kopf; Versteckte bleiben erreichbar, stehen dort aber nicht.
  const subnav = (ober) => ober.unter.filter((x) => !x.versteckt);

  // Ziel auflösen; ein unbekannter Unterpunkt fällt auf den ersten zurück.
  function finde(rolle, hatProfil, oberKey, unterKey) {
    const ober = oberFuer(rolle, hatProfil).find((o) => o.key === oberKey);
    if (!ober) return null;
    return { ober, unter: ober.unter.find((x) => x.key === unterKey) || ober.unter[0] };
  }

  window.NavKonfig = { NAV, oberFuer, tabs, subnav, finde };
})();
