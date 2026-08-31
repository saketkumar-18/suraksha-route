"""Fetch per-city OSM macro features (Overpass) -> data/processed/city_features_osm.csv.

v2: resilient — mirrors, retries/backoff, footways dropped (10x lighter),
truncation (`remark`) detection, per-feature sanity floors.
"""
import json
import math
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
CACHE = RAW / "overpass_macro"
CACHE.mkdir(exist_ok=True, parents=True)

UA = {"User-Agent": "suraksha-route/1.0 (research)"}
MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

cities = pd.read_csv(PROC / "cities_master_53.csv")
geo = json.loads((RAW / "geocode_cache_v2.json").read_text())


def bbox(lat, lon, km=6):
    dlat = km / 111.0
    dlng = km / (111.0 * math.cos(math.radians(lat)))
    return f"{lat-dlat:.4f},{lon-dlng:.4f},{lat+dlat:.4f},{lon+dlng:.4f}"


Q = """[out:json][timeout:300];
(
  way["highway"~"^(primary|secondary|tertiary|residential|trunk|living_street|unclassified)$"]({bbox});
  node["highway"="street_lamp"]({bbox});
  node["highway"="bus_stop"]({bbox});
  node["railway"~"station|halt|tram_stop"]({bbox});
  node["amenity"="police"]({bbox});
  node["shop"]({bbox});
  node["amenity"~"^(pharmacy|bank|atm|cafe|restaurant|fast_food|bar)$"]({bbox});
);
out body geom qt;"""


def fetch(city, lat, lon, tries=3):
    f = CACHE / (city.replace(" ", "_") + ".json")
    if f.exists():
        d = json.loads(f.read_text())
        if not d.get("remark") and d.get("elements"):
            return d
        f.unlink()  # cached copy was truncated; refetch
    last_err = None
    for attempt in range(tries):
        mirror = MIRRORS[attempt % len(MIRRORS)]
        try:
            r = requests.post(
                mirror, data={"data": Q.format(bbox=bbox(lat, lon))},
                headers=UA, timeout=320,
            )
            if r.status_code in (429, 504):
                last_err = f"{r.status_code} at {mirror}"
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            d = r.json()
            if d.get("remark"):
                last_err = f"truncated: {d['remark'][:80]}"
                time.sleep(10)
                continue
            if not d.get("elements"):
                last_err = "empty"
                time.sleep(5)
                continue
            f.write_text(r.text)
            return d
        except Exception as e:
            last_err = str(e)[:90]
            time.sleep(15 * (attempt + 1))
    print(f"  FAIL {city}: {last_err}")
    return None


def features_for(city, osm, lat, lon):
    area = math.pi * 36  # 6km radius
    road_km = 0.0
    lamps = transit = police = venues = 0
    coslat = math.cos(math.radians(lat))
    for e in osm.get("elements", []):
        if e["type"] == "way":
            geom = e.get("geometry") or []
            for i in range(1, len(geom)):
                # degree deltas * 111 km — NOT radians (that bug cost a 57x underestimate)
                dy = (geom[i]["lat"] - geom[i - 1]["lat"]) * 111.0
                dx = (geom[i]["lon"] - geom[i - 1]["lon"]) * 111.0 * coslat
                road_km += math.hypot(dx, dy)
        elif e["type"] == "node":
            t = e.get("tags", {})
            if t.get("highway") == "street_lamp":
                lamps += 1
            elif t.get("highway") == "bus_stop" or t.get("railway"):
                transit += 1
            elif t.get("amenity") == "police":
                police += 1
            elif t.get("shop") or t.get("amenity") in (
                "pharmacy", "bank", "atm", "cafe", "restaurant", "fast_food", "bar"
            ):
                venues += 1
    return {
        "road_km_per_km2": road_km / area,
        "lamps_per_road_km": lamps / max(0.5, road_km),
        "venue_density": venues / area,
        "transit_density": transit / area,
        "police_density": police / area,
    }


rows = []
fail = []
for _, r in cities.iterrows():
    g = geo.get(r["city"])
    if not g:
        print("skip (no geo):", r["city"])
        continue
    osm = fetch(r["city"], g[0], g[1])
    if osm is None:
        fail.append(r["city"])
        continue
    f = features_for(r["city"], osm, g[0], g[1])
    f["city"] = r["city"]
    f["street_crime_rate"] = r["street_crime_rate"]
    f["population_lakhs"] = r["population_lakhs"]
    f["assault_share"] = r["assault_354"] / r["total_crimes"]
    f["kidnap_share"] = r["kidnap_abduct"] / r["total_crimes"]
    f["pop_density_lakh_per_km2"] = r["population_lakhs"] / (math.pi * 36)
    rows.append(f)
    print(f"{r['city']}: roads={f['road_km_per_km2']:.1f} lamps/rdkm={f['lamps_per_road_km']:.2f} venues={f['venue_density']:.1f} transit={f['transit_density']:.1f}")
    time.sleep(3)

df = pd.DataFrame(rows)
df.to_csv(PROC / "city_features_osm.csv", index=False)
print(f"saved {PROC/'city_features_osm.csv'}: {len(df)} cities, failed: {fail}")
