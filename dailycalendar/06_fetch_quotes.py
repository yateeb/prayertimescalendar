#!/usr/bin/env python3
"""
06_fetch_quotes.py
------------------
Fetches motivational quotes for each calendar date and translates them to Norwegian.

Source API : https://type.fit/api/quotes  (~1600 quotes, no auth, one call)
AI model   : google/gemini-3.1-pro-preview via OpenRouter

Output: data/quotes.json
Format: {
  "2027-01-01": {"title": "Vise ord", "quote": "...", "author": "..."},
  ...
}

Titles (bolker) assigned by AI based on content:
  Vise ord | Sitat | Til ettertanke | Dagens tanke | Inspirasjon | Tankefullt
"""

import json
import os
import random
import time
import urllib.request
import urllib.error
from pathlib import Path

from dotenv import load_dotenv
import requests

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL   = "google/gemini-3.1-pro-preview"

PRAYER     = HERE / "data" / "prayer_times_2027.json"
QUOTES_OUT = HERE / "data" / "quotes.json"

TITLES = ["Vise ord", "Sitat", "Til ettertanke", "Dagens tanke", "Inspirasjon", "Tankefullt"]

SYSTEM_PROMPT = (
    "Du hjelper med å lage en daglig kalender for norske fengselsinnsatte. "
    "Kalenderens mål er å gi håp, styrke og motivasjon. "
    "ALDRI oversett eller bruk sitater som er vulgære, seksuelle, voldelige, støtende eller nedlatende. "
    "Hvis sitatet er upassende, erstatt det med et lignende motivasjonsord fra en kjent historisk person. "
    "Velg alltid sitater som er oppløftende, tålmodighetsstyrkende eller visdomsfulle."
)

# Keywords that disqualify a quote from being used
BLOCK_WORDS = {
    "dick", "penis", "sex", "nude", "naked", "fuck", "shit", "ass", "bitch",
    "porn", "erotic", "rape", "murder", "kill", "cocaine", "drug", "alcohol",
    "beer", "drunk", "weed", "marijuana",
}


def is_safe_quote(text: str) -> bool:
    """Return False if the quote contains any blocked keywords."""
    words = text.lower().split()
    return not any(w.strip(".,!?;:") in BLOCK_WORDS for w in words)


def fetch_all_quotes() -> list[tuple[str, str]]:
    """
    Fetch ~500 motivational quotes from dummyjson.com (1454 total, paginated).
    No authentication required. Format: {"quote": "...", "author": "..."}
    """
    result: list[tuple[str, str]] = []
    # Fetch 5 pages × 100 = 500 quotes (more than enough for 365 days)
    for page in range(5):
        skip = page * 100
        url  = f"https://dummyjson.com/quotes?limit=100&skip={skip}"
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read())
                for q in data.get("quotes", []):
                    text   = (q.get("quote") or "").strip()
                    author = (q.get("author") or "Ukjent").strip()
                    if len(text) >= 30 and is_safe_quote(text):
                        result.append((text, author))
                print(f"  Page {page+1}: +{len(data.get('quotes',[]))} quotes (total {len(result)})")
                time.sleep(0.5)
                break
            except Exception as e:
                wait = 5 * (2 ** attempt)
                print(f"  Quote API error page {page+1} ({e}) – waiting {wait}s …")
                time.sleep(wait)
    random.shuffle(result)
    return result


def ai_process_quote(quote: str, author: str) -> dict:
    """
    Translate one quote to Norwegian and assign a category title.
    Returns dict: {"title": ..., "quote": ..., "author": ...}
    Single-quote mode keeps max_tokens low, bounding thinking time to ~20s/call.
    """
    user_msg = (
        f'Sitat (original engelsk):\n"{quote}"\n– {author}\n\n'
        "Oppgave:\n"
        "1. Oversett sitatet til norsk bokmål. Behold forfatterens navn slik det er.\n"
        "2. Velg én tittel fra denne listen som passer innholdet best:\n"
        "   Vise ord | Sitat | Til ettertanke | Dagens tanke | Inspirasjon | Tankefullt\n"
        "3. Returner BARE JSON uten markdown, nøyaktig dette formatet:\n"
        '{"title":"...","quote":"...","author":"..."}'
    )

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "Quote Translator",
    }
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "max_tokens": 1500,
        "temperature": 0.4,
    }

    for attempt in range(4):
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=body,
                timeout=60,
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()

            # Extract JSON object robustly (first { … last })
            start = raw.find("{")
            last_brace = raw.rfind("}")
            if start != -1 and last_brace != -1 and last_brace > start:
                raw = raw[start:last_brace+1]

            return json.loads(raw)

        except json.JSONDecodeError as e:
            snippet = raw[:80] if 'raw' in dir() else '?'
            print(f"  JSON error (attempt {attempt+1}): {e} – {snippet!r}")
            time.sleep(3 * (2 ** attempt))
        except Exception as e:
            wait = 5 * (2 ** attempt)
            print(f"  AI error (attempt {attempt+1}): {e} – waiting {wait}s …")
            time.sleep(wait)

    # Fallback: return original untranslated
    return {"title": "Vise ord", "quote": quote, "author": author}


def main():
    dates = sorted(json.loads(PRAYER.read_text(encoding="utf-8")).keys())

    results: dict = {}
    if QUOTES_OUT.exists():
        results = json.loads(QUOTES_OUT.read_text(encoding="utf-8"))
        print(f"Loaded {len(results)} existing entries.")

    remaining = [d for d in dates if not results.get(d, {}).get("quote")]
    print(f"Total dates: {len(dates)} | Remaining: {len(remaining)}")

    if not remaining:
        print("All dates already processed. Nothing to do.")
        return

    # Fetch all quotes in one API call (dummyjson.com, 491 quotes)
    print("Fetching quote pool from dummyjson.com …")
    quote_pool = fetch_all_quotes()
    print(f"  Got {len(quote_pool)} usable quotes.")

    if not quote_pool:
        print("ERROR: Could not fetch quotes. Aborting.")
        return

    # Ensure we have enough (cycle if needed)
    if len(quote_pool) < len(remaining):
        extra_copies = (len(remaining) // len(quote_pool)) + 1
        quote_pool = (quote_pool * extra_copies)[:len(remaining)]
        random.shuffle(quote_pool)

    for i, date_str in enumerate(remaining):
        quote, author = quote_pool[i]
        print(f"Processing {date_str} …", end=" ", flush=True)

        entry = ai_process_quote(quote, author)
        label   = entry.get("title", "?")
        snippet = entry.get("quote", "")[:60]
        print(f"{label} — {snippet}")

        results[date_str] = entry
        QUOTES_OUT.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        time.sleep(0.3)

    print(f"\nDone. {len(results)} dates saved to {QUOTES_OUT}")


if __name__ == "__main__":
    main()
