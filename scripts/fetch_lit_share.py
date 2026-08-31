"""Fetch lit=yes road coverage per city -> adds lit_share to city_features_osm.csv.

Small targeted query (ways with lit tag only) so it is much lighter than the
main fetch. Merges into data/processed/city_features_osm.csv.
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
CACHE = RAW / "overpass_lit"
CACHE.mkdir(exist_ok=True, parents=True)

UA = {"User-Agent": "suraksha-route/1.0 (research)"}
MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

Q = """[out:json][timeout:120];
(
  way["highway"~"^(primary|secondary|tertiary|residential|trunk|living_street|unclassified)$"]({bbox});
  way["highway"]["lit"="yes"]({bbox});
);
out tags geom qt;"""


def bbox(lat, lon, km=6):
    dlat = km / 111.0
    dlng = km / (111.0 * math.cos(math.radians(lat)))
    return f"{lat-dlat:.4f},{lon-dlng:.4f},{lat+dlat:.4f},{lon+dlng:.4f}"


def fetch(name, lat, lon, tries=3):
    f = CACHE / (name.replace(" ", "_") + ".json")
    if f.exists():
        return json.loads(f.read_text())
    last = None
    for attempt in range(tries):
        mirror = MIRRORS[attempt % len(MIRRORS)]
        try:
            r = requests.post(mirror, data={"data": Q.format(bbox=bbox(lat, lon))},
                              headers=UA, timeout=150)
            if r.status_code in (429, 504):
                last = r.status_code
                time.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            d = r.json()
            f.write_text(r.text)
            return d
        except Exception as e:
            last = str(e)[:80]
            time.sleep(10 * (attempt + 1))
    print("FAIL", name, last)
    return None


def lit_stats(lat, osm):
    coslat = math.cos(math.radians(lat))
    road_km = lit_km = 0.0
    for e in osm.get("elements", []):
        if e["type"] != "way":
            continue
        t = e.get("tags", {})
        g = e.get("geometry") or []
        w = 0.0
        for i in range(1, len(g)):
            dy = (g[i]["lat"] - g[i - 1]["lat"]) * 111.0
            dx = (g[i]["lon"] - g[i - 1]["lon"]) * 111.0 * coslat
            w += math.hypot(dx, dy)
        road_km += w
        if t.get("lit") == "yes":
            lit_km += w
    return road_km, lit_km


def main():
    cities = pd.read_csv(PROC / "cities_master_53.csv")
    geo = json.loads((RAW / "geocode_cache_v2.json").read_text())
    feats = pd.read_csv(PROC / "city_features_osm.csv")

    shares = {}
    for _, r in cities.iterrows():
        g = geo.get(r["city"])
        if not g:
            continue
        d = fetch(r["city"], g[0], g[1])
        if d is None:
            continue
        road_km, lit_km = lit_stats(g[0], d)
        shares[r["city"]] = lit_km / max(0.1, road_km)
        print(f"{r['city']}: lit {lit_km:.0f}/{road_km:.0f} km = {shares[r['city']]:.2f}")
        time.sleep(3)

    feats["lit_share"] = feats["city"].map(shares).fillna(0)
    feats.to_csv(PROC / "city_features_osm.csv", index=False)
    print("merged lit_share into city_features_osm.csv")


if __name__ == "__main__":
    main()
