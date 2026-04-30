#!/usr/bin/env python3
"""
03c_fix_turkish.py
------------------
Scans reminders_no.json for remaining Turkish words/expressions
(missed during initial translation) and fixes them using OpenRouter.

Turkish indicators searched:
  - Turkish-specific characters: ş ğ İ ı Ş Ğ
  - Known untranslated Turkish terms: camii, kandili, paşa, efendi, etc.

Sends batches of 5 flagged entries to OpenRouter asking it to clean up
only the Turkish remnants while keeping the Norwegian text intact.

Reads / Writes: dailycalendar/data/reminders_no.json  (in-place update)
Resumable: tracks processed dates in dailycalendar/data/turkish_fixed.json
"""

import json
import os
import re
import time
from pathlib import Path

import requests

HERE       = Path(__file__).resolve().parent
NO_FILE    = HERE / "data" / "reminders_no.json"
DONE_FILE  = HERE / "data" / "turkish_fixed.json"
ENV        = HERE / ".env"

BATCH = 5

# Turkish-specific characters and known untranslated terms (case-insensitive flag at start)
TURKISH_RE = re.compile(
    r"(?i)[şğıŞĞ]"
    r"|(?<![A-Za-z])İ"
    r"|\bcamii\b"
    r"|\bkandili\b"
    r"|\bpaşa\b"
    r"|\befendi\b"
    r"|\bmutasavv\w+"
    r"|\bkülliye\b"
    r"|\btekke\b"
    r"|\bmedrese\b"
    r"|\bmihrab\b"
    r"|\bminare\b"
    r"|\bminber\b"
    r"|\büstad\b"
    r"|\büsküdar\b"
    r"|\beyüp\b"
    r"|\bfasıq\w*"
    r"|\bümmeti\b"
    r"|\bgazi\b"
    r"|\bbeylerbey\b"
)

SYSTEM = """\
You are editing Norwegian Bokmål Islamic educational text. The text has some
Turkish words and expressions that were NOT translated from Turkish.

Your task: replace ONLY the Turkish remnants with proper Norwegian Bokmål equivalents.
Leave all correct Norwegian text untouched. Leave Arabic Islamic terminology unchanged.

Specific rules:
- "Camii" / "camii" → "moske"
- "Miraç Kandili" → "Miraj-natten"
- "İstanbul" → "Istanbul"  (remove Turkish diacritic from İ)
- Any "İ" → "I"  (Turkish dotted capital I → regular I)
- "ş" → "sj" or natural Norwegian equivalent depending on context
- "ğ" → silent / drop or natural equivalent
- "ı" (dotless i) → "i"
- "Paşa" → "Pasha"
- "Bey" (Ottoman title) → "Bey" (acceptable loanword) or context-appropriate
- "Efendi" → "Efendi" (acceptable loanword, leave)
- "mutasavvıf" → "sufi-mystiker"
- "fasıqlık" / "fasıq" → "fordervelse" / "ugudelighet"
- "Külliye" → "religiøst kompleks"
- "Tekke" → "sufi-losje"
- "Medrese" → "madrasa"
- "Mihrab" → "mihrab" (leave – Arabic loanword used in Norwegian too)
- "Minare" → "minaret"
- "Minber" → "minbar"
- Turkish proper names of people: keep as-is (they are historical names)
- Turkish month names like "Şaban" → "Sha'ban", "Ramazan" → "Ramadan"
- "Kandili" alone (after a name) → "natten" or omit

Return ONLY a valid JSON array with the same structure as the input.
Keep the "date" field unchanged.
"""


def load_env():
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def call_api(batch: list[dict], api_key: str, model: str) -> list[dict]:
    user_msg = (
        "Fix the Turkish remnants in this Norwegian JSON array. "
        "Return ONLY the corrected JSON array.\n\n"
        + json.dumps(batch, ensure_ascii=False)
    )
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": user_msg},
            ],
            "temperature": 0.15,
            "max_tokens": 8192,
        },
        timeout=120,
    )
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        parts = content.split("```", 2)
        content = parts[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.rsplit("```", 1)[0]

    return json.loads(content.strip())


def is_flagged(entry: dict) -> bool:
    return any(
        TURKISH_RE.search(str(v))
        for v in entry.values()
        if v
    )


def main():
    load_env()
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    model   = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY not set in .env")

    no_data: dict = json.loads(NO_FILE.read_text(encoding="utf-8"))

    # Load set of already-fixed dates
    fixed_set: set = set()
    if DONE_FILE.exists():
        fixed_set = set(json.loads(DONE_FILE.read_text(encoding="utf-8")))
        print(f"Already fixed: {len(fixed_set)} dates")

    # Find all flagged dates not yet fixed
    pending = [
        {"date": d, **v}
        for d, v in no_data.items()
        if d not in fixed_set and is_flagged(v)
    ]
    print(f"Flagged and pending: {len(pending)} entries\n")

    if not pending:
        print("Nothing to fix.")
        return

    total = len(pending)
    done  = 0

    for i in range(0, total, BATCH):
        batch = pending[i : i + BATCH]
        dates_label = f"{batch[0]['date']} … {batch[-1]['date']}"
        print(f"[{i+1:>3}/{total}] {dates_label} ...", end="", flush=True)

        try:
            result = call_api(batch, api_key, model)

            for item in result:
                d = item.get("date", "")
                if not d:
                    continue
                no_data[d] = {
                    k: item.get(k, no_data.get(d, {}).get(k, ""))
                    for k in ["olay", "ayet_hadis", "konu", "metin", "dua"]
                }
                fixed_set.add(d)
                done += 1

            print(f" ✓ ({done} fixed)")

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            wait   = 60 if status == 429 else 15
            print(f" HTTP {status} – retrying 1-by-1 after {wait}s")
            time.sleep(wait)
            for item in batch:
                d = item["date"]
                if d in fixed_set:
                    continue
                print(f"    {d} ...", end="", flush=True)
                for attempt in range(3):
                    try:
                        res = call_api([item], api_key, model)
                        if res:
                            r = res[0]
                            no_data[d] = {
                                k: r.get(k, no_data.get(d, {}).get(k, ""))
                                for k in ["olay", "ayet_hadis", "konu", "metin", "dua"]
                            }
                            fixed_set.add(d)
                            done += 1
                            print(" ✓")
                            break
                    except Exception as e2:
                        print(f" ✗({e2.__class__.__name__})", end="", flush=True)
                        time.sleep(10)
                else:
                    print(" SKIPPED")

        except Exception as exc:
            print(f" parse error ({exc.__class__.__name__}) – retrying 1-by-1")
            for item in batch:
                d = item["date"]
                if d in fixed_set:
                    continue
                print(f"    {d} ...", end="", flush=True)
                for attempt in range(3):
                    try:
                        res = call_api([item], api_key, model)
                        if res:
                            r = res[0]
                            no_data[d] = {
                                k: r.get(k, no_data.get(d, {}).get(k, ""))
                                for k in ["olay", "ayet_hadis", "konu", "metin", "dua"]
                            }
                            fixed_set.add(d)
                            done += 1
                            print(" ✓")
                            break
                    except Exception as e2:
                        print(f" ✗({e2.__class__.__name__})", end="", flush=True)
                        time.sleep(5)
                else:
                    print(" SKIPPED")

        # Save progress after every batch
        NO_FILE.write_text(
            json.dumps(no_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        DONE_FILE.write_text(
            json.dumps(sorted(fixed_set), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        time.sleep(3.0)

    print(f"\nDone. {done} entries cleaned → {NO_FILE}")


if __name__ == "__main__":
    main()
