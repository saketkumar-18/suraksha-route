"""Build web/cities-data.js from cities_master_53.csv + Nominatim geocoding.

Output: window.CITIES = [{name, state, center, population_lakhs, cases_latest,
street_crime_rate, ...}...] — the app's city dropdown + crime context.
"""
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
WEB = ROOT / "web"

df = pd.read_csv(PROC / "cities_master_53.csv")

GEO = RAW / "geocode_cache_v2.json"
cache = json.loads(GEO.read_text()) if GEO.exists() else {}
UA = {"User-Agent": "suraksha-route/1.0 (research; contact: k.saket@op.iitg.ac.in)"}

STATE_FIX = {
    "Delhi City": "Delhi", "Chandigarh City": "Chandigarh",
    "Vishakhapatnam": "Andhra Pradesh", "Nasik": "Maharashtra",
    "Tiruchirapalli": "Tamil Nadu", "Durg-Bhilainagar": "Chhattisgarh",
    "Vasai Virar": "Maharashtra", "Kannur": "Kerala",
}

SEARCH = {
    "Delhi City": "New Delhi", "Chandigarh City": "Chandigarh",
    "Nasik": "Nashik", "Tiruchirapalli": "Tiruchirappalli",
    "Vishakhapatnam": "Visakhapatnam", "Durg-Bhilainagar": "Bhilai",
}


def geocode(city):
    if city in cache:
        return cache[city]
    q = SEARCH.get(city, city) + ", India"
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": 1},
            headers=UA, timeout=30,
        )
        r.raise_for_status()
        js = r.json()
        val = (float(js[0]["lat"]), float(js[0]["lon"]), js[0].get("display_name", "")) if js else None
    except Exception as e:
        print("geo fail", city, e)
        val = None
    cache[city] = val
    GEO.write_text(json.dumps(cache, indent=1))
    time.sleep(1.1)
    return val


records = []
missing = []
for _, r in df.iterrows():
    g = geocode(r["city"])
    if not g:
        missing.append(r["city"])
        continue
    records.append({
        "name": r["city"],
        "state": STATE_FIX.get(r["city"], r.get("state", "")),
        "center": [g[0], g[1]],
        "radius_km": 7 if r["population_lakhs"] > 15 else 5,
        "cases_2023": float(r["cases_2023"]) if pd.notna(r["cases_2023"]) else None,
        "population_lakhs": float(r["population_lakhs"]),
        "rape": float(r["rape"]) if pd.notna(r["rape"]) else 0,
        "kidnap_abduct": float(r["kidnap_abduct"]) if pd.notna(r["kidnap_abduct"]) else 0,
        "assault_354": float(r["assault_354"]) if pd.notna(r["assault_354"]) else 0,
        "insult_509": float(r["insult_509"]) if pd.notna(r["insult_509"]) else 0,
        "street_crime": float(r["street_crime"]),
        "total_crimes": float(r["total_crimes"]),
        "street_crime_rate": round(float(r["street_crime_rate"]), 2),
        "chargesheet_rate": float(r["chargesheet_rate"]) if pd.notna(r["chargesheet_rate"]) else None,
    })

# sort: biggest / most crime-relevant first for the dropdown
records.sort(key=lambda x: -x["population_lakhs"])
js = "window.CITIES = " + json.dumps(records, ensure_ascii=False, indent=1) + ";\n"
(WEB / "cities-data.js").write_text(js)
print(f"cities: {len(records)} written; missing geocode: {missing}")
