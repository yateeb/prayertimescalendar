#!/usr/bin/env python3
"""
03_translate.py
---------------
Translates Turkish Islamic reminders to Norwegian Bokmål using the
OpenRouter API (google/gemini-2.0-flash-001 by default).

Translates all 5 fields per day:
  olay       – Historical event note  (appears on front page)
  ayet_hadis – Quranic verse / Hadith (appears on front page)
  konu       – Topic title            (appears on back page)
  metin      – Main educational text  (appears on back page)
  dua        – Supplication           (appears on back page)

Reads  : dailycalendar/data/reminders_tr.json
Writes : dailycalendar/data/reminders_no.json  (with progress saving)

Resumable: already-translated dates are skipped on re-run.
API key is read from dailycalendar/.env (OPENROUTER_API_KEY=...).
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

HERE    = Path(__file__).resolve().parent
INPUT   = HERE / "data" / "reminders_tr.json"
OUTPUT  = HERE / "data" / "reminders_no.json"
ENV     = HERE / ".env"

MODEL   = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
BATCH   = 3    # days per first-pass API call
RETRY_BATCH = 1  # retry failed batches one day at a time

SYSTEM_PROMPT = """\
You are a professional translator specializing in Islamic educational texts.
Translate the provided Turkish text to formal Norwegian Bokmål (norsk bokmål).

Rules:
- Preserve Arabic Islamic terms as-is: Allah, Quran/Koran, Hadith, Sunnah,
  salat, dua, sahabi, names of prophets (Ibrahim, Musa, Isa, Muhammad s.a.v.),
  Sura/sure names, and honorifics (s.a.v., r.a., a.s.).
- Keep Quranic verse references in the format (SureName X:Y).
- Keep hadith collection names (Bukhari, Muslim, Tirmizi, etc.) unchanged.
- Keep personal names, city names and historical names unchanged.
- Use formal, respectful language appropriate for Islamic educational material.
- Return ONLY a valid JSON array – no markdown, no extra text.
"""


def load_env():
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def get_api_key() -> str:
    load_env()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        print("ERROR: OPENROUTER_API_KEY not found.\n"
              "Add it to dailycalendar/.env as:\n"
              "  OPENROUTER_API_KEY=sk-or-v1-...")
        sys.exit(1)
    return key


def translate_batch(batch: list[dict], api_key: str) -> list[dict]:
    """
    batch: list of dicts with keys date, olay, ayet_hadis, konu, metin, dua
    Returns same list with text fields translated to Norwegian.
    """
    user_prompt = (
        "Translate the following JSON array from Turkish to Norwegian Bokmål.\n"
        "Return ONLY the translated JSON array with the exact same structure.\n"
        "Keep the \"date\" field unchanged.\n\n"
        + json.dumps(batch, ensure_ascii=False)
    )

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 8192,
        },
        timeout=120,
    )
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences if the model wraps the JSON
    if content.startswith("```"):
        parts = content.split("```", 2)
        content = parts[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.rsplit("```", 1)[0]

    content = content.strip()

    # Fix common truncation: unterminated string / missing closing brackets.
    # Count unclosed quotes (odd = unterminated string value)
    # Strategy: if parse fails, close any open string then close the array.
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Attempt simple repair: truncate to last complete object
    # Find last complete '}' at top-level depth
    depth = 0
    last_complete = -1
    in_str = False
    escape_next = False
    for idx, ch in enumerate(content):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_str:
            escape_next = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    last_complete = idx

    if last_complete > 0:
        repaired = content[:last_complete + 1]
        # Wrap in array if not already
        stripped = repaired.strip()
        if not stripped.startswith("["):
            stripped = "[" + stripped + "]"
        else:
            # Close array
            stripped = stripped.rstrip() + "]"
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse model response as JSON (len={len(content)})")


def main():
    api_key = get_api_key()

    tr_data: dict = json.loads(INPUT.read_text(encoding="utf-8"))
    print(f"Loaded {len(tr_data)} Turkish entries")

    # Resume: load existing translations
    no_data: dict = {}
    if OUTPUT.exists():
        no_data = json.loads(OUTPUT.read_text(encoding="utf-8"))
        print(f"Already translated: {len(no_data)} entries")

    # Build pending list (preserve date order)
    pending = [
        {
            "date":       d,
            "olay":       v["olay"],
            "ayet_hadis": v["ayet_hadis"],
            "konu":       v["konu"],
            "metin":      v["metin"],
            "dua":        v["dua"],
        }
        for d, v in tr_data.items()
        if d not in no_data
    ]
    print(f"To translate: {len(pending)} entries\n")

    if not pending:
        print("Nothing to do.")
        return

    total   = len(pending)
    done    = 0
    consecutive_errors = 0

    for i in range(0, total, BATCH):
        batch = pending[i : i + BATCH]
        dates = f"{batch[0]['date']} … {batch[-1]['date']}"
        print(f"[{i+1:>3}/{total}] {dates} ...", end="", flush=True)

        try:
            translated = translate_batch(batch, api_key)
            for item in translated:
                date_str = item.get("date", "")
                if not date_str:
                    continue
                no_data[date_str] = {
                    "olay":       item.get("olay",       ""),
                    "ayet_hadis": item.get("ayet_hadis", ""),
                    "konu":       item.get("konu",       ""),
                    "metin":      item.get("metin",      ""),
                    "dua":        item.get("dua",        ""),
                }
                done += 1
            print(f" ✓ ({done} done)")
            consecutive_errors = 0

        except requests.HTTPError as exc:
            consecutive_errors += 1
            status = exc.response.status_code if exc.response is not None else 0
            print(f" HTTP {status}")
            wait = 30 if status == 429 else 10
            print(f"  → waiting {wait}s before retry...", flush=True)
            time.sleep(wait)
            # Re-insert batch at front of remaining work by continuing (not consumed)
            continue

        except Exception as exc:
            consecutive_errors += 1
            print(f" parse error ({exc.__class__.__name__}) – retrying 1-by-1")
            # Retry each day in the batch individually
            for item in batch:
                d = item["date"]
                if d in no_data:
                    continue
                print(f"    {d} ...", end="", flush=True)
                for attempt in range(3):
                    try:
                        result = translate_batch([item], api_key)
                        if result:
                            r = result[0]
                            no_data[d] = {
                                "olay":       r.get("olay",       ""),
                                "ayet_hadis": r.get("ayet_hadis", ""),
                                "konu":       r.get("konu",       ""),
                                "metin":      r.get("metin",      ""),
                                "dua":        r.get("dua",        ""),
                            }
                            done += 1
                            print(f" ✓")
                            consecutive_errors = 0
                            break
                    except requests.HTTPError as he:
                        status = he.response.status_code if he.response is not None else 0
                        wait = 30 if status == 429 else 10
                        print(f" HTTP {status}, wait {wait}s", end="", flush=True)
                        time.sleep(wait)
                    except Exception as e2:
                        print(f" ✗ ({e2.__class__.__name__})", end="", flush=True)
                        time.sleep(3)
                else:
                    print(f" SKIPPED after 3 attempts")

        # Save progress after every batch
        OUTPUT.write_text(
            json.dumps(no_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        time.sleep(1.2)  # polite rate-limiting

    print(f"\nFinished. {len(no_data)}/{len(tr_data)} days translated → {OUTPUT}")


if __name__ == "__main__":
    main()
