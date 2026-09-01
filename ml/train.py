"""Train the macro street-crime risk model.

Task: predict a city's street-crime rate band (quartile) from OSM urban-form
features (road density, lit-road share, venue density, transit density) —
i.e. learn what built-environment correlates with street crime against women.

Data: NCRB CII 2023 (53 metros) x OSM macro features (per-city Overpass stats).
Model: RandomForest + GradientBoosting comparison, 5-fold stratified CV.
Outputs: ml/model.joblib, ml/metrics.json, ml/importances.json
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
ML = ROOT / "ml"
ML.mkdir(exist_ok=True)

df = pd.read_csv(PROC / "city_features_osm.csv")
if "lit_share" not in df.columns:
    df["lit_share"] = 0.0
df["lit_share"] = df["lit_share"].fillna(0.0)
y_band = pd.qcut(df["street_crime_rate"], q=3, labels=["low", "mid", "high"])
X = df[[
    "road_km_per_km2", "lit_share", "venue_density", "transit_density",
    "police_density", "pop_density_lakh_per_km2", "assault_share", "kidnap_share",
]]
y = y_band.astype(str).values

models = {
    "rf": Pipeline([("sc", StandardScaler()), ("clf", RandomForestClassifier(n_estimators=300, random_state=42, class_weight="balanced"))]),
    "gb": Pipeline([("sc", StandardScaler()), ("clf", GradientBoostingClassifier(n_estimators=200, random_state=42))]),
    "lr": Pipeline([("sc", StandardScaler()), ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))]),
}

# small-sample guard: n_splits must be <= smallest band count
n_splits = min(5, pd.Series(y).value_counts().min())
print(f"cities: {len(df)} | cv folds: {n_splits}")
skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
results = {}
for name, m in models.items():
    acc = cross_val_score(m, X, y, cv=skf, scoring="accuracy")
    f1 = cross_val_score(m, X, y, cv=skf, scoring="f1_macro")
    m.fit(X, y)
    results[name] = {
        "cv_accuracy_mean": round(float(acc.mean()), 3),
        "cv_accuracy_std": round(float(acc.std()), 3),
        "cv_f1_macro_mean": round(float(f1.mean()), 3),
        "cv_f1_macro_std": round(float(f1.std()), 3),
    }
    print(f"{name}: acc={acc.mean():.3f}±{acc.std():.3f} f1={f1.mean():.3f}±{f1.std():.3f}")

# pick best by f1
best_name = max(results, key=lambda k: results[k]["cv_f1_macro_mean"])
best = models[best_name]
print("BEST:", best_name)

# permutation importance on the best model (fit on all data)
pi = permutation_importance(best, X, y, n_repeats=20, random_state=42, scoring="f1_macro")
imps = sorted(zip(X.columns, pi.importances_mean), key=lambda t: -t[1])
importances = {c: round(v, 4) for c, v in imps}
print("importances:", importances)

# also fit a regressor for continuous rate (for reporting)
from sklearn.ensemble import RandomForestRegressor
rf_reg = RandomForestRegressor(n_estimators=400, random_state=42)
mae = -cross_val_score(rf_reg, X, df["street_crime_rate"], cv=n_splits, scoring="neg_mean_absolute_error")
rf_reg.fit(X, df["street_crime_rate"])
results["rf_regressor_mae"] = round(float(mae.mean()), 2)
results["n_cities"] = int(len(df))
results["majority_band_share"] = round(float(pd.Series(y).value_counts(normalize=True).max()), 3)

joblib.dump({"model": best, "regressor": rf_reg, "features": list(X.columns),
             "bands": ["low", "mid", "high"]}, ML / "model.joblib")
(ML / "metrics.json").write_text(json.dumps(results, indent=2))
(ML / "importances.json").write_text(json.dumps(importances, indent=2))
print("saved ml/model.joblib, metrics.json, importances.json")
