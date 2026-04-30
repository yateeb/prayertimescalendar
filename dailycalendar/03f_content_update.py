#!/usr/bin/env python3
"""
03f_content_update.py
---------------------
Two-pass content improvement for reminders_no.json:

  PASS 1 – Replace non-relevant entries
    Topics like BARNETEKST (children's texts), AKTIVITET (activity placeholders),
    organisation campaigns, tourist-city profiles, and Turkey-specific political
    events are replaced with Islamic content relevant to prison inmates: patience,
    repentance, dhikr, stories of prophets/companions who faced hardship, etc.

  PASS 2 – Add Arabic transliteration to every dua
    Each entry's 'dua' field gets two new sibling fields:
      dua_arabic       – original Arabic supplication in Arabic script
      dua_translit     – Latin-script transliteration for memorisation

Both passes are fully resumable via separate progress files.
"""

import json
import os
import re
import time
from pathlib import Path

import requests

HERE     = Path(__file__).resolve().parent
NO_FILE  = HERE / "data" / "reminders_no.json"
PROG1    = HERE / "data" / "pass1_replaced.json"   # set of replaced dates
PROG2    = HERE / "data" / "pass2_translit.json"   # set of transliterated dates

# ── Load env ──────────────────────────────────────────────────────────────────
for line in (HERE / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL   = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
}

# ── Entries irrelevant for prison inmates ────────────────────────────────────
# Children's texts (BARNETEKST)
BARNETEKST = [
    "2027-01-05","2027-02-02","2027-04-06","2027-04-13","2027-05-04",
    "2027-06-01","2027-07-06","2027-08-03","2027-09-07","2027-10-05",
    "2027-11-02","2027-12-07","2027-12-28",
]
# Placeholder activities / events
AKTIVITET = [
    "2027-01-20","2027-02-18","2027-05-18","2027-07-20","2027-08-17",
    "2027-09-21","2027-10-20","2027-11-16","2027-11-30","2027-12-14",
]
# Organisation campaigns and competitions (not actionable in prison)
ORGANIZATION = [
    "2027-02-25",  # Zekat kampanje
    "2027-02-26",  # Innsamling av Zekat
    "2027-07-21",  # FAIR International Forening
    "2027-10-13",  # IGMG Europeiske Koranresitasjonskonkurranser
    "2027-10-16",  # Kvinneorganisasjonens Koran-konkurranse
    "2027-10-17",  # Foreldreløse prosjekter
]
# Tourist city / mosque profiles (irrelevant in prison context)
CITIES = [
    "2027-01-04",  # Istanbul Sultan Ahmet moske
    "2027-01-16",  # Gamle byer: Bukhara
    "2027-04-22",  # Gamle Byer: Damaskus
    "2027-05-08",  # Gamle byer: Bagdad
    "2027-05-22",  # Gamle byer: Aleppo
    "2027-05-28",  # Gamle byer: Basra
    "2027-06-19",  # Gamle Byer: Sana'a
    "2027-07-17",  # Gamle byer: Kairo
    "2027-07-29",  # Gamle byer: Alexandria
    "2027-08-14",  # Gamle byer: Sarajevo
    "2027-08-28",  # Gamle byer: Üsküp
    "2027-09-11",  # Gamle Byer: Granada
]
# Turkey-specific political events (no resonance in Norwegian prisons)
TURKISH_POLITICAL = [
    "2027-02-27",  # Necmettin Erbakan
    "2027-02-28",  # 28. februar-kuppet
    "2027-07-15",  # 15. juli kuppforsøket
]
# Vacation / family invitations (painful reminder or irrelevant)
VACATION = [
    "2027-06-17",  # Å ha en god intensjon for sommerferien
]

REPLACE_DATES = sorted(set(
    BARNETEKST + AKTIVITET + ORGANIZATION + CITIES + TURKISH_POLITICAL + VACATION
))

# ── Replacement themes ────────────────────────────────────────────────────────
# A pool of themes the AI should draw from when writing replacement content.
# These are especially relevant for inmates: patience, repentance, hope, dhikr.
REPLACEMENT_THEMES = [
    "Sabr (tålmodighet) – dets dyder og belønning i Islam",
    "Tawbah (anger og tilgivelse) – Allahs dør er alltid åpen",
    "Hz. Yûsuf (a.s.) i fengselet – tro i isolasjon",
    "Dhikr (Allahs ihukommelse) som hjertets trygghet",
    "Tawakkul (tillit til Allah) i vanskelige tider",
    "Istighfar – å søke tilgivelse og dens virkning",
    "Hz. Yûnus (a.s.) i havdypets mørke – bønn i fortvilelse",
    "Hz. Ayyûb (a.s.) – tålmodighet i lidelse",
    "Allahs barmhjertighet (Rahma) overgår Hans vrede",
    "Å finne ro i salat og tilbedelse",
    "Koranens helbredende kraft for hjertet",
    "Muraqaba – selvrefleksjon og åndelig bevissthet",
    "Frihet gjennom Iman – det indre fengselet",
    "Å styrke sin karakter i prøvelsenes skole",
    "Håp og gjenoppbygging – Islam om en ny begynnelse",
    "Nettid og natten – ekstra tilbedelse og dens velsignelse",
    "Å kontrollere sinnet (Hilm) og dens dyder",
    "Oppriktig dua – hjertet som kommuniserer med Allah",
    "Hz. Ibrahim (a.s.) i ilden – Allahs beskyttelse",
    "Riyadu's-Salihin – daglige ord og handlinger fra Sunnah",
    "Grenser for tilgivelse mellom mennesker – å tilgi og bli tilgitt",
    "Shukr (takknemlighet) som vei til tilfredshet",
    "Allahs navn Al-Latîf – den subtile og kjærlige",
    "Å huske døden og forberede seg på det hinsidige",
    "Å lese Koranen daglig – dets åndelige virkning",
]


def call_api(messages: list, max_tokens: int = 4096) -> str | None:
    """Single API call, returns content string or None on failure."""
    for attempt in range(4):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=HEADERS,
                json={
                    "model":       MODEL,
                    "messages":    messages,
                    "temperature": 0.35,
                    "max_tokens":  max_tokens,
                },
                timeout=90,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            wait   = 90 if status == 429 else 20
            print(f"   HTTP {status} – waiting {wait}s …", flush=True)
            time.sleep(wait)
        except Exception as exc:
            print(f"   Error: {exc.__class__.__name__} – waiting 15s …", flush=True)
            time.sleep(15)
    return None


def parse_json_response(raw: str) -> dict | list | None:
    """Strip markdown fences and parse JSON."""
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.M)
    raw = re.sub(r"\s*```$",          "", raw, flags=re.M)
    raw = raw.strip()
    # Truncate to last complete '}' if truncated
    if raw and raw[-1] not in "]}":
        idx = max(raw.rfind("}"), raw.rfind("]"))
        if idx != -1:
            raw = raw[: idx + 1]
    try:
        return json.loads(raw)
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────────────
# PASS 1 – Replace irrelevant entries
# ────────────────────────────────────────────────────────────────────────────

PASS1_SYSTEM = (
    "Du er en islamsk kalenderredaktør for en norsk fengselsimam. "
    "Skriv islamsk innhold på norsk bokmål som er relevant for muslimske innsatte "
    "(isolasjon, tålmodighet, anger, håp, tillit til Allah, karakter). "
    "Unngå innhold om familie, ferie, politikk, turiststeder eller organisasjoner. "
    "Svar KUN med gyldig JSON-objekt med feltene: "
    "olay (historisk hendelse/islamsk fakta, 1 setning), "
    "ayet_hadis (Koranvers eller hadith + kilde, 1–2 setninger), "
    "konu (emnetittel, maks 6 ord), "
    "metin (refleksjonstekst, 6–10 setninger), "
    "dua (bønn/suplikasjon på norsk, 1–3 setninger med kildeangivelse)."
)


def pass1_replace(no_data: dict, done: set, theme_iter) -> int:
    replaced = 0
    for date_str in REPLACE_DATES:
        if date_str in done:
            continue
        theme = next(theme_iter)
        print(f"  [{date_str}] Theme: {theme[:50]} …", end="", flush=True)
        raw = call_api(
            [
                {"role": "system",  "content": PASS1_SYSTEM},
                {"role": "user",    "content":
                    f"Dato: {date_str}\n"
                    f"Tema: {theme}\n\n"
                    "Skriv innhold for denne dagen. Svar KUN med JSON."},
            ],
            max_tokens=2048,
        )
        if raw is None:
            print(" SKIPPED (API failure)")
            continue

        obj = parse_json_response(raw)
        if not isinstance(obj, dict) or "konu" not in obj:
            print(f" BAD JSON: {raw[:80]}")
            continue

        no_data[date_str] = {k: obj.get(k, "") for k in ["olay","ayet_hadis","konu","metin","dua"]}
        done.add(date_str)
        PROG1.write_text(json.dumps(sorted(done), ensure_ascii=False, indent=2), encoding="utf-8")
        NO_FILE.write_text(json.dumps(no_data, ensure_ascii=False, indent=2), encoding="utf-8")
        replaced += 1
        print(f" ✓ {obj.get('konu','')[:40]}")
        time.sleep(3.5)

    return replaced


# ────────────────────────────────────────────────────────────────────────────
# PASS 2 – Add Arabic transliteration to dua fields
# ────────────────────────────────────────────────────────────────────────────

PASS2_SYSTEM = (
    "Du er en islamsk lærd. Gitt en norsk oversettelse av en islamsk bønn/dua, "
    "identifiser den originale arabiske bønnen og svar KUN med et JSON-objekt med:"
    "\n  arabic:     original arabisk tekst (arabisk skrift)"
    "\n  translit:   latinsk translitterasjon av den arabiske teksten (for memorering)"
    "\nHvis du ikke kan identifisere en spesifikk arabisk bønn, lag en passende "
    "generisk arabisk suplikasjon basert på innholdet i den norske teksten. "
    "Svar KUN med JSON – ingen forklaring."
)


def pass2_translit(no_data: dict, done: set) -> int:
    added = 0
    all_dates = sorted(no_data.keys())
    total = len(all_dates)
    for i, date_str in enumerate(all_dates, 1):
        if date_str in done:
            continue
        entry = no_data[date_str]
        dua = entry.get("dua", "").strip()
        if not dua:
            done.add(date_str)
            continue

        print(f"  [{i:3d}/{total}] {date_str} …", end="", flush=True)
        raw = call_api(
            [
                {"role": "system", "content": PASS2_SYSTEM},
                {"role": "user",   "content": f"Norsk dua:\n{dua}"},
            ],
            max_tokens=512,
        )
        if raw is None:
            print(" SKIPPED")
            continue

        obj = parse_json_response(raw)
        if not isinstance(obj, dict) or "translit" not in obj:
            print(f" BAD JSON: {raw[:60]}")
            continue

        entry["dua_arabic"]   = obj.get("arabic", "")
        entry["dua_translit"] = obj.get("translit", "")
        done.add(date_str)
        PROG2.write_text(json.dumps(sorted(done), ensure_ascii=False, indent=2), encoding="utf-8")
        NO_FILE.write_text(json.dumps(no_data, ensure_ascii=False, indent=2), encoding="utf-8")
        added += 1
        print(f" ✓  {obj.get('translit','')[:50]}")
        time.sleep(2.5)

    return added


# ────────────────────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────────────────────

def main():
    no_data: dict = json.loads(NO_FILE.read_text(encoding="utf-8"))

    # ── Pass 1 ────────────────────────────────────────────────────────────────
    done1: set = set()
    if PROG1.exists():
        done1 = set(json.loads(PROG1.read_text(encoding="utf-8")))
    remaining1 = [d for d in REPLACE_DATES if d not in done1]
    print(f"\n=== PASS 1: Replace irrelevant entries ===")
    print(f"Total to replace: {len(REPLACE_DATES)}  |  Already done: {len(done1)}  |  Remaining: {len(remaining1)}")

    if remaining1:
        import itertools
        theme_iter = itertools.cycle(REPLACEMENT_THEMES)
        # Advance theme iterator so resumed runs get different themes
        for _ in range(len(done1)):
            next(theme_iter)
        replaced = pass1_replace(no_data, done1, theme_iter)
        print(f"Pass 1 complete: {replaced} entries replaced.\n")
    else:
        print("Pass 1 already complete.\n")

    # ── Pass 2 ────────────────────────────────────────────────────────────────
    done2: set = set()
    if PROG2.exists():
        done2 = set(json.loads(PROG2.read_text(encoding="utf-8")))
    total_with_dua = sum(1 for e in no_data.values() if e.get("dua","").strip())
    remaining2 = [d for d,e in no_data.items()
                  if d not in done2 and e.get("dua","").strip()]
    print(f"=== PASS 2: Add Arabic transliteration to dua fields ===")
    print(f"Entries with dua: {total_with_dua}  |  Already done: {len(done2)}  |  Remaining: {len(remaining2)}")

    if remaining2:
        added = pass2_translit(no_data, done2)
        print(f"\nPass 2 complete: {added} dua fields updated.")
    else:
        print("Pass 2 already complete.")

    print(f"\nAll done. {NO_FILE}")


if __name__ == "__main__":
    main()
