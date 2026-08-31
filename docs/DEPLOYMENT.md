# Deployment

## Live

- **URL:** https://suraksha-route.vercel.app
- **Host:** Vercel (static, zero backend)
- **Deploy:** `cd web && vercel deploy --prod --yes`

## Why static-only

The app is deliberately backend-free:

- Route requests go browser → OSRM public API (CORS-open).
- Grid queries go browser → Overpass mirrors (CORS-open), cached per city
  in-memory.
- No user data ever leaves the device (SOS uses on-device geolocation).

This removes an entire class of privacy risks (see ETHICS.md) and keeps hosting
inside the free tier forever.

## Environment

No secrets, no env vars. Third-party usage policies respected:

- Nominatim: 1 req/s max, app queries on user action only.
- Overpass: mirrors + 3s spacing + per-city caching.
- OSRM demo: fair use, low QPS by design.

## Rebuild pipeline (data refresh)

```bash
# 1. refresh NCRB source files (optional; manifest in data/raw)
python scripts/download_ncrb.py
python scripts/fetch_vol1.py

# 2. re-parse tables
python scripts/parse_final.py

# 3. re-geocode + rebuild web bundle
python scripts/build_city_js.py

# 4. retrain ML model
python ml/train.py

# 5. run tests
python -m pytest
```

## Redeploy checklist

- [ ] `python -m pytest` green
- [ ] `node --check` on all web JS
- [ ] `vercel deploy --prod` from `web/`
- [ ] curl the live URL: title contains "Suraksha"
- [ ] pick two cities, run a route each, scores render
