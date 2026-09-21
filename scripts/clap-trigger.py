#!/usr/bin/env python3
"""
Jarvis — Double Clap Trigger (macOS)
Listens to mic. Detects two claps within 1.2s, min 0.1s apart.
On trigger: opens Jarvis in browser with morning routine autostart.
Restarts listening after COOLDOWN seconds so it can fire again.
"""

import sounddevice as sd
import numpy as np
import subprocess
import time
import os
import sys

LAYOUT_SCRIPT = os.path.join(os.path.dirname(__file__), "layout.scpt")

SAMPLE_RATE = 48000
BLOCK_SIZE = 1024
THRESHOLD = 0.15
MIN_GAP = 0.1
MAX_GAP = 1.2
COOLDOWN = 5.0

last_clap_time = 0.0
last_trigger_time = 0.0


def open_jarvis():
    """Open full morning layout via AppleScript."""
    subprocess.Popen(["osascript", LAYOUT_SCRIPT])
    print(f"[jarvis] Layout gestartet", flush=True)


def audio_callback(indata, frames, time_info, status):
    global last_clap_time, last_trigger_time

    now = time.time()

    # Ignore during cooldown after trigger
    if now - last_trigger_time < COOLDOWN:
        return

    rms = float(np.sqrt(np.mean(indata ** 2)))

    if rms > THRESHOLD:
        gap = now - last_clap_time

        if gap >= MIN_GAP:
            if gap <= MAX_GAP and last_clap_time > 0:
                print(f"[jarvis] Double clap! Firing morning routine.", flush=True)
                last_clap_time = 0.0
                last_trigger_time = now
                open_jarvis()
            else:
                print(f"[jarvis] First clap (rms={rms:.3f})", flush=True)
                last_clap_time = now


with sd.InputStream(
    device=2,
    samplerate=SAMPLE_RATE,
    blocksize=BLOCK_SIZE,
    channels=1,
    dtype="float32",
    callback=audio_callback,
):
    print("[jarvis] Listening for double clap... (Ctrl+C to stop)", flush=True)
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("[jarvis] Stopped.", flush=True)
