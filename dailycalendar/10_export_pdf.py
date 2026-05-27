#!/usr/bin/env python3
"""
10_export_pdf.py
----------------
Exports the generated HTML calendar to a print-ready PDF using Playwright
(headless Chromium).  The @page CSS rules in the HTML (127mm × 102mm) are
honoured exactly, so the output is ready for professional printing.

Usage:
    python dailycalendar/10_export_pdf.py [--input PATH] [--output PATH]

Defaults:
    input  : dailycalendar/output/kalender-2027-daglig.html
    output : dailycalendar/output/kalender-2027-daglig.pdf
"""

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE   = Path(__file__).resolve().parent
INPUT  = HERE / "output" / "kalender-2027-daglig.html"
OUTPUT = HERE / "output" / "kalender-2027-daglig.pdf"


def export_pdf(input_path: Path, output_path: Path) -> None:
    if not input_path.exists():
        sys.exit(f"[ERROR] Input file not found: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Rendering  : {input_path}")
    print(f"[INFO] Output PDF : {output_path}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()

        # Load the HTML file directly from disk
        page.goto(input_path.as_uri(), wait_until="networkidle")

        page.pdf(
            path=str(output_path),
            # Respect the @page size declared in the HTML CSS (127mm × 102mm).
            # Setting prefer_css_page_size=True tells Chromium to use whatever
            # size is declared in the stylesheet instead of the 'width'/'height'
            # kwargs below (which are ignored when this flag is True).
            prefer_css_page_size=True,
            print_background=True,
        )

        browser.close()

    size_kb = output_path.stat().st_size // 1024
    print(f"[OK]  PDF written ({size_kb:,} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export HTML calendar to PDF")
    parser.add_argument(
        "--input",
        type=Path,
        default=INPUT,
        help=f"Path to input HTML file (default: {INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help=f"Path to output PDF file (default: {OUTPUT})",
    )
    args = parser.parse_args()
    export_pdf(args.input, args.output)


if __name__ == "__main__":
    main()
