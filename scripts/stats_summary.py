"""Compute top-line project stats from processed data -> stats_summary.json."""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

df = pd.read_csv(PROC / "cities_master_53.csv")
stats = {
    "cities_covered": int(len(df)),
    "total_cases_2023": int(df["cases_2023"].sum()),
    "total_street_crime": int(df["street_crime"].sum()),
    "median_street_rate": round(float(df["street_crime_rate"].median()), 1),
    "top5_riskiest": [
        {"city": r.city, "rate": round(float(r.street_crime_rate), 1)}
        for r in df.nlargest(5, "street_crime_rate").itertuples()
    ],
    "top5_safest": [
        {"city": r.city, "rate": round(float(r.street_crime_rate), 1)}
        for r in df.nsmallest(5, "street_crime_rate").itertuples()
    ],
    "delhi": {
        "cases": int(df[df.city == "Delhi City"].cases_2023.iloc[0]),
        "street_rate": round(float(df[df.city == "Delhi City"].street_crime_rate.iloc[0]), 1),
    },
}

feats_path = PROC / "city_features_osm.csv"
if feats_path.exists():
    f = pd.read_csv(feats_path)
    stats["osm_features_cities"] = int(len(f))
    stats["avg_venue_density"] = round(float(f["venue_density"].mean()), 1)
    stats["avg_road_km_km2"] = round(float(f["road_km_per_km2"].mean()), 1)

out = ROOT / "data" / "processed" / "stats_summary.json"
out.write_text(json.dumps(stats, indent=2))
print(json.dumps(stats, indent=2))
