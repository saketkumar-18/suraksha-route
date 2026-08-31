# Suraksha — Women's Safety Route Scorer

Score city routes by **crime data, street lighting, crowd density and open
businesses at night**; suggest the safest route home.

**Live:** https://suraksha-route.vercel.app

## What it does

1. Pick a city (53 Indian metros, NCRB Crime in India 2023 data) and a departure
   time bucket (day / evening / late night / after midnight).
2. Set start & destination (search or tap the map).
3. The app pulls alternative routes from OSRM, builds a **350 m safety grid**
   from live OpenStreetMap features (street lamps, bus stops, shops, cafés,
   pharmacies, ATMs, police stations, road class), and scores every route
   0–100: lighting · open venues · footfall proxy · official watch · visibility,
   weighted by time of day and the city's NCRB street-crime context.
4. The safest route is highlighted green; the darkest, emptiest stretches are
   flagged red on the map so you know exactly where to be alert.
5. SOS button: one tap to call 112 / women helpline 1091 and share your live
   location.

## Safety model

Cell score (per 350 m grid cell, 0–100):

```
score = 0.34·lighting×(0.4+0.6·timeWeight) + 0.26·openVenues
      + 0.22·crowdProxy + 0.10·officialWatch + 0.08·visibility
```

Route aggregation emphasizes the **worst 25% of cells** — night safety is
dominated by the darkest kilometer, not the average. The final score scales by
the city's NCRB street-crime band (rape + kidnapping & abduction + assault +
insult to modesty rate per lakh women, CII 2023 Table 3B.2).

Full details: [docs/METHODOLOGY.md](docs/METHODOLOGY.md) ·
[docs/ETHICS.md](docs/ETHICS.md)

## Data sources

| Source | Use | License |
|---|---|---|
| NCRB *Crime in India 2023* (via OpenCity CKAN mirror of data.gov.in) | city crime context, 53 metros | Government Open Data (GODL) |
| OpenStreetMap (Overpass API) | street lamps, venues, transit, police, roads | ODbL |
| OSRM (demo server) | alternative routes | Apache 2.0 |
| Nominatim | place search | ODbL, usage policy respected |

## Repo layout

```
scripts/    fetch + parse + build pipeline (NCRB PDFs/XLSX -> tidy CSVs -> JS)
ml/         train.py — street-crime risk model (sklearn), metrics, importances
web/        static app: index.html, style.css, safety.js, app.js, cities-data.js
tests/      pytest suite: data integrity, JS-model parity (node), live routing
docs/       METHODOLOGY.md, ETHICS.md, DEPLOYMENT.md
data/       raw (not committed) + processed CSVs (committed)
```

## Run locally

```bash
python -m http.server -d web 8000
# open http://localhost:8000
```

Tests (needs python deps + node on PATH):

```bash
uv venv .venv && uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python.exe -m pytest
```

## Limitations

- OSM street-lamp coverage in Indian cities is partial — lighting scores are
  best-effort and improve as OSM grows.
- Crime data is city-level (NCRB publishes district/city, not street-level);
  the grid model is a heuristic informed by urban-form research, **not** a
  street-crime predictor.
- Research prototype. Always prefer official guidance and your own judgment.

## License

MIT. Data belongs to its respective sources (NCRB/GODL, OSM/ODbL).
