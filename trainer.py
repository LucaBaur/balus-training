"""Trainingsplan-Generierung ueber OpenRouter (offene Modelle).

Der Kern von Idee 2: aus der (transkribierten) Beschreibung des Trainers einen
strukturierten Handball-Trainingsplan erzeugen. Fehlen wesentliche Infos, gibt
das Modell Rueckfragen zurueck statt zu raten.

CLI-Test:
  python trainer.py "Wir wollen Tempospiel und erste Welle, 90 min, 14 Spielerinnen"
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests

BASIS = Path(__file__).parent
# Anbieter-neutral (OpenAI-kompatibel). Default: Groq (offene Modelle, zuverlaessig).
LLM_URL_DEFAULT = "https://api.groq.com/openai/v1/chat/completions"
# Modelle in Reihenfolge; bei Rate-Limit/Fehler wird das naechste probiert.
MODELLE_DEFAULT = "llama-3.3-70b-versatile,llama-3.1-8b-instant"
# Transkription (Sprachnachricht -> Text) ueber Groq Whisper.
STT_URL_DEFAULT = "https://api.groq.com/openai/v1/audio/transcriptions"
STT_MODELL_DEFAULT = "whisper-large-v3-turbo"

SYSTEM_PROMPT = """Du bist erfahrener Co-Trainer einer Frauen-Handballmannschaft \
(Bezirksoberliga) und erstellst Trainingsplaene auf Deutsch.

Fixer Rahmen (immer so, nie danach fragen):
- Trainingsdauer: 90 Minuten. Teile die Phasen-Zeiten sinnvoll auf (Summe = 90).
- Zielgruppe: Frauen, Bezirksoberliga.
- Anzahl Spielerinnen und Torhueterinnen stehen (falls bekannt) unter
  "Aktueller Rahmen" – plane die Uebungen fuer diese Anzahl.

Fester Phasen-Aufbau, IMMER in dieser Reihenfolge:
1. Einstimmung / Erwaermung
2. Aufwaermspiel
3. Aktives (dynamisches) Dehnen
4. Einpassen (Passformen zum Warmwerfen)
5. Torhueter einwerfen
6. Hauptteil – Schwerpunkt
7. Anwendung / Spielform
8. Abschlussspiel
9. Ausklang / Dehnen

Der Schwerpunkt (Phase 6) wird IMMER aus der Nachricht des Trainers abgeleitet.

Antworte in GENAU EINEM von zwei Formaten, ohne Code-Bloecke, ohne JSON:

1) Ist der Schwerpunkt unklar oder fehlt er: Antwort beginnt mit der Zeile
   RUECKFRAGEN, danach je Zeile eine kurze Frage mit "- " davor. Frage NUR zum
   Schwerpunkt/Inhalt – niemals nach Dauer, Anzahl oder Niveau.

2) Ist der Schwerpunkt klar: Antwort beginnt mit der Zeile PLAN, danach der Titel
   als Markdown-Ueberschrift "# <Titel>", danach der komplette Plan als Markdown
   mit allen 9 Phasen (Uebungen mit Aufbau, Ablauf, Coaching-Punkten und
   Material). Kurz und praxistauglich.

   Jede Phase MUSS eine Ueberschrift dieser Form haben, damit die App die
   Zeiten uebernehmen kann:
   ## <Nr>. <Phasenname> (<Minuten> min)
   Beispiel: "## 1. Einstimmung / Erwaermung (10 min)".
   Die Minuten aller neun Phasen ergeben zusammen 90."""


def load_env(pfad: Path | str = BASIS / ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    pfad = Path(pfad)
    if pfad.exists():
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            zeile = zeile.strip()
            if zeile and not zeile.startswith("#") and "=" in zeile:
                k, v = zeile.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("LLM_KEY", "GROQ_KEY", "OPENROUTER_KEY", "LLM_URL", "LLM_MODEL"):
        if os.getenv(k):
            env[k] = os.environ[k]
    return env


def _llm_key(env: dict[str, str]) -> str | None:
    return env.get("LLM_KEY") or env.get("GROQ_KEY") or env.get("OPENROUTER_KEY")


def frage_modell(messages: list[dict], env: dict[str, str]) -> tuple[str, str]:
    """Fragt die Modelle der Reihe nach; bei Rate-Limit/Fehler das naechste.
    Liefert (Antworttext, verwendetes Modell)."""
    key = _llm_key(env)
    if not key:
        raise RuntimeError("Kein LLM-Key in der .env (GROQ_KEY)")
    url = env.get("LLM_URL", LLM_URL_DEFAULT)
    modelle = [m.strip() for m in env.get("LLM_MODEL", MODELLE_DEFAULT).split(",")
               if m.strip()]
    letzter = "keine Modelle konfiguriert"
    for model in modelle:
        try:
            r = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "X-Title": "Handball-Trainingsbot",
                },
                json={"model": model, "messages": messages, "temperature": 0.7},
                timeout=120,
            )
        except requests.RequestException as e:
            letzter = f"{model}: {e}"
            continue
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"], model
        letzter = f"{model}: HTTP {r.status_code} {r.text[:160]}"
    raise RuntimeError("Alle Modelle fehlgeschlagen. Letzter Fehler: " + letzter)


def _entferne_fences(t: str) -> str:
    t = t.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[^\n]*\n", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


def transkribiere(audio: bytes, dateiname: str = "audio.webm",
                  env: dict[str, str] | None = None) -> str:
    """Sprachnachricht (Audio-Bytes) via Groq Whisper zu deutschem Text."""
    env = env or load_env()
    key = _llm_key(env)
    if not key:
        raise RuntimeError("Kein Key fuer STT (GROQ_KEY) in der .env")
    url = env.get("STT_URL", STT_URL_DEFAULT)
    model = env.get("STT_MODELL", STT_MODELL_DEFAULT)
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {key}"},
        files={"file": (dateiname, audio)},
        data={"model": model, "language": "de"},
        timeout=180,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"STT {r.status_code}: {r.text[:300]}")
    return r.json().get("text", "").strip()


def parse_antwort(text: str) -> dict:
    """Robustes Textprotokoll: erste Zeile RUECKFRAGEN oder PLAN."""
    t = _entferne_fences(text)
    lines = t.splitlines()
    erste = next((l for l in lines if l.strip()), "")
    kopf = erste.strip().lstrip("#*- ").upper()

    if kopf.startswith("RUECKFRAGEN") or kopf.startswith("RÜCKFRAGEN"):
        fragen = []
        for l in lines:
            s = l.strip()
            if s.startswith(("-", "*")) or re.match(r"^\d+[.)]", s):
                fragen.append(re.sub(r"^[-*\d.)\s]+", "", s).strip())
        if not fragen:  # Fallback: alle Zeilen nach der ersten
            fragen = [l.strip() for l in lines[1:] if l.strip()]
        return {"typ": "rueckfrage", "fragen": [f for f in fragen if f]}

    # sonst: Plan (auch wenn das PLAN-Tag mal fehlt)
    if kopf.startswith("PLAN"):
        idx = lines.index(erste)
        md = "\n".join(lines[idx + 1:]).strip()
    else:
        md = t
    m = re.search(r"^#+\s*(.+)$", md, re.M)
    titel = m.group(1).strip() if m else "Training"
    return {"typ": "plan", "titel": titel, "markdown": md}


_DAUER = re.compile(r"\(?\b(\d{1,3})\s*(?:min\.?|minuten|'|′)\b\)?", re.I)


def bloecke_aus_markdown(md: str) -> list[dict]:
    """Plantext in Bloecke zerlegen: jede Ueberschrift wird ein Block, die
    Zeilen darunter die Notiz.

    Zwei Welten muessen hier durch dieselbe Tuer: die handgeschriebenen Plaene
    ('# Erwaermung' + Stichpunkte, ohne Minuten) und die Coach-Plaene
    ('## 1. Einstimmung (10 min)'). Eine Minutenangabe in der Ueberschrift wird
    als Dauer uebernommen und aus dem Titel entfernt; fehlt sie, bleibt die
    Dauer leer - das ist erlaubt.
    """
    if not md or not md.strip():
        return []
    bloecke: list[dict] = []
    akt: dict | None = None
    vorspann: list[str] = []

    def schliesse():
        if akt is not None:
            akt["notiz"] = " · ".join(akt.pop("_zeilen"))[:500]
            bloecke.append(akt)

    for zeile in md.splitlines():
        kopf = re.match(r"^\s*#{1,6}\s*(.+?)\s*$", zeile)
        if kopf:
            schliesse()
            titel = kopf.group(1)
            dauer = None
            m = _DAUER.search(titel)
            if m:
                dauer = int(m.group(1))
                titel = _DAUER.sub("", titel, count=1)
            titel = re.sub(r"[*~_`]", "", titel)             # Markdown-Auszeichnung
            titel = re.sub(r"^\s*\d+[.)]\s*", "", titel)     # "1. " am Anfang
            akt = {"dauer_min": dauer, "titel": titel.strip()[:120] or "Block", "_zeilen": []}
            continue
        text = re.sub(r"^\s*[-*+]\s*", "", zeile).strip()
        if not text:
            continue
        if akt is None:
            vorspann.append(text)
        else:
            akt["_zeilen"].append(text)
    schliesse()

    if vorspann:                       # Text vor der ersten Ueberschrift
        bloecke.insert(0, {"dauer_min": None, "titel": "Vorbemerkung",
                           "notiz": " · ".join(vorspann)[:500]})
    return bloecke


def generiere(verlauf: list[dict], env: dict[str, str] | None = None,
              kontext: str | None = None) -> tuple[dict, str, str]:
    """verlauf: Liste von {'role','content'} (user/assistant, ohne system).
    kontext: optionale Rahmeninfos (z. B. Anzahl Spielerinnen/Torhueterinnen).
    Liefert (geparstes Ergebnis, Rohtext, verwendetes Modell)."""
    env = env or load_env()
    system = SYSTEM_PROMPT
    if kontext:
        system += f"\n\nAktueller Rahmen:\n{kontext}"
    messages = [{"role": "system", "content": system}] + verlauf
    roh, modell = frage_modell(messages, env)
    return parse_antwort(roh), roh, modell


def _cli() -> None:
    if len(sys.argv) < 2:
        print('Aufruf: python trainer.py "Beschreibung des Trainings"')
        return
    beschreibung = " ".join(sys.argv[1:])
    ergebnis, roh, modell = generiere([{"role": "user", "content": beschreibung}])
    typ = ergebnis.get("typ")
    print("=== Modell:", modell, "| TYP:", typ, "===")
    if typ == "rueckfrage":
        for f in ergebnis.get("fragen", []):
            print(" -", f)
    elif typ == "plan":
        print("Titel:", ergebnis.get("titel"))
        print(ergebnis.get("markdown", ""))
    else:
        print(roh)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
