"""Retry the failed Overpass cities (single mirror, fresh backoff)."""
import json
import math
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
sys_cache = RAW / "overpass_macro"

UA = {"User-Agent": "suraksha-route/1.0 (research)"}
MIRROR = "https://overpass.kumi.systems/api/interpreter"

import sys
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_osm_features import Q, bbox, features_for  # noqa: E402

cities = pd.read_csv(PROC / "cities_master_53.csv")
feats = pd.read_csv(PROC / "city_features_osm.csv")
have = set(feats["city"])
geo = json.loads((RAW / "geocode_cache_v2.json").read_text())
todo = [c for c in cities["city"] if c not in have]
print("retrying:", todo)

rows = feats.to_dict("records")
for city in todo:
    g = geo.get(city)
    if not g:
        print("no geo:", city)
        continue
    f = sys_cache / (city.replace(" ", "_") + ".json")
    if f.exists():
        continue  # cached from main run (means it failed then too; try fresh)
    ok = False
    for attempt in range(4):
        try:
            r = requests.post(MIRROR, data={"data": Q.format(bbox=bbox(g[0], g[1]))},
                              headers=UA, timeout=320)
            if r.status_code in (429, 504, 500, 502):
                print(f"  {city}: {r.status_code}, backoff {20*(attempt+1)}s")
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            d = r.json()
            if d.get("remark") or not d.get("elements"):
                print(f"  {city}: truncated/empty, retry")
                time.sleep(15)
                continue
            f.write_text(r.text)
            rec = features_for(city, d, g[0], g[1])
            mrow = cities[cities.city == city].iloc[0]
            rec["city"] = city
            rec["street_crime_rate"] = mrow["street_crime_rate"]
            rec["population_lakhs"] = mrow["population_lakhs"]
            rec["assault_share"] = mrow["assault_354"] / mrow["total_crimes"]
            rec["kidnap_share"] = mrow["kidnap_abduct"] / mrow["total_crimes"]
            rec["pop_density_lakh_per_km2"] = mrow["population_lakhs"] / (math.pi * 36)
            rows.append(rec)
            print(f"  OK {city}: roads={rec['road_km_per_km2']:.1f}")
            ok = True
            break
        except Exception as e:
            print(f"  {city}: {str(e)[:60]}")
            time.sleep(20 * (attempt + 1))
    time.sleep(3)

df = pd.DataFrame(rows)
df.to_csv(PROC / "city_features_osm.csv", index=False)
print(f"total cities now: {len(df)}")
