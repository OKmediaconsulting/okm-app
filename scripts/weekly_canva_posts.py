"""
Eigenstaendiger woechentlicher Runner - generiert Posts fuer alle Kunden
mit hinterlegtem Medien-Ordner, unabhaengig davon ob Jarvis
(net.okmediaconsulting.jarvis) gerade laeuft oder nicht.
Getriggert via launchd (com.jarvis.weeklycanva.plist).
"""

import argparse
import asyncio
import json
import os
import sys
import time

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WORKSPACE)
sys.path.insert(0, "/Users/user/Library/Python/3.9/lib/python/site-packages")

import anthropic  # noqa: E402

import canva_pipeline  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kid", type=int, help="Nur diesen einen Kunden generieren (statt alle)")
    args = parser.parse_args()

    with open(os.path.join(WORKSPACE, "config.json"), "r") as f:
        config = json.load(f)

    ai = anthropic.AsyncAnthropic(api_key=config["anthropic_api_key"])

    print(f"[weekly-posts] Start {time.strftime('%Y-%m-%d %H:%M')}", flush=True)
    if args.kid is not None:
        asyncio.run(canva_pipeline.run_kunde(ai, args.kid))
        print(f"[weekly-posts] Kunde {args.kid}: ok", flush=True)
    else:
        summary = asyncio.run(canva_pipeline.run_alle_kunden(ai))
        if not summary:
            print("[weekly-posts] Kein Kunde mit Medien-Ordner konfiguriert.", flush=True)
        for name, status in summary.items():
            print(f"[weekly-posts] {name}: {status}", flush=True)
    print(f"[weekly-posts] Fertig {time.strftime('%Y-%m-%d %H:%M')}", flush=True)


if __name__ == "__main__":
    main()
