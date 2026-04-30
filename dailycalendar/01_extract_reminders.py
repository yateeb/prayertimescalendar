#!/usr/bin/env python3
"""
01_extract_reminders.py
-----------------------
Extracts daily Islamic reminders from the Turkish xlsx file
(HT 2027_Arka_Sayfalar.xlsx) and maps them to 2027 dates
by day-of-year position.

Columns used (from "Bütün_Yil" sheet):
  B (index 1): Olay       – Historical / non-Islamic event note
  C (index 2): Ayet/Hadis – Quranic verse or Hadith
  D (index 3): Konu       – Topic title
  E (index 4): Metin      – Main educational text
  F (index 5): DUA        – Supplication / prayer

Output: dailycalendar/data/reminders_tr.json
"""

import csv
import datetime
import json
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
XLSX = HERE / "HT 2027_Arka_Sayfalar.xlsx"
OUTPUT = HERE / "data" / "reminders_tr.json"


def clean(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


def main():
    OUTPUT.parent.mkdir(exist_ok=True)

    wb = openpyxl.load_workbook(str(XLSX))
    ws = wb.active  # "Bütün_Yil" sheet

    # Collect all data rows (rows 3 onwards; rows 1-2 are headers)
    source_days = []
    for row in ws.iter_rows(min_row=3, values_only=True):
        if row[0] is None:
            continue
        source_days.append({
            "olay":      clean(row[1]),
            "ayet_hadis": clean(row[2]),
            "konu":      clean(row[3]),
            "metin":     clean(row[4]),
            "dua":       clean(row[5]),
        })

    print(f"Source: {len(source_days)} day entries extracted from xlsx")

    # Map to 2027 by day-of-year (2027 has 365 days)
    result = {}
    d = datetime.date(2027, 1, 1)
    for i in range(365):
        date_str = d.strftime("%Y-%m-%d")
        result[date_str] = source_days[i % len(source_days)]
        d += datetime.timedelta(days=1)

    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(result)} days → {OUTPUT}")


if __name__ == "__main__":
    main()
