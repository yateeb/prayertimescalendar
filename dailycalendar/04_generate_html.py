#!/usr/bin/env python3
"""
04_generate_html.py
-------------------
Generates a print-ready HTML daily calendar for 2027.
Page size: 127 mm × 102 mm (landscape-ish).

Each physical day = 2 HTML pages in the output:
  Front – header (Ayet/Hadis | Date | Olay) + 28-city prayer times table
  Back  – Islamic reminder (Konu + Metin + Dua) – translated to Norwegian

Page order in HTML: front₁, back₁, front₂, back₂ … (duplex-friendly)

Reads:
  dailycalendar/data/prayer_times_2027.json
  dailycalendar/data/reminders_no.json    (preferred)
  dailycalendar/data/reminders_tr.json    (fallback if translation missing)

Output:
  dailycalendar/output/kalender-2027-daglig.html
"""

import base64
import json
from html import escape as esc
from pathlib import Path

HERE     = Path(__file__).resolve().parent
LOGO     = HERE.parent / "logo.png"
PRAYER   = HERE / "data" / "prayer_times_2027.json"
REM_NO   = HERE / "data" / "reminders_no.json"
REM_TR   = HERE / "data" / "reminders_tr.json"
OUTPUT   = HERE / "output" / "kalender-2027-daglig.html"

# Cities in Norwegian alphabetical order (Æ, Ø, Å come after Z)
CITY_LEFT = [
    "Badsø", "Bastøy", "Bergen", "Bjørgvin", "Bodø", "Eidsberg",
    "Froland", "Halden", "Hamar", "Hustad", "Ila", "Kongsvinger",
    "Kroksrud", "Mandal",
]
CITY_RIGHT = [
    "Ringerike", "Sandeid", "Sarpsborg", "Sem", "Skien", "Stavanger",
    "Tromsø", "Trondheim", "Trøgstad", "Tønsberg", "Ullersmo", "Vik",
    "Ålesund", "Åna",
]

PRAYER_KEYS  = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
PRAYER_HEADS = ["Fajr", "Sol↑", "Zuhr", "Asr", "Maghr", "Isha"]

# ── CSS ──────────────────────────────────────────────────────────────────────
CSS = """
@page { size: 127mm 102mm; margin: 1.5mm; }
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 6pt; color: #111; }

/* ── shared page shell ── */
.page {
  width: 124mm;
  height: 99mm;
  overflow: hidden;
  page-break-after: always;
  position: relative;
}
.page:last-child { page-break-after: auto; }

/* ────────────────────────── FRONT PAGE ───────────────────────────────── */

/* Make the front page a flex column so prayer area fills all leftover height */
.front {
  display: flex;
  flex-direction: column;
  padding: 1mm 1.5mm 0.5mm;
}

.front .header {
  display: flex;
  flex-shrink: 0;
  border-bottom: 0.35mm solid #1a3a5c;
  padding-bottom: 0.8mm;
  margin-bottom: 0.8mm;
  gap: 1mm;
}

/* Left column – Ayet / Hadis */
.col-ayet {
  width: 36mm;
  padding: 0.5mm 1mm 0.5mm 0;
  border-right: 0.2mm solid #c0cfe0;
  overflow: hidden;
}
.col-ayet h4 {
  font-size: 4.5pt;
  font-weight: bold;
  color: #1a3a5c;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  margin-bottom: 0.5mm;
}
.col-ayet p {
  font-size: 5pt;
  font-style: italic;
  color: #333;
  line-height: 1.35;
}

/* Centre column – Date block */
.col-date {
  flex: 1;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.1mm;
}
.date-num {
  font-size: 26pt;
  font-weight: 900;
  color: #1a3a5c;
  line-height: 1;
}
.date-wd {
  font-size: 7pt;
  font-weight: bold;
  color: #222;
  letter-spacing: 0.03em;
}
.date-mth {
  font-size: 6.5pt;
  color: #333;
}
.date-hijri {
  font-size: 5pt;
  color: #555;
}
.date-doy {
  font-size: 4.5pt;
  color: #888;
  margin-top: 0.3mm;
}

/* Right column – Olay (historical events) */
.col-olay {
  width: 36mm;
  padding: 0.5mm 0 0.5mm 1mm;
  border-left: 0.2mm solid #c0cfe0;
  overflow: hidden;
}
.col-olay h4 {
  font-size: 4.5pt;
  font-weight: bold;
  color: #1a3a5c;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  margin-bottom: 0.5mm;
}
.col-olay p {
  font-size: 5pt;
  color: #333;
  line-height: 1.35;
}

/* ── Prayer-times section ── */
.prayer-area {
  flex: 1;                  /* grow to fill remaining page height */
  display: flex;
  gap: 0;
  position: relative;
}
/* Logo watermark centred behind both tables */
.prayer-area::before {
  content: '';
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 75mm; height: 75mm;
  background: url("__LOGO_URI__") no-repeat center center;
  background-size: contain;
  opacity: 0.05;
  pointer-events: none;
  z-index: 2;
}
.prayer-wrap {
  flex: 1;
  overflow: hidden;
  position: relative;
  z-index: 1;
}
.prayer-wrap:first-child { border-right: 0.3mm solid #c0cfe0; padding-right: 0.3mm; }
.pt {
  border-collapse: collapse;
  width: 100%;
  height: 100%;             /* stretch rows to fill the prayer-wrap */
  font-size: 6pt;
}
.pt thead tr th {
  background: #1a3a5c;
  color: #fff;
  padding: 0.8mm 0.3mm;
  text-align: center;
  font-size: 5.5pt;
  font-weight: bold;
  white-space: nowrap;
}
.pt thead tr th.ch {
  text-align: left;
  padding-left: 0.8mm;
}
.pt tbody tr td {
  padding: 0.5mm 0.3mm;
  text-align: center;
  border-bottom: 0.15mm solid #d8e8f4;
  color: #1a4060;
  font-size: 6pt;
}
.pt tbody tr td.city {
  text-align: left;
  font-weight: 600;
  color: #1a3a5c;
  padding-left: 0.8mm;
  white-space: nowrap;
  overflow: hidden;
  max-width: 16mm;
}
.pt tbody tr:nth-child(even) td { background: #e6f0f9; }
.pt tbody tr:nth-child(odd)  td { background: #f4f9fd; }

/* ────────────────────────── BACK PAGE ────────────────────────────────── */

.back {
  padding: 2mm 2.5mm 1.5mm;
  height: 99mm;
  display: flex;
  flex-direction: column;
  background: #fafcff;
}
.back-konu {
  font-size: 7.5pt;
  font-weight: bold;
  color: #1a3a5c;
  text-align: center;
  border-bottom: 0.5mm solid #1a3a5c;
  padding-bottom: 1mm;
  margin-bottom: 1.5mm;
  line-height: 1.25;
}
.back-metin {
  font-size: 5.5pt;
  line-height: 1.4;
  text-align: justify;
  color: #1a1a1a;
  flex: 1;
  overflow: hidden;
  hyphens: auto;
}
.back-dua {
  margin-top: 1.5mm;
  padding: 1mm 1.5mm;
  background: #e8f0fb;
  border: 0.3mm solid #2c5f8a;
  border-radius: 0.8mm;
  flex-shrink: 0;
}
.dua-label {
  font-size: 4.5pt;
  font-weight: bold;
  color: #1a3a5c;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.dua-text {
  font-size: 5pt;
  font-style: italic;
  color: #1a3a5c;
  line-height: 1.35;
  margin-top: 0.3mm;
}
.dua-arabic {
  font-size: 7pt;
  color: #1a3a5c;
  text-align: right;
  direction: rtl;
  line-height: 1.6;
  margin-top: 1mm;
  font-family: 'Traditional Arabic', 'Scheherazade New', serif;
}
.dua-translit {
  font-size: 4.8pt;
  color: #2c5f8a;
  font-style: italic;
  line-height: 1.4;
  margin-top: 0.5mm;
  border-top: 0.15mm solid #b0c8e8;
  padding-top: 0.4mm;
}

/* ── Screen preview ── */
@media screen {
  body { background: #3a3a3a; padding: 10px; }
  .page {
    background: #fff;
    margin: 6px auto;
    box-shadow: 0 2px 10px rgba(0,0,0,.45);
  }
}
"""

# ── helpers ──────────────────────────────────────────────────────────────────

def _p(text: str, cls: str = "") -> str:
    """Wrap escaped text in <p>."""
    cls_attr = f' class="{cls}"' if cls else ""
    return f"<p{cls_attr}>{esc(text)}</p>"


def prayer_table(cities: list[str], city_data: dict) -> str:
    """Build one half-page prayer-time <table>."""
    heads = "".join(
        f'<th class="ch">Sted</th>' +
        "".join(f"<th>{h}</th>" for h in PRAYER_HEADS)
    )
    rows = []
    for city in cities:
        times = city_data.get(city, {})
        cells = "".join(
            f"<td>{esc(times.get(k, '—'))}</td>" for k in PRAYER_KEYS
        )
        rows.append(
            f'<tr><td class="city">{esc(city)}</td>{cells}</tr>'
        )
    return (
        '<table class="pt">'
        f"<thead><tr>{heads}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def front_page(date_str: str, meta: dict, rem: dict) -> str:
    hijri = meta.get("hijri", {})
    ayet  = rem.get("ayet_hadis", "")
    olay  = rem.get("olay", "")
    cities_data = meta.get("cities", {})

    hijri_str = (
        f"{hijri.get('day', '')} {hijri.get('month', '')} {hijri.get('year', '')} H"
    )
    doy       = meta.get("day_of_year", "")
    days_left = meta.get("days_left", "")

    header = f"""
<div class="header">
  <div class="col-ayet">
    <h4>Ayet / Hadis</h4>
    <p>{esc(ayet)}</p>
  </div>
  <div class="col-date">
    <div class="date-num">{meta.get('day', ''):02d}</div>
    <div class="date-wd">{esc(meta.get('weekday', ''))}</div>
    <div class="date-mth">{esc(meta.get('month', ''))} {meta.get('year', '')}</div>
    <div class="date-hijri">{esc(hijri_str)}</div>
    <div class="date-doy">Dag {doy} &nbsp;·&nbsp; {days_left} igjen</div>
  </div>
  <div class="col-olay">
    <h4>Historisk</h4>
    <p>{esc(olay)}</p>
  </div>
</div>"""

    prayers = f"""
<div class="prayer-area">
  <div class="prayer-wrap">{prayer_table(CITY_LEFT,  cities_data)}</div>
  <div class="prayer-wrap">{prayer_table(CITY_RIGHT, cities_data)}</div>
</div>"""

    return (
        f'<div class="page front" data-date="{date_str}">'
        f"{header}{prayers}"
        f"</div>"
    )


def back_page(date_str: str, rem: dict) -> str:
    konu        = rem.get("konu",  "")
    metin       = rem.get("metin", "")
    dua         = rem.get("dua",   "")
    dua_arabic  = rem.get("dua_arabic",  "")
    dua_translit= rem.get("dua_translit","")

    # Convert newlines in metin to <br> tags for display
    metin_html = "<br>".join(esc(line) for line in metin.splitlines()) if metin else ""

    dua_block = ""
    if dua:
        arabic_html = (
            f'<div class="dua-arabic">{esc(dua_arabic)}</div>'
            if dua_arabic else ""
        )
        translit_html = (
            f'<div class="dua-translit">{esc(dua_translit)}</div>'
            if dua_translit else ""
        )
        dua_block = (
            '<div class="back-dua">'
            '<div class="dua-label">Dua</div>'
            f'<div class="dua-text">{esc(dua)}</div>'
            f'{arabic_html}'
            f'{translit_html}'
            "</div>"
        )

    return (
        f'<div class="page back" data-date="{date_str}">'
        f'<div class="back">'
        f'<div class="back-konu">{esc(konu)}</div>'
        f'<div class="back-metin">{metin_html}</div>'
        f"{dua_block}"
        f"</div>"
        f"</div>"
    )


def build_html(pages_html: list[str], logo_uri: str = "") -> str:
    body = "\n".join(pages_html)
    css  = CSS.replace("__LOGO_URI__", logo_uri)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="no">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        "<title>Bønnetidskalender 2027 – Daglig</title>\n"
        f"<style>{css}</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def main():
    OUTPUT.parent.mkdir(exist_ok=True)

    # Embed logo as inline base64 so the watermark works when printing / offline
    logo_uri = ""
    if LOGO.exists():
        logo_b64 = base64.b64encode(LOGO.read_bytes()).decode()
        logo_uri = f"data:image/png;base64,{logo_b64}"
        print(f"Logo: {LOGO.name} ({len(logo_b64)//1024} KB base64)")
    else:
        print(f"Warning: logo not found at {LOGO}")

    if not PRAYER.exists():
        print(f"ERROR: {PRAYER} not found.\nRun 02_prayer_times.py first.")
        raise SystemExit(1)

    prayer_data: dict = json.loads(PRAYER.read_text(encoding="utf-8"))
    print(f"Prayer data: {len(prayer_data)} days")

    # Load both sources; Norwegian preferred per day, Turkish as fallback
    rem_tr: dict = {}
    rem_no: dict = {}
    if REM_TR.exists():
        rem_tr = json.loads(REM_TR.read_text(encoding="utf-8"))
    if REM_NO.exists():
        rem_no = json.loads(REM_NO.read_text(encoding="utf-8"))
        print(f"Reminders: {len(rem_no)} Norwegian + {len(rem_tr) - len(rem_no)} Turkish fallback entries")
    elif rem_tr:
        print(f"Reminders: {len(rem_tr)} Turkish entries (translation not yet run)")
    else:
        print(f"ERROR: No reminder data found.\nRun 01_extract_reminders.py first.")
        raise SystemExit(1)

    def get_reminder(date_str: str) -> dict:
        """Return Norwegian if translated, else Turkish fallback."""
        return rem_no.get(date_str) or rem_tr.get(date_str, {})

    pages: list[str] = []
    sorted_dates = sorted(prayer_data.keys())

    for date_str in sorted_dates:
        meta = prayer_data[date_str]
        rem  = get_reminder(date_str)
        pages.append(front_page(date_str, meta, rem))
        pages.append(back_page(date_str, rem))

    html = build_html(pages, logo_uri=logo_uri)
    OUTPUT.write_text(html, encoding="utf-8")

    size_kb = OUTPUT.stat().st_size // 1024
    print(f"Generated {len(sorted_dates)} days ({len(pages)} pages) → {OUTPUT}  [{size_kb} KB]")


if __name__ == "__main__":
    main()
