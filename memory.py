"""
Jarvis — Langzeit-Gedächtnis
Speichert wichtige Informationen zwischen Sessions in memory.json.
"""
import json
import os
from datetime import datetime

MEMORY_PATH = os.path.expanduser("~/Library/Application Support/OKMediaCRM/jarvis_memory.json")


def load() -> dict:
    if not os.path.exists(MEMORY_PATH):
        return {"notizen": [], "letzte_themen": [], "aufgaben": []}
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"notizen": [], "letzte_themen": [], "aufgaben": []}


def save(data: dict):
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_notiz(text: str):
    data = load()
    data.setdefault("notizen", [])
    data["notizen"].insert(0, {
        "text": text,
        "datum": datetime.now().strftime("%d.%m.%Y %H:%M")
    })
    data["notizen"] = data["notizen"][:20]  # max 20 Notizen
    save(data)


def add_thema(thema: str):
    data = load()
    data.setdefault("letzte_themen", [])
    # Duplikate vermeiden
    data["letzte_themen"] = [t for t in data["letzte_themen"] if t["text"] != thema]
    data["letzte_themen"].insert(0, {
        "text": thema,
        "datum": datetime.now().strftime("%d.%m.%Y %H:%M")
    })
    data["letzte_themen"] = data["letzte_themen"][:10]
    save(data)


def add_aufgabe(text: str):
    data = load()
    data.setdefault("aufgaben", [])
    data["aufgaben"].insert(0, {
        "text": text,
        "datum": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "erledigt": False
    })
    save(data)


def erledige_aufgabe(index: int):
    data = load()
    offene = [a for a in data.get("aufgaben", []) if not a["erledigt"]]
    if 0 <= index < len(offene):
        offene[index]["erledigt"] = True
        save(data)


def als_prompt_block() -> str:
    """Gibt das Gedächtnis als kompakten Text-Block für den System-Prompt zurück."""
    data = load()
    lines = []

    themen = [t for t in data.get("letzte_themen", [])]
    if themen:
        lines.append("Letzte Themen: " + " | ".join(t["text"] for t in themen[:5]))

    notizen = data.get("notizen", [])
    if notizen:
        lines.append("Notizen: " + " | ".join(n["text"] for n in notizen[:5]))

    aufgaben = [a for a in data.get("aufgaben", []) if not a["erledigt"]]
    if aufgaben:
        lines.append("Offene Aufgaben: " + " | ".join(a["text"] for a in aufgaben[:5]))

    if not lines:
        return ""
    return "\n=== GEDÄCHTNIS ===\n" + "\n".join(lines) + "\n==="
