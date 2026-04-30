#!/usr/bin/env python3
"""
02_prayer_times.py
------------------
Fetches prayer times for all 28 Norwegian prison locations for every
day of 2027, using the AlAdhan monthly calendar API.

Method  : 3 – Muslim World League (MWL)
High-lat: MidNight (for Tromsø/Badsø at ~70 °N)

Also computes:
  • Norwegian weekday / month names
  • Hijri date (from AlAdhan response)
  • Rumi (Ottoman/Julian) date

Output  : dailycalendar/data/prayer_times_2027.json
Resumable: already-fetched cities/months are skipped on re-run.
"""

import csv
import datetime
import json
import time
import urllib.request
from pathlib import Path

HERE   = Path(__file__).resolve().parent
CSV    = HERE / "Fengsler i Norge.xlsx - Sheet3.csv"
OUTPUT = HERE / "data" / "prayer_times_2027.json"

METHOD   = 3          # Muslim World League
HIGH_LAT = "MidNight"
YEAR     = 2027

WEEKDAY_NO = {
    "Monday": "Mandag", "Tuesday": "Tirsdag", "Wednesday": "Onsdag",
    "Thursday": "Torsdag", "Friday": "Fredag",
    "Saturday": "Lørdag", "Sunday": "Søndag",
}
MONTH_NO = {
    "January": "Januar",   "February": "Februar", "March": "Mars",
    "April": "April",      "May": "Mai",           "June": "Juni",
    "July": "Juli",        "August": "August",     "September": "September",
    "October": "Oktober",  "November": "November", "December": "Desember",
}
HIJRI_MND = {
    "Muharram": "Muharram",         "Safar": "Safar",
    "Rabi al-awwal": "Rabi al-Awwal", "Rabi al-thani": "Rabi al-Thani",
    "Jumada al-ula": "Jumada al-Ula", "Jumada al-akhirah": "Jumada al-Akhirah",
    "Rajab": "Rajab",               "Shaban": "Sha'ban",
    "Ramadan": "Ramadan",           "Shawwal": "Shawwal",
    "Dhu al-Qidah": "Dhul Qi'dah", "Dhu al-Hijjah": "Dhul Hijjah",
    # Variants with diacritical marks returned by AlAdhan
    "Ramaḍān": "Ramadan",          "Sha\u02BFbān": "Sha'ban",
    "Sha'bān": "Sha'ban",          "Shawwāl": "Shawwal",
    "Muḥarram": "Muharram",        "Ṣafar": "Safar",
    "Rabīʿ al-awwal": "Rabi al-Awwal",  "Rabīʿ al-thānī": "Rabi al-Thani",
    "Rabīʿ al-Awwal": "Rabi al-Awwal",  "Rabīʿ al-Thānī": "Rabi al-Thani",
    "Jumādá al-ūlá": "Jumada al-Ula",   "Jumādá al-ākhirah": "Jumada al-Akhirah",
    "Dhū al-Qaʿdah": "Dhul Qi'dah",    "Dhū al-Ḥijjah": "Dhul Hijjah",
}


def hijri_month(name: str) -> str:
    return HIJRI_MND.get(name, name)


def gregorian_to_rumi(year: int, month: int, day: int) -> dict:
    """
    Rumi (Maliye/Ottoman) calendar = Julian calendar with year − 584.
    The Julian calendar is 13 days behind Gregorian in the 21st century.
    """
    d = datetime.date(year, month, day)
    julian = d - datetime.timedelta(days=13)
    return {
        "day":        julian.day,
        "month":      julian.month,
        "month_name": MONTH_NO.get(julian.strftime("%B"), julian.strftime("%B")),
        "year":       julian.year - 584,
    }


def read_cities() -> list[dict]:
    cities = []
    with open(str(CSV), newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)  # skip header
        for row in reader:
            if len(row) < 2:
                continue
            name = row[0].strip()
            coords = row[1].strip()
            lat_str, lng_str = coords.split(",", 1)
            cities.append({
                "navn": name,
                "lat":  float(lat_str.strip()),
                "lng":  float(lng_str.strip()),
            })
    return cities


def fetch_month(lat: float, lng: float, year: int, month: int) -> list:
    url = (
        f"https://api.aladhan.com/v1/calendar/{year}/{month}"
        f"?latitude={lat}&longitude={lng}"
        f"&method={METHOD}&latitudeAdjustmentMethod={HIGH_LAT}"
    )
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["data"]


def strip_tz(t: str) -> str:
    """'06:32 (+01)' → '06:32'"""
    return t.split(" ")[0]


def main():
    OUTPUT.parent.mkdir(exist_ok=True)

    # Resume support: load existing data
    result: dict = {}
    if OUTPUT.exists():
        result = json.loads(OUTPUT.read_text(encoding="utf-8"))
        print(f"Loaded {len(result)} existing day entries (resuming)")

    cities = read_cities()
    print(f"Processing {len(cities)} cities × 12 months = {len(cities) * 12} API calls\n")

    for month_num in range(1, 13):
        print(f"─── Month {month_num:02d} ───────────────────────────────")
        for city in cities:
            name = city["navn"]

            # Check if this city-month is already done
            # We check the first day of the month
            sample_date = f"{YEAR}-{month_num:02d}-01"
            if (
                sample_date in result
                and name in result[sample_date].get("cities", {})
            ):
                print(f"  {name}: already done, skipping")
                continue

            print(f"  {name} ...", end="", flush=True)
            try:
                days_data = fetch_month(city["lat"], city["lng"], YEAR, month_num)
                for day_data in days_data:
                    greg   = day_data["date"]["gregorian"]
                    hijri  = day_data["date"]["hijri"]
                    day_no = int(greg["day"])
                    mth_en = greg["month"]["en"]
                    yr_str = greg["year"]
                    date_str = f"{yr_str}-{month_num:02d}-{day_no:02d}"

                    # Build meta entry if first city to fill this date
                    if date_str not in result:
                        d   = datetime.date(int(yr_str), month_num, day_no)
                        doy = d.timetuple().tm_yday
                        result[date_str] = {
                            "weekday":    WEEKDAY_NO.get(greg["weekday"]["en"], greg["weekday"]["en"]),
                            "day":        day_no,
                            "month_no":   month_num,
                            "month":      MONTH_NO.get(mth_en, mth_en),
                            "year":       int(yr_str),
                            "day_of_year": doy,
                            "days_left":  365 - doy,
                            "hijri": {
                                "day":   hijri["day"],
                                "month": hijri_month(hijri["month"]["en"]),
                                "year":  hijri["year"],
                            },
                            "rumi": gregorian_to_rumi(int(yr_str), month_num, day_no),
                            "cities": {},
                        }

                    t = day_data["timings"]
                    result[date_str]["cities"][name] = {
                        "Fajr":    strip_tz(t["Fajr"]),
                        "Sunrise": strip_tz(t["Sunrise"]),
                        "Dhuhr":   strip_tz(t["Dhuhr"]),
                        "Asr":     strip_tz(t["Asr"]),
                        "Maghrib": strip_tz(t["Maghrib"]),
                        "Isha":    strip_tz(t["Isha"]),
                    }

                print(" ✓")
                time.sleep(0.4)  # polite rate limiting

            except Exception as exc:
                print(f" ERROR: {exc}")
                time.sleep(3)

        # Save after every month
        OUTPUT.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  ↳ Saved {len(result)} days so far\n")

    print(f"Done. {len(result)} days → {OUTPUT}")


if __name__ == "__main__":
    main()
