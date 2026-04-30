#!/usr/bin/env python3
"""
03d_local_fix.py
----------------
Fast, API-free pass that applies deterministic text substitutions to
fix the most common Turkish remnants in reminders_no.json.

Handles:
  - Turkish-only Unicode chars: İ → I, ı → i, ğ → g (or context rules)
  - Term replacements: Camii → moske, Miraç → Miraj, etc.
  - Name normalisation: Şaban → Sha'ban, Ramazan → Ramadan, etc.

After this pass, run 03c_fix_turkish.py for the AI cleanup of what remains.
"""

import json
import re
from pathlib import Path

HERE    = Path(__file__).resolve().parent
NO_FILE = HERE / "data" / "reminders_no.json"

# ── Ordered substitution rules (applied top-to-bottom, case-sensitive first) ──
# Each entry: (pattern, replacement, use_regex)
RULES = [
    # ── Turkish Unicode characters ──
    ("İ",               "I",                False),   # U+0130 dotted capital I
    ("ı",               "i",                False),   # U+0131 dotless i
    # ğ: usually silent/lengthens vowel. Drop it in common patterns:
    ("ğ",               "",                 False),   # e.g. "Müdafaği" – rare
    # Ş in Islamic calendar month names
    ("Şaban",           "Sha'ban",          False),
    ("Şevval",          "Shawwal",          False),
    ("Şevvâl",          "Shawwal",          False),
    # Other common Ş words
    ("Şam",             "Damaskus",         False),
    ("Şeyh",            "Sheikh",           False),
    ("Şeyhi",           "Sheikhen",         False),
    # ş in month/common terms
    ("Ramazan",         "Ramadan",          False),
    # ── Islamic night/event names ──
    ("Miraç Kandili",   "Miraj-natten",     False),
    ("Regaip Kandili",  "Regaip-natten",    False),
    ("Beraat Kandili",  "Berat-natten",     False),
    ("Kadir Gecesi",    "Laylat al-Qadr",   False),
    ("Kadir gecesi",    "Laylat al-Qadr",   False),
    ("Miraç",           "Miraj",            False),
    # ── Architectural terms ──
    (r"\bCamii\b",      "moske",            True),
    (r"\bcamii\b",      "moske",            True),
    (r"\bCami\b",       "moske",            True),
    (r"\bcami\b",       "moske",            True),
    (r"\bKülliye\b",    "religiøst kompleks", True),
    (r"\bkülliye\b",    "religiøst kompleks", True),
    (r"\bMinare\b",     "minaret",          True),
    (r"\bminare\b",     "minaret",          True),
    (r"\bMinber\b",     "minbar",           True),
    (r"\bminber\b",     "minbar",           True),
    (r"\bTekke\b",      "sufi-losje",       True),
    (r"\btekke\b",      "sufi-losje",       True),
    (r"\bMedrese\b",    "madrasa",          True),
    (r"\bmedrese\b",    "madrasa",          True),
    # ── Titles ──
    (r"\bPaşa\b",       "Pasha",            True),
    (r"\bpaşa\b",       "Pasha",            True),
    # ── Other common Turkish terms ──
    (r"\bmutasavvıf\b", "sufi-mystiker",    True),
    (r"\bmutasavvif\b", "sufi-mystiker",    True),
    (r"\bfasıqlık\b",   "ugudelighet",      True),
    (r"\bfasıq\b",      "ugudig",           True),
    (r"\bfasiq\b",      "ugudig",           True),
    # Remaining ş after specific word fixes → sj (rough approximation)
    # Only do this for lowercase ş mid-word; proper names left alone
    # (handled last, after named patterns above)
    ("ş",               "sj",               False),
    ("Ş",               "Sj",               False),
]


def apply_rules(text: str) -> str:
    for pattern, repl, is_regex in RULES:
        if is_regex:
            text = re.sub(pattern, repl, text)
        else:
            text = text.replace(pattern, repl)
    return text


def main():
    no_data: dict = json.loads(NO_FILE.read_text(encoding="utf-8"))
    total   = len(no_data)
    changed = 0

    for date_str, entry in no_data.items():
        new_entry = {}
        entry_changed = False
        for field, text in entry.items():
            if not text:
                new_entry[field] = text
                continue
            fixed = apply_rules(text)
            new_entry[field] = fixed
            if fixed != text:
                entry_changed = True
        no_data[date_str] = new_entry
        if entry_changed:
            changed += 1

    NO_FILE.write_text(
        json.dumps(no_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Local fix applied to {changed}/{total} entries → {NO_FILE}")


if __name__ == "__main__":
    main()
