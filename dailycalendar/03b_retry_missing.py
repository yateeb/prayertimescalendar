#!/usr/bin/env python3
"""Retry the 3 permanently-failing translation days with a longer timeout."""
import json
import os
import time
from pathlib import Path
import requests

HERE    = Path(__file__).resolve().parent
TR_FILE = HERE / "data" / "reminders_tr.json"
NO_FILE = HERE / "data" / "reminders_no.json"
ENV     = HERE / ".env"

MISSING = ["2027-06-14", "2027-09-11", "2027-09-12"]

# Load env
for line in ENV.read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL   = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")

tr_data = json.loads(TR_FILE.read_text(encoding="utf-8"))
no_data = json.loads(NO_FILE.read_text(encoding="utf-8"))

SYSTEM = (
    "Translate Turkish to Norwegian Bokmål. "
    "Return only a valid JSON array with the same structure. "
    "Keep Islamic terms, Arabic names, and verse references unchanged."
)

for d in MISSING:
    if d in no_data:
        print(f"{d}: already done, skipping")
        continue

    item = {"date": d, **tr_data[d]}
    print(f"{d} ...", end="", flush=True)

    for attempt in range(5):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {
                            "role": "user",
                            "content": (
                                "Translate this JSON array to Norwegian Bokmål. "
                                "Return ONLY the JSON array.\n\n"
                                + json.dumps([item], ensure_ascii=False)
                            ),
                        },
                    ],
                    "temperature": 0.2,
                    "max_tokens": 8192,
                },
                timeout=180,
            )
            resp.raise_for_status()

            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                parts = content.split("```", 2)
                content = parts[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.rsplit("```", 1)[0]

            result = json.loads(content.strip())[0]
            no_data[d] = {k: result.get(k, "") for k in ["olay", "ayet_hadis", "konu", "metin", "dua"]}
            print(" OK")
            break

        except Exception as exc:
            print(f" attempt {attempt + 1} failed ({exc.__class__.__name__})", end="", flush=True)
            time.sleep(20)
    else:
        print(" GAVE UP — will use Turkish fallback")

NO_FILE.write_text(json.dumps(no_data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nSaved. Total: {len(no_data)}/365")
