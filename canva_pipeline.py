"""
Glue: generiert die woechentlichen Posts fuer einen Kunden Ende-zu-Ende
(Claude-Text -> Bilder auswaehlen -> lokal als PNG rendern).
Nutzt von beitrag/Skripte-System unabhaengige Kundendaten aus scripts_tools.py.

Hinweis: urspruenglich ueber die Canva Autofill API geplant, aber das
Benennen von Datenfeldern in Brand Templates erfordert laut Canva
Canva Enterprise (nicht auf diesem Konto verfuegbar). Posts werden
stattdessen direkt per HTML/CSS -> PNG gerendert (post_renderer.py) und
im bestehenden "OK Media Skripte"-Ordner abgelegt.
"""

from __future__ import annotations

import json
import os
import re
import time

import canva_content as content
import post_renderer as renderer
import scripts_tools as store

SKRIPTE_ROOT = os.path.expanduser("~/Desktop/OK Media Skripte")
MONATE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
          "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "post"


async def run_kunde(ai, kid: int) -> list:
    kunde = store.kunde_detail(kid)
    if not kunde:
        raise ValueError("Kunde nicht gefunden")
    if not kunde.get("canva_medien_pfad"):
        raise ValueError(f"Kein Medien-Ordner fuer '{kunde['name']}' hinterlegt")

    medien_pfad = kunde["canva_medien_pfad"]
    posts_copy = await content.generate_weekly_posts(ai, kunde)

    logo_path = content.pick_logo(medien_pfad)
    try:
        used = json.loads(kunde.get("canva_used_photos") or "[]")
    except json.JSONDecodeError:
        used = []
    photos, new_used = content.pick_photos(medien_pfad, len(posts_copy), used)

    now = time.localtime()
    out_dir = os.path.join(SKRIPTE_ROOT, kunde["name"], str(now.tm_year), MONATE[now.tm_mon])
    date_str = time.strftime("%Y-%m-%d")

    results = []
    for i, post in enumerate(posts_copy):
        photo_path = photos[i] if i < len(photos) else None
        if not photo_path:
            continue
        filename = f"{date_str}_{_slug(post.get('goal', f'post-{i+1}'))}.png"
        output_path = os.path.join(out_dir, filename)
        await renderer.render_post(
            photo_path=photo_path,
            logo_path=logo_path,
            headline=post.get("headline", ""),
            subtext=post.get("subtext", ""),
            cta=post.get("cta", ""),
            output_path=output_path,
        )
        results.append({**post, "image_path": output_path})

    store.canva_posts_speichern(kid, results)
    store.canva_run_status_setzen(kid, json.dumps(new_used, ensure_ascii=False), "ok")
    return results


async def run_alle_kunden(ai) -> dict:
    """Fuer den woechentlichen Scheduler. Returns {kundenname: "ok" | "error: ..."}."""
    summary = {}
    for kunde in store.kunden_liste():
        if not kunde.get("canva_medien_pfad"):
            continue
        try:
            await run_kunde(ai, kunde["id"])
            summary[kunde["name"]] = "ok"
        except Exception as e:
            store.canva_run_status_setzen(kunde["id"], kunde.get("canva_used_photos") or "[]", f"error: {e}")
            summary[kunde["name"]] = f"error: {e}"
    return summary
