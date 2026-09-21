#!/usr/bin/env python3
"""
Jarvis — Global Hotkey Trigger
Cmd+Shift+J → öffnet das Jarvis Morning Layout
"""

import subprocess
import os
from pynput import keyboard

LAYOUT_SCRIPT = os.path.join(os.path.dirname(__file__), "layout.scpt")

current_keys = set()

HOTKEY = {keyboard.Key.cmd, keyboard.Key.alt, keyboard.KeyCode.from_char('j')}

def on_press(key):
    current_keys.add(key)
    if all(k in current_keys for k in HOTKEY):
        print("[jarvis] Hotkey ausgelöst — Layout wird geöffnet", flush=True)
        subprocess.Popen(["osascript", LAYOUT_SCRIPT])

def on_release(key):
    current_keys.discard(key)

print("[jarvis] Hotkey-Trigger aktiv — Cmd+Option+J startet Jarvis", flush=True)

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
