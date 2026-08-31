# Suraksha Safety Model — Methodology

## 1. Problem framing

"Safest route home at night" is not a routing problem OSRM can solve alone: the
shortest path ignores lighting, deserted stretches, closed shops and dark
alleys. Suraksha layers a **safety grid** on top of standard alternatives
routing: we fetch several geometric alternatives from OSRM, then re-rank them
by a transparent, auditable score built from OpenStreetMap urban-form features
and NCRB city crime context.

The model is deliberately **rule-based at the street level** (weights below)
and **statistical at the city level** (trained sklearn model). This separation
matters: street-level "crime prediction" from OSM features would be unsound
and ethically unsafe (see ETHICS.md); city-level risk banding from official
NCRB statistics is defensible and grounded in published government data.

## 2. Data sources

### 2.1 Crime data — NCRB *Crime in India 2023*

- Source of truth: Table 3B.1 (crime against women, IPC+SLL, 53 metropolitan
  cities, 2021–2023) and Table 3B.2 (crime-head-wise & city-wise).
- Obtained via the OpenCity CKAN mirror of the data.gov.in catalog (NCRB
  publishes identical tables as PDF/XLSX; the resource API requires a personal
  key, so we mirror from the CKAN copy with provenance recorded in
  `data/raw/download_manifest.json`).
- **Street-relevant heads** (crimes that plausibly occur on a street/journey):
  - Rape (Sec. 376 IPC / relevant BNS)
  - Kidnapping & Abduction of Women (Sec. 363–369 IPC)
  - Assault on Women with Intent to Outrage her Modesty (Sec. 354 IPC)
  - Insult to the Modesty of Women (Sec. 509 IPC)
- **Excluded heads**: cruelty by husband/relatives (498A) and dowry deaths
  (304B) are overwhelmingly domestic — including them would misroute the
  street-safety signal.
- `street_crime_rate = (rape + K&A + assault354 + insult509) / population_lakhs`
  (NCRB's own per-lakh convention; population is the 2011 census figure NCRB
  uses for rates in CII 2023).

### 2.2 Urban form — OpenStreetMap (Overpass API)

Per-city bbox (6 km radius) and per-route corridor, we query:

| OSM feature | Safety signal |
|---|---|
| `highway=street_lamp` nodes | direct lighting |
| `highway=bus_stop`, `railway=station/halt/tram_stop` | footfall + "help proximity" |
| `shop`, `amenity=pharmacy/bank/atm/cafe/restaurant/fast_food/bar` | open-business density (eyes on the street) |
| `amenity=college/hospital` | daytime crowd generators |
| `amenity=police`, `surveillance=*` | official watch |
| `highway=primary/secondary/...` ways | road length + class (visibility proxy) |

### 2.3 Routing — OSRM

Public demo server (`router.project-osrm.org`, CORS-open) with
`alternatives=3`. Routes are car-profile geometries used as walking corridors —
acceptable for corridor scoring (sidewalks follow the same streets), and noted
as a limitation.

## 3. Grid construction

- The city view is divided into ~350 m cells (0.0032° latitude snap).
- Each cell accumulates: lamp count, transit stops, venue count, activity
  nodes, police, CCTV flags, road length and primary-road share.
- Derived per-cell features: `lights_per_km`, `venues_per_km2`,
  `transit_per_km2`, `police_per_km2`, `activity_per_km2`, `visibility`.
- Cell score (0–100, higher = safer):

```
lightScore   = min(1, lights_per_km / 6)
venueScore   = min(1, openVenues_per_km2 / 40)     # gated by time-of-day openShare
crowdScore   = min(1, (transit·crowdW + activity·0.5) / 25)
watchScore   = min(1, police/2 + cctv/4)
visScore     = primary-road share clipped to [0,1]

score = 100 · ( 0.34·lightScore·(0.4+0.6·lightW)
              + 0.26·venueScore
              + 0.22·crowdScore
              + 0.10·watchScore
              + 0.08·visScore )
```

Weights are fixed by domain reasoning (literature consensus that lighting and
informal surveillance dominate perceived night safety), not fitted to
street-level crime data — we do not have street-level crime data, and fitting
to city totals would be an ecological fallacy.

## 4. Time-of-day model

| Bucket | openShare | crowdW | lightW | worst-stretch weight |
|---|---|---|---|---|
| Day (10–18) | 0.95 | 1.00 | 0.35 | 0.25 |
| Evening (18–21) | 0.75 | 0.90 | 0.85 | 0.40 |
| Night (21–24) | 0.40 | 0.55 | 1.00 | 0.55 |
| After midnight (0–6) | 0.15 | 0.30 | 1.00 | 0.65 |

Rationale: after dark, (a) fewer businesses are open (openShare falls), (b)
transit frequency and footfall fall, (c) lighting becomes the dominant factor,
and (d) a single dark stretch matters more than the route average.

## 5. Route aggregation

- The polyline is sampled every ~150 m; each sample maps to the nearest grid
  cell (≤250 m; beyond that a neutral-cautious 40 is used).
- `mean` = average cell score; `worst` = mean of the worst 25% of cells.
- `base = (1−worstW)·mean + worstW·worst`.
- Final = `clamp(base · cityMultiplier, 0, 100)`.

City multiplier comes from NCRB street-crime-rate bands (quartiles of the 53
metros): low 0.9, mid 1.0, high 1.12, very-high 1.25. A high-crime city scales
risk up (score down), so the same street quality scores lower in Jaipur than
in Chennai.

## 6. City-level ML model (`ml/train.py`)

Purpose: quantify which **urban-form features correlate with street-crime
rates** across the 53 metros, and provide a learned risk banding for cities
outside the NCRB table.

- Features (per city, from Overpass): road km/km², lamps per road-km, venue
  density, transit density, police density, population density, plus NCRB crime
  mix (assault share, kidnap share).
- Target: tercile band of `street_crime_rate`.
- Models compared with 5-fold stratified CV: RandomForest, GradientBoosting,
  Logistic Regression. Best by macro-F1 is persisted (`ml/model.joblib`)
  alongside a RandomForest regressor for the continuous rate.
- Metrics and permutation importances land in `ml/metrics.json` /
  `ml/importances.json` and are quoted in the report.

### Honest expectations

53 samples, 8 features, 3 classes — this is a **descriptive correlation
model**, not a production predictor. CV macro-F1 materially above the majority
band (~0.36) indicates real signal; anything near or below it is reported as
"no learnable signal", which is itself an honest finding for the report.

## 7. Known limitations

1. OSM lamp coverage is uneven; absence of mapped lamps ≠ dark street.
2. NCRB data is city-aggregate; the model does not (and must not) claim
   street-level crime prediction.
3. OSRM alternatives are car routes; walking networks can differ.
4. Overpass demo endpoints are rate-limited; the app caches per-city grids.
5. openShare/crowdW are weekday assumptions; no holiday/festival modelling.
