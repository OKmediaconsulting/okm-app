"""
Woechentliche Canva-Post-Texte: nutzt das bestehende Kundenprofil aus
scripts_tools.py (Branche, Zielgruppe, Ziele, Tonalitaet, Leistungen) und
waehlt Bilder aus dem hinterlegten Medien-Ordner.
"""

from __future__ import annotations

import json
import os
import random

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
CONTENT_MODEL = "claude-sonnet-5"
POSTS_PRO_LAUF = 3


def list_images(medien_pfad: str) -> list:
    """Findet Bilder auch in Unterordnern (z.B. wenn der Nutzer einen 'logo'-Ordner reinzieht)."""
    if not medien_pfad or not os.path.isdir(medien_pfad):
        return []
    found = []
    for root, _dirs, files in os.walk(medien_pfad):
        for f in files:
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                found.append(os.path.join(root, f))
    return sorted(found)


def _is_logo(path: str) -> bool:
    """Datei oder ihr (Unter-)Ordner enthaelt 'logo' im Namen."""
    return "logo" in path.lower()


def pick_logo(medien_pfad: str):
    imgs = list_images(medien_pfad)
    logos = [p for p in imgs if _is_logo(p)]
    return logos[0] if logos else (imgs[0] if imgs else None)


def pick_photos(medien_pfad: str, count: int, used: list) -> tuple:
    """Returns (chosen_paths, updated_used_list). Bevorzugt zuletzt nicht genutzte Fotos."""
    imgs = [p for p in list_images(medien_pfad) if not _is_logo(p)]
    if not imgs:
        return [], used

    unused = [p for p in imgs if p not in used]
    pool = unused if len(unused) >= count else imgs
    random.shuffle(pool)
    chosen = (pool * ((count // len(pool)) + 1))[:count]

    new_used = (used + chosen)[-max(len(imgs) * 2, count):]
    return chosen, new_used


async def generate_weekly_posts(ai, kunde: dict) -> list:
    """Erzeugt POSTS_PRO_LAUF Post-Konzepte basierend auf dem vollen Kundenprofil."""
    prompt = f"""Du bist Social-Media-Texter bei OK Media Consulting, einer Marketingagentur. Erstelle {POSTS_PRO_LAUF} verschiedene Instagram/Facebook-Posting-Konzepte fuer den Kunden "{kunde['name']}".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KUNDENPROFIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Branche: {kunde.get('branche', '')}
Standort: {kunde.get('standort', '')}
Zielgruppe: {kunde.get('zielgruppe', '')}
Unternehmensziele: {kunde.get('ziele', '')}
Leistungen: {kunde.get('leistungen', '')}
Tonalitaet: {kunde.get('tonalitaet', '')}
Besonderheiten: {kunde.get('besonderheiten', '')}

Waehle {POSTS_PRO_LAUF} UNTERSCHIEDLICHE Blickwinkel aus den Unternehmenszielen/Leistungen (z.B. je ein Posting fuer Neukundengewinnung, Verkauf/Produkt, Werkstatt/Service — passend zur tatsaechlichen Branche des Kunden).

Pro Posting brauche ich:
- goal: welcher Blickwinkel/welches Ziel (kurz, 2-4 Woerter)
- headline: kurzer, knackiger Blickfang (max. 6 Woerter, Deutsch)
- subtext: 1-2 Saetze Beschreibungstext (Deutsch, einladend, konkret, keine Floskeln)
- cta: kurzer Call-to-Action (max. 5 Woerter)

Halte dich an die Tonalitaet des Kunden. Schreibe lokal, persoenlich und hochwertig - keine generischen Marketing-Phrasen. Antworte AUSSCHLIESSLICH mit einem JSON-Array von {POSTS_PRO_LAUF} Objekten, Felder: goal, headline, subtext, cta. Kein Text davor oder danach."""

    response = await ai.messages.create(
        model=CONTENT_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    text_blocks = [b.text for b in response.content if b.type == "text"]
    if not text_blocks:
        raise ValueError("Claude-Antwort enthielt keinen Text-Block")
    raw = text_blocks[0].strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        posts = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude-Antwort war kein gueltiges JSON: {e}\n{raw[:500]}")
    return posts
