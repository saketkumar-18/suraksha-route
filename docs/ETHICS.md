# Ethics & Responsible Use

## What this system IS

A decision-support tool that makes **urban-form factors visible** — lighting,
open businesses, footfall, road visibility — so a woman planning a journey can
see *why* one route scores safer than another, backed by official city-level
crime statistics from the NCRB.

## What this system IS NOT

- **Not a crime predictor.** We never claim a street is "safe" or "unsafe"
  based on where crimes will happen; we have no street-level crime data, and
  OSM features cannot carry that weight. The city multiplier is derived from
  aggregate official statistics and labelled as such.
- **Not a substitute for official guidance**, policing judgments, or personal
  judgment.
- **Not a surveillance tool.** It reads public map data; it does not track
  users, store locations, or profile anyone. The SOS feature works entirely
  on-device (geolocation + tel: links + Web Share API); nothing is transmitted
  to us — there is no backend, no analytics, no cookies.

## Bias & fairness

- NCRB data records *reported* crimes. Under-reporting is well documented and
  uneven (by city, class, community). A "low rate" can mean better reporting
  barriers, not safer streets. The UI and report state this caveat.
- OSM coverage is volunteer-driven and denser in wealthier areas — grid cells
  with no mapped features get a *neutral-cautious* 40, not a low score, to
  avoid penalising unmapped (often poorer) neighbourhoods as "risky" merely for
  being unmapped.
- Score bands (Safer/Caution/Risky) are comparative within a city and time
  bucket, not absolute claims. The UI labels them as guidance, not verdicts.
- We deliberately exclude domestic-violence heads (498A, dowry deaths) from
  the street-safety score — using them would (a) misstate street risk and
  (b) stigmatise cities for private-violence reporting patterns.

## Harms we actively mitigated

| Harm | Mitigation |
|---|---|
| Victim-blaming ("she took the risky route") | framing is planner/infrastructure; report targets city authorities as much as users |
| Redlining neighbourhoods as "crime areas" | no crime data at neighbourhood level is used; empty cells are neutral, not low |
| False sense of security | "Safer" never means "safe"; prominent disclaimers; worst-stretch flags keep risk visible |
| Data misuse / tracking | static app, zero backend, zero storage; only public map + police stat data |
| Re-traumatising content | crime statistics aggregated by city; no incident narratives |

## If deployed for real

1. Partner with local police / women's organizations for validation.
2. Recalibrate weights with lived-experience surveys (e.g. SafetiPin-style
   audits), not just OSM features.
3. Accessibility & language localization (Hindi + regional first).
4. Never feed scores into anything punitive (insurance, policing allocation)
   — this is a route-planning aid only.

## Data licensing

- NCRB Crime in India tables: Government Open Data License (India).
- OpenStreetMap: ODbL © OSM contributors. Overpass mirrors used with polite
  rate limits and caching.
- This project's code: MIT. Derived stats reproduce NCRB numbers faithfully;
  any error is ours, not NCRB's.
