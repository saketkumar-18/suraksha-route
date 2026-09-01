"""Tests for the Suraksha safety model (JS parity + Python ML pipeline).

JS model is loaded via Node and must produce identical scores to the documented
formula. Python tests validate the trained artifacts + data integrity.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import joblib
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------- data integrity ----------
def test_cities_master_53():
    df = pd.read_csv(ROOT / "data" / "processed" / "cities_master_53.csv")
    assert len(df) == 53, f"expected 53 metros, got {len(df)}"
    for col in ["rape", "kidnap_abduct", "assault_354", "total_crimes", "population_lakhs"]:
        assert df[col].notna().all(), f"{col} has NaN"
    assert (df["total_crimes"] > 0).all()
    # Delhi sanity: NCRB 2023 says 13,366 cases, 75.8 lakh pop
    d = df[df["city"] == "Delhi City"].iloc[0]
    assert d["cases_2023"] == 13366
    assert d["population_lakhs"] == 75.8


def test_street_crime_rate_range():
    df = pd.read_csv(ROOT / "data" / "processed" / "cities_master_53.csv")
    assert df["street_crime_rate"].between(0, 200).all()


def test_cities_js_present():
    js = (ROOT / "web" / "cities-data.js").read_text()
    assert "window.CITIES" in js
    data = json.loads(js.split("=", 1)[1].strip().rstrip(";"))
    assert len(data) >= 50
    for c in data:
        assert "center" in c and len(c["center"]) == 2
        assert "street_crime_rate" in c


# ---------- JS safety model parity ----------
BRIDGE = ROOT / "tests" / "js_bridge.js"


def _js_model():
    """Evaluate an expression in node with the real web/safety.js loaded.

    JSON.stringify drops functions, so tests send arguments and call methods
    inside node; the bridge file provides callable shims.
    """
    def run(fn, *args):
        expr = (
            "const b=require(" + json.dumps(str(BRIDGE).replace("\\", "/")) + ");"
            "const args=" + json.dumps(list(args)) + ";"
            "console.log(JSON.stringify(b." + fn + "(...args)))"
        )
        out = subprocess.run(["node", "-e", expr], capture_output=True, text=True, check=True)
        return json.loads(out.stdout or "null")
    return run


def test_js_model_exported():
    m = _js_model()
    assert m("scoreCell", {"lights_per_km": 1}, "night") is not None  # callable via bridge
    out = subprocess.run(
        ["node", "-e", "const b=require(" + json.dumps(str(BRIDGE).replace("\\", "/")) + ");console.log(JSON.stringify(Object.keys(b)))"],
        capture_output=True, text=True, check=True,
    )
    keys = json.loads(out.stdout)
    for k in ["scoreCell", "scoreRoute", "finalScore", "cityCrimeBand", "band", "TIME_PROFILES"]:
        assert k in keys


def test_well_lit_cell_scores_higher():
    m = _js_model()
    lit = m("scoreCell", {"lights_per_km": 8, "venues_per_km2": 50, "transit_per_km2": 20, "activity_per_km2": 10, "police_per_km2": 1, "visibility": 0.9}, "night")
    dark = m("scoreCell", {"lights_per_km": 0, "venues_per_km2": 0, "transit_per_km2": 0, "activity_per_km2": 0, "police_per_km2": 0, "visibility": 0.1}, "night")
    assert lit > dark
    # night openShare=0.40 caps venue credit; a fully-lit lively cell tops out ~73
    assert lit >= 70, f"well-lit lively night cell should be >=70, got {lit}"
    assert dark <= 25, f"dark empty night cell should be <=25, got {dark}"
    # the same cell by day (openShare=0.95) must outscore night
    day = m("scoreCell", {"lights_per_km": 8, "venues_per_km2": 50, "transit_per_km2": 20, "activity_per_km2": 10, "police_per_km2": 1, "visibility": 0.9}, "day")
    assert day >= 80, f"well-lit lively day cell should be >=80, got {day}"


def test_night_harder_than_day():
    m = _js_model()
    feats = {"lights_per_km": 2, "venues_per_km2": 30, "transit_per_km2": 10, "activity_per_km2": 5, "police_per_km2": 0.2, "visibility": 0.6}
    day = m("scoreCell", feats, "day")
    late = m("scoreCell", feats, "late")
    assert day > late


def test_worst_stretch_dominates_at_night():
    m = _js_model()
    cells = [{"score": 80}, {"score": 80}, {"score": 80}, {"score": 20}]
    agg_day = m("scoreRoute", cells, "day")
    agg_late = m("scoreRoute", cells, "late")
    # worst-quarter weight higher at late -> lower base score
    assert agg_late["base"] < agg_day["base"]


def test_high_crime_city_lowers_final():
    m = _js_model()
    agg = {"mean": 70, "worst": 50, "base": 60}
    low = m("finalScore", agg, m("cityCrimeBand", 10))
    high = m("finalScore", agg, m("cityCrimeBand", 150))
    # mult divides: low-crime city 60/0.9=67, very-high 60/1.25=48
    assert low == 67
    assert high == 48
    assert high < low, "very-high-crime city should produce a lower safety score"


def test_bands():
    m = _js_model()
    assert m("band", 85)["label"] == "Safer"
    assert m("band", 55)["label"] == "Caution"
    assert m("band", 20)["label"] == "Risky"


# ---------- ML artifacts ----------
def test_model_artifacts():
    bundle = joblib.load(ROOT / "ml" / "model.joblib")
    assert "model" in bundle and "regressor" in bundle
    metrics = json.loads((ROOT / "ml" / "metrics.json").read_text())
    assert metrics["rf"]["cv_f1_macro_mean"] > 0.25  # 3-class, majority class ~34% -> must beat chance
    assert "rf_regressor_mae" in metrics


def test_model_predicts_valid_band():
    bundle = joblib.load(ROOT / "ml" / "model.joblib")
    feats = pd.read_csv(ROOT / "data" / "processed" / "city_features_osm.csv")
    # reindex handles optional columns (e.g. lit_share before fetch_lit_share ran)
    X = feats.reindex(columns=bundle["features"], fill_value=0).head(5)
    pred = bundle["model"].predict(X)
    assert set(pred) <= set(bundle["bands"])
