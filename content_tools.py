"""
Jarvis — Content Tools
Skript-Generierung, Markdown-Speicherung und PDF-Export für OK Media Consulting.
"""

import os
import re
import sys
from datetime import datetime

sys.path.insert(0, "/Users/user/Library/Python/3.9/lib/python/site-packages")
from fpdf import FPDF

# ── Pfade ────────────────────────────────────────────────────────────────────

OK_MEDIA_OS   = "/Users/user/Desktop/OK Media OS/02 Kunden"
SKRIPTE_ROOT  = "/Users/user/Desktop/OK Media Skripte"

KUNDEN = {
    # Suchbegriffe → Ordner + Kürzel + Desktop-Ordner
    "genesis verl":      {"ordner": "01 Genesis Vital Verl",        "kuerzel": "GNV", "desktop": "Genesis Verl"},
    "genesis hövelhof":  {"ordner": "01 Genesis Vital Hövelhof",    "kuerzel": "GNH", "desktop": "Genesis Hövelhof"},
    "genesis rietberg":  {"ordner": "01 Genesis Vital Rietberg",    "kuerzel": "GNR", "desktop": "Genesis Rietberg"},
    "genesis":           {"ordner": "01 Genesis Vital Verl",        "kuerzel": "GNV", "desktop": "Genesis Verl"},
    "browns":            {"ordner": "02 Browns Active Park",         "kuerzel": "BRO", "desktop": "Browns"},
    "browns active":     {"ordner": "02 Browns Active Park",         "kuerzel": "BRO", "desktop": "Browns"},
    "devk":              {"ordner": "03 DEVK Agentur Selent",        "kuerzel": "DEV", "desktop": "DEVK"},
    "werners":           {"ordner": "04 Werners Fahrrad Fach-Werk",  "kuerzel": "WER", "desktop": "Werners"},
    "werner":            {"ordner": "04 Werners Fahrrad Fach-Werk",  "kuerzel": "WER", "desktop": "Werners"},
    "fahrrad":           {"ordner": "04 Werners Fahrrad Fach-Werk",  "kuerzel": "WER", "desktop": "Werners"},
}

MONATE_DE = {
    "januar": "01 Januar", "februar": "02 Februar", "märz": "03 März",
    "april": "04 April", "mai": "05 Mai", "juni": "06 Juni",
    "juli": "07 Juli", "august": "08 August", "september": "09 September",
    "oktober": "10 Oktober", "november": "11 November", "dezember": "12 Dezember",
}

MONATE_NUM = {
    "01": "Januar", "02": "Februar", "03": "März", "04": "April",
    "05": "Mai", "06": "Juni", "07": "Juli", "08": "August",
    "09": "September", "10": "Oktober", "11": "November", "12": "Dezember",
}


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def find_kunde(name: str):
    n = name.lower().strip()
    if n in KUNDEN:
        return KUNDEN[n]
    for key, val in KUNDEN.items():
        if key in n or n in key:
            return val
    return None


def find_monat(text: str):
    t = text.lower()
    for key, val in MONATE_DE.items():
        if key in t:
            return val
    return None


def get_paths(kunde_info: dict, monat_ordner: str, jahr: str = "2026") -> dict:
    monat_name = monat_ordner.split(" ", 1)[1]
    # Interner Arbeitsordner (OK Media OS)
    base = f"{OK_MEDIA_OS}/{kunde_info['ordner']}/11 Content/{jahr}/{monat_ordner}"
    # Standard-Speicherpfad laut Content-Standard: Desktop/OK Media Skripte/[Kunde]/[Jahr]/[Monat]
    skripte_dir = f"{SKRIPTE_ROOT}/{kunde_info['desktop']}/{jahr}/{monat_name}"
    os.makedirs(base, exist_ok=True)
    os.makedirs(skripte_dir, exist_ok=True)
    dateiname = f"{kunde_info['desktop']}_{monat_name}_{jahr}_4_Reel_Skripte"
    return {
        "base": base,
        "skript_pdf_md": f"{base}/01 Skript-PDF.md",
        "finale_skripte": f"{base}/02 Finale Skripte.md",
        "themenhistorie": f"{base}/03 Themenhistorie.md",
        "contentanalyse": f"{base}/04 Contentanalyse.md",
        "skripte_dir": skripte_dir,
        "monat_name": monat_name,
        "pdf_filename": f"{skripte_dir}/{dateiname}.pdf",
        "md_filename":  f"{skripte_dir}/{dateiname}.md",
    }


def read_themenhistorie(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def next_skript_nummer(themenhistorie: str, kuerzel: str, jahr: str = "2026") -> int:
    pattern = rf"{kuerzel}-S-{jahr}-(\d+)"
    nummern = [int(m) for m in re.findall(pattern, themenhistorie)]
    return max(nummern, default=0) + 1


# ── Markdown speichern ────────────────────────────────────────────────────────

THEMEN_HISTORIE_TEMPLATE = """\
# Themenhistorie

| Skript-ID | Titel | Thema | Datum | Veröffentlicht |
|-----------|-------|-------|-------|----------------|
"""


def save_markdown(paths: dict, skripte: list, monat: str, jahr: str, kuerzel: str, kundenname: str):
    """Speichert die 4 Skripte als Markdown und aktualisiert die Themenhistorie."""
    # 1. Finale Skripte speichern
    lines = [f"# Finale Skripte — {monat} {jahr}\n\n"]
    lines.append("> Erstellt von Jarvis · OK Media Consulting\n\n---\n\n")
    for i, s in enumerate(skripte, 1):
        lines.append(f"## Skript {i}\n\n")
        lines.append(f"**ID:** {s['id']}  \n")
        lines.append(f"**Titel:** {s['titel']}  \n")
        lines.append(f"**Ziel:** {s['ziel']}  \n\n")
        lines.append(f"### HOOK\n> {s['hook']}\n\n")
        lines.append(f"### SKRIPT\n{s['skript']}\n\n")
        lines.append(f"### ABSCHLUSS\n{s['abschluss']}\n\n")
        lines.append(f"### CTA\n> {s['cta']}\n\n")
        lines.append(f"### JARVIS ANALYSE\n{s['analyse']}\n\n---\n\n")
    with open(paths["finale_skripte"], "w", encoding="utf-8") as f:
        f.writelines(lines)
    # Standard-Speicherort: Desktop/OK Media Skripte/[Kunde]/[Jahr]/[Monat]/
    with open(paths["md_filename"], "w", encoding="utf-8") as f:
        f.writelines(lines)

    # 2. Themenhistorie aktualisieren — Datei anlegen falls noch nicht vorhanden
    hist_path = paths["themenhistorie"]
    try:
        with open(hist_path, "r", encoding="utf-8") as f:
            hist = f.read()
    except FileNotFoundError:
        hist = THEMEN_HISTORIE_TEMPLATE

    datum = datetime.now().strftime("%d.%m.%Y")
    neue_zeilen = ""
    for s in skripte:
        neue_zeilen += f"| {s['id']} | {s['titel']} | {s.get('thema', s.get('ziel', ''))} | {datum} | Nein |\n"

    # Platzhalter ersetzen falls vorhanden, sonst anhängen
    if "| — | — | — | — | — |" in hist:
        hist = hist.replace("| — | — | — | — | — |", neue_zeilen.strip())
    else:
        hist = hist.rstrip() + "\n" + neue_zeilen

    with open(hist_path, "w", encoding="utf-8") as f:
        f.write(hist)


# ── PDF erstellen ─────────────────────────────────────────────────────────────

def _safe(text: str) -> str:
    """Ersetzt Zeichen die latin-1 nicht unterstützt."""
    return (text
        .replace("—", "-").replace("–", "-")
        .replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
        .replace("…", "...").replace("ä", "ae")
        .replace("ö", "oe").replace("ü", "ue")
        .replace("Ä", "Ae").replace("Ö", "Oe")
        .replace("Ü", "Ue").replace("ß", "ss")
        .replace("é", "e").replace("è", "e")
        .replace("à", "a").replace("ó", "o")
    )


class JarvisPDF(FPDF):
    def __init__(self, kundenname, monat, jahr):
        super().__init__()
        self.kundenname = kundenname
        self.monat = monat
        self.jahr = jahr

    def header(self):
        self.set_fill_color(10, 20, 40)
        self.rect(0, 0, 210, 18, "F")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(100, 180, 255)
        self.set_xy(10, 5)
        self.cell(0, 8, _safe(f"OK MEDIA CONSULTING  ·  {self.kundenname.upper()}  ·  {self.monat} {self.jahr}"), align="L")
        self.set_text_color(60, 120, 200)
        self.set_xy(10, 5)
        self.cell(0, 8, _safe("J.A.R.V.I.S. CONTENT SYSTEM"), align="R")
        self.ln(14)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, _safe(f"OK Media Consulting  ·  Erstellt von Jarvis  ·  Seite {self.page_no()}"), align="C")

    def title_page(self, skript_count=4):
        self.add_page()
        self.set_fill_color(10, 20, 40)
        self.rect(0, 0, 210, 297, "F")
        # Glow-Ring Simulation
        self.set_draw_color(30, 100, 200)
        self.set_line_width(0.5)
        self.ellipse(85, 80, 40, 40)
        self.set_draw_color(50, 140, 255)
        self.set_line_width(0.3)
        self.ellipse(80, 75, 50, 50)
        # Titel
        self.set_font("Helvetica", "B", 26)
        self.set_text_color(100, 180, 255)
        self.set_xy(0, 145)
        self.cell(210, 14, _safe(self.kundenname), align="C")
        self.set_font("Helvetica", "", 14)
        self.set_text_color(60, 120, 200)
        self.set_xy(0, 162)
        self.cell(210, 8, _safe(f"Skripte {self.monat} {self.jahr}"), align="C")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 80, 140)
        self.set_xy(0, 174)
        self.cell(210, 6, _safe(f"{skript_count} Reel-Skripte  ·  Social Media  ·  Druckbereit"), align="C")
        self.set_xy(0, 260)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(30, 60, 100)
        self.cell(210, 5, _safe("Erstellt von J.A.R.V.I.S.  ·  OK Media OS  ·  Streng vertraulich"), align="C")

    def section_header(self, text):
        self.set_fill_color(15, 35, 70)
        self.set_text_color(100, 180, 255)
        self.set_font("Helvetica", "B", 11)
        self.set_x(10)
        self.cell(190, 8, _safe(f"  {text}"), fill=True, ln=True)
        self.ln(3)

    def skript_block(self, nr, s):
        self.add_page()
        # Skript-Header
        self.set_fill_color(20, 50, 100)
        self.rect(10, self.get_y(), 190, 14, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 12)
        self.set_x(14)
        self.cell(100, 14, _safe(f"Skript {nr}  —  {s['titel']}"), ln=False)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(150, 200, 255)
        self.cell(0, 14, _safe(s['id']), align="R", ln=True)
        self.ln(4)

        def field(label, value, bold_value=False):
            if not value:
                return
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(80, 140, 220)
            self.set_x(12)
            self.cell(35, 5, _safe(label), ln=False)
            self.set_font("Helvetica", "B" if bold_value else "", 9)
            self.set_text_color(30, 30, 30)
            self.multi_cell(155, 5, _safe(value))
            self.ln(1)

        def block(label, value):
            if not value:
                return
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(80, 140, 220)
            self.set_x(12)
            self.cell(0, 5, _safe(label), ln=True)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(30, 30, 30)
            self.set_x(14)
            self.multi_cell(183, 5, _safe(value))
            self.ln(2)

        field("Ziel:", s.get("ziel", ""))
        self.ln(2)

        # Hook-Box
        self.set_fill_color(230, 240, 255)
        self.set_x(12)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(30, 80, 180)
        self.multi_cell(186, 6, _safe(f"HOOK:  {s.get('hook', '')}"), fill=True)
        self.ln(3)

        block("SKRIPT", s.get("skript", ""))
        block("ABSCHLUSS", s.get("abschluss", ""))

        # CTA-Box
        self.set_fill_color(220, 255, 230)
        self.set_x(12)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(20, 120, 60)
        self.multi_cell(186, 6, _safe(f"CTA:  {s.get('cta', '')}"), fill=True)
        self.ln(3)

        # Jarvis Analyse
        self.set_fill_color(245, 245, 200)
        self.set_x(12)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(100, 80, 0)
        self.cell(0, 5, _safe("JARVIS ANALYSE"), ln=True)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(60, 50, 0)
        self.set_x(14)
        self.multi_cell(183, 5, _safe(s.get("analyse", "")), fill=False)


def create_pdf(paths: dict, skripte: list, monat: str, jahr: str, kundenname: str, strategie: str = "") -> str:
    pdf = JarvisPDF(kundenname, monat, jahr)
    pdf.set_auto_page_break(auto=True, margin=15)

    # Titelseite
    pdf.title_page(len(skripte))

    # Übersichtsseite
    pdf.add_page()
    pdf.section_header("ÜBERSICHT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(30, 30, 30)
    pdf.set_x(12)
    pdf.multi_cell(186, 6, _safe(f"Kunde: {kundenname}\nMonat: {monat} {jahr}\nAnzahl Skripte: {len(skripte)}\nErstellt: {datetime.now().strftime('%d.%m.%Y')}"))
    pdf.ln(6)

    pdf.section_header("SKRIPT-IDs DIESES MONATS")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(30, 30, 30)
    for i, s in enumerate(skripte, 1):
        pdf.set_x(14)
        pdf.cell(0, 6, _safe(f"Skript {i}:  {s['id']}  -  {s['titel']}"), ln=True)
    pdf.ln(6)

    if strategie:
        pdf.section_header("JARVIS STRATEGIEANALYSE")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 30, 30)
        pdf.set_x(12)
        pdf.multi_cell(186, 6, _safe(strategie))

    # Skript-Seiten
    for i, s in enumerate(skripte, 1):
        pdf.skript_block(i, s)

    # Speichern
    pdf_path = paths["pdf_filename"]
    pdf.output(pdf_path)
    return pdf_path
