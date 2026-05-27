#!/usr/bin/env python3
"""
08_fetch_hadith_reminders.py
-----------------------------
Replaces all 365 back-page texts with authentic hadiths from four collections:
  • Sahih al-Bukhari
  • Sahih Muslim
  • Jami' at-Tirmidhi
  • Sunan Abu Dawud

For each calendar day the script:
  1. Fetches a relevant hadith from hadithapi.com  (Phase 1 — no AI, fast)
  2. Translates it to Norwegian using Gemini       (Phase 2 — AI, ~2 min/entry)
  3. Adds a short explanation for the Muslim prison inmate
  4. Includes source info: hadith number, book, chapter, status
  5. Keeps the original DUA section from reminders_no.json untouched

Reads:
  data/reminders_no.json         (DUA fields only)
  data/prayer_times_2027.json    (date list)
Writes:
  data/hadith_pool.json          (resume-safe — skip if exists)
  data/reminders_hadith.json     (resume-safe — skips done dates)

Model: google/gemini-3.1-pro-preview (via OpenRouter) — hardcoded as requested.

After this script completes:
  copy data\\reminders_hadith.json data\\reminders_no.json
  python 04_generate_html.py
"""

import json
import os
import random
import re
import time
import urllib.request
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

# ── API config ─────────────────────────────────────────────────────────────────
HADITH_API_KEY = "$2y$10$46HdpIMI6ThXKrnvqsEJk716GAQqEtNHSizkQVTs29GiabzQ6qsm"
HADITH_BASE    = "https://hadithapi.com/api"

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
MODEL          = "google/gemini-2.5-flash"   # hardcoded as requested
OR_URL         = "https://openrouter.ai/api/v1/chat/completions"

BOOK_SLUGS = ["sahih-bukhari", "sahih-muslim", "al-tirmidhi", "abu-dawood"]
BOOK_NAMES = {
    "sahih-bukhari": "Sahih al-Bukhari",
    "sahih-muslim":  "Sahih Muslim",
    "al-tirmidhi":   "Jami' at-Tirmidhi",
    "abu-dawood":    "Sunan Abu Dawud",
}

# ── File paths ──────────────────────────────────────────────────────────────────
POOL_FILE = HERE / "data" / "hadith_pool.json"
OUT_FILE  = HERE / "data" / "reminders_hadith.json"
REM_ORIG  = HERE / "data" / "reminders_no.json"
PRAYER_F  = HERE / "data" / "prayer_times_2027.json"

# ── Relevant chapter keywords (English) ────────────────────────────────────────
# Chapters covering faith, ethics, hope, repentance, patience — relevant for
# a Muslim in prison seeking spiritual guidance.
RELEVANT_KEYWORDS = {
    "belief", "faith", "iman", "prayer", "salat", "fasting", "heart",
    "tender", "manners", "adab", "repentance", "tawbah", "invocation",
    "supplication", "remembrance", "patience", "forgiveness", "mercy",
    "knowledge", "righteous", "piety", "virtue", "good", "deed", "sin",
    "intention", "night", "qur'an", "quran", "death", "hereafter",
    "paradise", "character", "truthful", "honest", "riqaq", "zuhd",
    "wisdom", "softening", "asceticism", "fear", "hope", "charity",
    "generosity", "kindness", "brother", "community", "creation",
    "tawheed", "oneness", "prophet", "sunnah", "dhikr", "dream",
    "peacemaking", "wishes", "divine will", "qadar",
}


# ── Phase 1 helpers: fetch hadith pool ─────────────────────────────────────────

def hadith_get(url: str) -> dict:
    """HTTP GET → parsed JSON. Retries 3x on failure."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read())
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
            else:
                raise RuntimeError(f"GET failed after 3 attempts: {url[:80]} — {e}") from e


def fetch_chapters(slug: str) -> list[dict]:
    url = f"{HADITH_BASE}/{slug}/chapters?apiKey={HADITH_API_KEY}"
    return hadith_get(url).get("chapters", [])


def chapter_is_relevant(chapter_english: str) -> bool:
    name = chapter_english.lower()
    return any(kw in name for kw in RELEVANT_KEYWORDS)


def fetch_hadiths_from_chapter(slug: str, chapter_id: str) -> list[dict]:
    """Fetch up to 4 pages (×50) of hadiths from one chapter."""
    hadiths: list[dict] = []
    for page in range(1, 5):
        url = (
            f"{HADITH_BASE}/hadiths"
            f"?apiKey={HADITH_API_KEY}"
            f"&book={slug}&chapter={chapter_id}&paginate=50&page={page}"
        )
        try:
            data = hadith_get(url)
        except Exception as e:
            print(f"      ✗ page {page}: {e}")
            break
        page_items = data.get("hadiths", {}).get("data", [])
        if not page_items:
            break
        hadiths.extend(page_items)
        last_page = data.get("hadiths", {}).get("last_page", 1)
        if page >= last_page:
            break
        time.sleep(0.25)
    return hadiths


def build_pool() -> list[dict]:
    """Phase 1: Build a pool of filtered hadiths from relevant chapters."""
    if POOL_FILE.exists():
        pool = json.loads(POOL_FILE.read_text(encoding="utf-8"))
        print(f"  Loaded existing pool: {len(pool)} hadiths from {POOL_FILE.name}")
        return pool

    print("Phase 1: Building hadith pool from API ...")
    pool: list[dict] = []

    for slug in BOOK_SLUGS:
        print(f"  ── {BOOK_NAMES[slug]} ({slug}) ──")
        try:
            chapters = fetch_chapters(slug)
        except Exception as e:
            print(f"    ✗ Could not fetch chapters: {e}")
            continue

        relevant = [c for c in chapters if chapter_is_relevant(c.get("chapterEnglish", ""))]
        print(f"    {len(relevant)}/{len(chapters)} chapters selected")

        for ch in relevant:
            ch_id   = ch["chapterNumber"]
            ch_name = ch.get("chapterEnglish", "")
            print(f"    ch {ch_id:>3}: {ch_name[:65]}", end="  ", flush=True)

            try:
                raw_hadiths = fetch_hadiths_from_chapter(slug, ch_id)
            except Exception as e:
                print(f"✗ {e}")
                continue

            added = 0
            for h in raw_hadiths:
                text     = (h.get("hadithEnglish") or "").strip()
                narrator = (h.get("englishNarrator") or "").strip()
                status   = (h.get("status") or "").strip()
                h_num    = str(h.get("hadithNumber") or "").strip()

                # Quality filters
                if not text:
                    continue
                if len(text) < 40 or len(text) > 650:
                    continue
                # Skip hadiths about specific ritual details not meaningful in isolation
                if not h_num:
                    continue

                pool.append({
                    "hadithNumber": h_num,
                    "text":         text,
                    "narrator":     narrator,
                    "bookSlug":     slug,
                    "bookName":     BOOK_NAMES[slug],
                    "chapterId":    ch_id,
                    "chapterName":  ch_name,
                    "status":       status,
                })
                added += 1

            print(f"{added} hadiths")
            time.sleep(0.3)

    print(f"\n  ✓ Pool total: {len(pool)} hadiths")
    POOL_FILE.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Saved → {POOL_FILE}")
    return pool


# ── Phase 2 helpers: AI translate + explain ────────────────────────────────────

SYSTEM_PROMPT = """\
Du er en islamsk oversetter og rådgiver som lager daglige tekster for en kalender \
brukt av muslimske innsatte i norske fengsler.

Du mottar én hadith på engelsk og skal lage en norsk back-side kalenderside.

STRUKTUR I METIN (følg denne rekkefølgen nøyaktig):

1. FORTELLER — Første linje: «Fortalt av [navn]:» (ingen formattering)

2. HADITH-TEKST — Neste linje: hadithteksten oversatt til norsk, ALLTID omsluttet \
av doble asterisker for fet skrift: **«oversatt hadith-tekst her»**
Profetens navn følges alltid av ﷺ.

3. KILDE — Linjen rett etter hadith-teksten (ingen blank linje mellom): \
skriv kilden i kursiv med understrekmarkering, UTEN emoji:
_Kilde: Hadith nr. X · Boknavn · Kap. Y: Kapittelnavn · Status_

4. FORKLARING — Én blank linje, deretter 2–3 avsnitt skilt av dobbelt linjeskift. \
Tal direkte til den innsatte: «du», «deg», «din». Knytt hadithen til \
fengselshverdagen – håp i mørket, tålmodighet, Allahs tilgivelse og nåde, \
en ny fremtid, indre styrke, sabr, tawbah.

5. TITTEL (konu) — 3–6 norske ord som oppsummerer temaet. Ingen arabiske ord.

6. LENGDE — Metin totalt 220–380 ord.

7. IKKE generer noe dua — det håndteres separat.

EKSEMPEL på riktig metin-struktur:
Fortalt av Abu Hurairah:
**«Profeten ﷺ sa: Den sterkeste er den som kontrollerer seg selv i sinne.»**
_Kilde: Hadith nr. 6114 · Sahih al-Bukhari · Kap. 79: Gode manerer · Sahih_

Forklaring avsnitt 1...

Forklaring avsnitt 2...

Returner KUN gyldig JSON uten markdown:
{"konu": "...", "metin": "..."}
"""


def ai_process(hadith: dict) -> dict:
    """Send one hadith to Gemini → return {konu, metin}."""
    # Strip Arabic from narrator for cleaner prompt
    narrator_clean = re.sub(r"[\u0600-\u06ff\s]+$", "", hadith["narrator"]).strip().rstrip(":")

    source_str = (
        f"Hadith nr. {hadith['hadithNumber']} · "
        f"{hadith['bookName']} · "
        f"Kap. {hadith['chapterId']}: {hadith['chapterName']} · "
        f"{hadith['status'] or 'ukjent'}"
    )

    user_prompt = (
        "Lag en norsk kalenderside av denne hadithen for muslimske fengselsinnsatte.\n\n"
        f"Forteller: {narrator_clean}\n"
        f"Hadith (engelsk):\n{hadith['text']}\n\n"
        f"Bruk denne kildelinjen eksakt rett etter hadith-teksten (i kursiv, ingen emoji):\n"
        f"_Kilde: {source_str}_\n\n"
        'Returner BARE JSON: {"konu": "...", "metin": "..."}'
    )

    headers = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":      MODEL,
        "max_tokens": 4000,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
    }

    resp = requests.post(OR_URL, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    raw = (resp.json()["choices"][0]["message"]["content"] or "").strip()

    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found in response:\n{raw[:300]}")

    return json.loads(raw[start:end])


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    if not OPENROUTER_KEY:
        raise SystemExit("❌ OPENROUTER_API_KEY not set in .env")

    # ── Phase 1 ──────────────────────────────────────────────────────────────
    pool = build_pool()
    if len(pool) < 365:
        raise SystemExit(
            f"❌ Pool too small ({len(pool)} hadiths). "
            "Delete data/hadith_pool.json and re-run to rebuild."
        )

    # ── Setup ─────────────────────────────────────────────────────────────────
    dates      = sorted(json.loads(PRAYER_F.read_text(encoding="utf-8")).keys())
    orig_rems  = json.loads(REM_ORIG.read_text(encoding="utf-8")) if REM_ORIG.exists() else {}

    # Stable deterministic assignment: shuffle once with fixed seed
    rng = random.Random(2027)
    pool_shuffled = pool.copy()
    rng.shuffle(pool_shuffled)
    # De-duplicate by hadith text within the 365 window where possible
    seen_texts: set[str] = set()
    ordered_pool: list[dict] = []
    leftover: list[dict] = []
    for h in pool_shuffled:
        if h["text"] not in seen_texts:
            ordered_pool.append(h)
            seen_texts.add(h["text"])
        else:
            leftover.append(h)
    ordered_pool.extend(leftover)   # fill overflow with duplicates if pool < 365 unique

    date_to_hadith = {d: ordered_pool[i % len(ordered_pool)] for i, d in enumerate(dates)}

    # ── Resume ────────────────────────────────────────────────────────────────
    out_data: dict = {}
    if OUT_FILE.exists():
        out_data = json.loads(OUT_FILE.read_text(encoding="utf-8"))
        already  = sum(1 for v in out_data.values() if v.get("metin", "").strip())
        print(f"Resuming — {already} already done.\n")

    total   = len(dates)
    done    = 0
    skipped = 0

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    print("Phase 2: AI translation + explanation ...")
    for i, date_str in enumerate(dates, 1):
        # Skip if already processed
        if date_str in out_data and out_data[date_str].get("metin", "").strip():
            skipped += 1
            if skipped % 50 == 1:
                print(f"  [{i:3d}/{total}] {date_str} — skip")
            continue

        hadith = date_to_hadith[date_str]
        label  = f"{hadith['bookName'][:22]} #{hadith['hadithNumber']}"
        print(f"[{i:3d}/{total}] {date_str}  {label}", end="", flush=True)

        result = None
        for attempt in range(3):
            try:
                result = ai_process(hadith)
                break
            except Exception as e:
                print(f"  ⚠ attempt {attempt+1}: {e}", end="")
                if attempt < 2:
                    time.sleep(6)

        if result is None:
            print("  ✗ FAILED — skipping date")
            continue

        wc = len(result.get("metin", "").split())
        print(f"  ✓  ({wc} ord)")

        # Preserve original olay + ayet_hadis + dua fields
        orig = orig_rems.get(date_str, {})
        out_data[date_str] = {
            "olay":         orig.get("olay", ""),
            "ayet_hadis":   orig.get("ayet_hadis", ""),
            "konu":         result.get("konu", "Hadith"),
            "metin":        result.get("metin", ""),
            "dua":          orig.get("dua", ""),
            "dua_translit": orig.get("dua_translit", ""),
        }

        OUT_FILE.write_text(
            json.dumps(out_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        done += 1
        time.sleep(0.3)

    # ── Summary ───────────────────────────────────────────────────────────────
    total_saved = sum(1 for v in out_data.values() if v.get("metin", "").strip())
    print(f"\n✓ Done.  {done} new,  {skipped} skipped,  {total_saved}/365 total saved.")
    print(f"  Output → {OUT_FILE}\n")
    print("Neste steg:")
    print(f"  copy \"{OUT_FILE}\" \"{REM_ORIG}\"")
    print(f"  python \"{HERE / '04_generate_html.py'}\"")


if __name__ == "__main__":
    main()
