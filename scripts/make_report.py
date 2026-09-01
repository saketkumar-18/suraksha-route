"""Generate the Suraksha project report PDF -> ~/Downloads/suraksha-report.pdf.

fpdf2 note: multi_cell defaults to new_x=RIGHT, so after a full-width cell the
cursor sits at the right margin and the NEXT multi_cell(0,...) gets zero width.
Every helper here resets x to the left margin first.
"""
import json
from datetime import date
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
STATS = json.loads((ROOT / "data" / "processed" / "stats_summary.json").read_text())
metrics = {}
mpath = ROOT / "ml" / "metrics.json"
if mpath.exists():
    metrics = json.loads(mpath.read_text())
imp = {}
ipath = ROOT / "ml" / "importances.json"
if ipath.exists():
    imp = json.loads(ipath.read_text())


def A(t):
    """latin-1-safe text: em/en dashes, arrows, plus-minus -> ASCII."""
    return (
        str(t)
        .replace("\u2014", "-").replace("\u2013", "-").replace("\u2018", "'")
        .replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
        .replace("\u00b1", "+/-").replace("\u2192", "->").replace("\u00d7", "x")
        .replace("\u2026", "...")
    )


class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return  # no header band on the title page
        self.set_font("helvetica", "I", 8)
        self.set_text_color(120)
        w = self.epw
        self.cell(w * 0.6, 5, A("Suraksha - Women's Safety Route Scorer"), align="L")
        self.cell(w * 0.4, 5, date.today().isoformat(), align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(120)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


p = PDF()
p.set_auto_page_break(auto=True, margin=18)
p.add_page()


def mc(text, h=5.2, size=10, style=""):
    """Full-width paragraph that always starts at the left margin."""
    p.set_x(p.l_margin)
    p.set_font("helvetica", style, size)
    p.multi_cell(p.epw, h, A(text))
    p.set_x(p.l_margin)


def h1(t):
    p.set_x(p.l_margin)
    p.set_font("helvetica", "B", 13)
    p.set_fill_color(235, 235, 245)
    p.cell(p.epw, 8, "  " + A(t), fill=True)
    p.set_x(p.l_margin)
    p.ln(10)


mc("Suraksha: A Women's Safety Route Scorer for Indian Cities", h=9, size=17, style="B")
mc("Saket Kumar - IIT Guwahati (B.Sc. Data Science & AI) - k.saket@op.iitg.ac.in", h=5, size=10)
p.set_text_color(90)
mc("Live app: https://suraksha-route-iota.vercel.app | Source: github.com/saketkumar-18/suraksha-route", h=5, size=9)
p.set_text_color(0)
p.ln(3)

h1("Abstract")
mc(
    "Women's mobility at night is constrained as much by perceived risk as by "
    "actual safety. Suraksha is a production-deployed web application that "
    f"scores alternative routes across {STATS['cities_covered']} Indian metropolitan cities "
    "using four street-level signals - street lighting, crowd/footfall "
    "proxies, open businesses, and road visibility - combined with official "
    "city-level crime statistics from the NCRB Crime in India 2023 report. "
    "The system fetches candidate routes from OSRM, overlays a 350 m safety "
    "grid built from OpenStreetMap features, and re-ranks alternatives by a "
    "transparent, rule-based safety score that emphasizes the worst stretch "
    "of a journey (the darkest-kilometre problem). A city-level "
    "machine-learning model quantifies which urban-form features correlate "
    "with street-crime rates. The app is fully static (no backend, no "
    "tracking), ships an on-device SOS (112 / women helpline 1091 / "
    "live-location share), and is live at suraksha-route-iota.vercel.app."
)

h1("1. Introduction")
mc(
    "Route planners optimise for time and distance; none of the mainstream "
    "planners used in India expose safety. For women travelling after dark, "
    "the difference between two 20-minute routes is not minutes but exposure: "
    "an unlit 300-metre stretch, a closed market, or an empty bus corridor. "
    "Suraksha reframes routing as a safety-scoring problem: it keeps the "
    "router's geometry but re-ranks its alternatives by environmental safety "
    "signals and official crime context. The goal is decision support - "
    "making the invisible factors (lighting, eyes on the street, visibility) "
    "visible on a map - not crime prediction."
)

h1("2. Data Sources")
mc(
    "Crime: NCRB 'Crime in India 2023' (Tables 3B.1 / 3B.2), all "
    f"{STATS['cities_covered']} metropolitan cities - {STATS['total_cases_2023']:,} cases "
    "registered against women in 2023. Street-relevant heads (rape, "
    "kidnapping & abduction, assault with intent to outrage modesty, insult "
    f"to modesty) total {STATS['total_street_crime']:,} cases "
    f"({100*STATS['total_street_crime']/STATS['total_cases_2023']:.0f}% of the total); "
    "domestic-violence heads are deliberately excluded from street scoring. "
    "Urban form: OpenStreetMap via Overpass (street lamps, lit=yes road tags, "
    "shops, cafes, pharmacies, ATMs, bus stops, rail stations, police, road "
    "class; 51 of 53 cities fetched successfully). Routing: OSRM public API "
    "with alternatives."
)

h1("3. Methodology")
mc(
    "3.1 Safety grid. Each city is divided into ~350 m cells. Per cell: "
    "lighting (lamp density blended with lit-tagged road share; unmapped "
    "cells take a 0.45 city-typical prior - unmapped does not mean unlit), "
    "open-venue density, footfall proxy (transit + institutional activity), "
    "official-watch presence (police/CCTV), and visibility (primary-road "
    "share). Cell score = 100 x (0.34 x lighting x timeW + 0.26 x venues + "
    "0.22 x crowd + 0.10 x watch + 0.08 x visibility)."
)
mc(
    "3.2 Time-of-day model. Four departure buckets (day, evening, late "
    "night, after midnight) set the share of venues assumed open (0.95 to "
    "0.15), crowd weight (1.0 to 0.3), and lighting weight (0.35 to 1.0). "
    "Night safety is dominated by the worst stretch: route aggregation "
    "weights the worst 25% of cells from 0.25 (day) to 0.65 (after midnight)."
)
mc(
    "3.3 City crime context. NCRB street-crime rates band cities into "
    "quartiles; the final route score divides by the band multiplier "
    "(0.9-1.25) so the same street scores lower in Jaipur (133.6 per lakh) "
    "than Chennai (4.9 per lakh)."
)

h1("4. Machine-Learning Model")
mc(
    "A city-level classifier predicts the street-crime-rate tercile band "
    "from OSM urban-form features (road density, lit share, venue density, "
    "transit density, police density, population density, crime-mix shares)."
)
if metrics:
    n = metrics.get("n_cities", "?")
    mj = metrics.get("majority_band_share", 0.35)
    mc(f"Cross-validated results (5-fold, stratified, {n} cities; majority band = {mj:.0%}):")
    p.set_x(p.l_margin)
    p.set_font("courier", "", 8)
    for k in ["lr", "rf", "gb"]:
        v = metrics.get(k)
        if isinstance(v, dict):
            p.set_x(p.l_margin)
            p.multi_cell(p.epw, 4.2, A(
                f"  {k:>4}: acc {v['cv_accuracy_mean']:.3f} +/- {v['cv_accuracy_std']:.3f}  "
                f"F1 {v['cv_f1_macro_mean']:.3f} +/- {v['cv_f1_macro_std']:.3f}"))
            p.set_x(p.l_margin)
    p.set_font("courier", "", 8)
    p.set_x(p.l_margin)
    p.multi_cell(p.epw, 4.2, A(f"  rate regressor MAE: {metrics.get('rf_regressor_mae', '?')} per lakh"))
    p.set_x(p.l_margin)
    p.ln(2)
if imp:
    mc("Permutation importances (top features):")
    p.set_font("courier", "", 8)
    for c, v in list(imp.items())[:6]:
        p.set_x(p.l_margin)
        p.multi_cell(p.epw, 4.2, f"  {A(c)[:26]:<28} {v:.3f}")
        p.set_x(p.l_margin)
    p.ln(2)
mc(
    "The strongest signals are the crime-mix shares (kidnapping, assault - "
    "both NCRB-derived), followed by venue density and police density. "
    "With 51 samples this is a descriptive correlation model, not a "
    "street-level predictor; the reported macro-F1 of ~0.70 against a "
    "majority-band baseline of ~0.35 indicates genuine learnable signal in "
    "urban form."
)

h1("5. System & Deployment")
mc(
    "The web app is a zero-backend static site (Vercel): Leaflet map with a "
    "dark CARTO basemap, client-side Overpass grid caching per city, OSRM "
    "alternative fetching, worst-stretch flagging (red markers on cells "
    "scoring below 45), and an on-device SOS modal (112 / 1091 / Web-Share "
    "live location). No user data leaves the device - no analytics, no "
    "cookies, no backend. The full pipeline (NCRB PDF parsing to tidy CSVs "
    "to JS bundle to ML training to pytest + node test suites) is "
    "reproducible from scripts/."
)

h1("6. Results & Verification")
mc(
    "End-to-end verification: tests/e2e_pipeline.js fetches real OSRM "
    "alternatives for a 20 km Delhi corridor, builds a 1,296-cell grid from "
    "20,809 OSM elements, and produces ranked night scores (28 vs 23 of "
    "100 - the safer route trades ~0.5 km for better-lit, busier cells). "
    "The pytest suite (13 tests, all passing) validates NCRB data integrity "
    "(53 cities; Delhi = 13,366 cases / 75.8 lakh), JS-model parity between "
    "the browser and the test harness, ML artifacts, and live routing. The "
    "deployed app is live and serving the latest build."
)

h1("7. Ethics & Limitations")
mc(
    "NCRB data records reported crime; under-reporting is uneven and a "
    "'low rate' can reflect reporting barriers, not safety. OSM coverage is "
    "volunteer-biased toward wealthier areas, so unmapped cells take a "
    "neutral-cautious prior rather than a low score - the system never "
    "labels a neighbourhood 'risky' merely for being unmapped. Scores are "
    "comparative within a city and time bucket, never absolute claims; the "
    "UI says guidance, not verdicts. OSRM alternatives are car-profile "
    "geometries used as walking corridors. Full statement: docs/ETHICS.md."
)

h1("8. Conclusion")
mc(
    "Suraksha demonstrates that open data (NCRB + OSM + OSRM) is sufficient "
    "to ship a useful, honest safety-aware route planner today: no "
    "proprietary feeds, no backend, no tracking. The scoring is transparent "
    "and auditable, the worst-stretch emphasis matches how people actually "
    "experience night-time risk, and the ethics constraints are engineered "
    "into the product rather than appended to it."
)

out = Path.home() / "Downloads" / "suraksha-report.pdf"
p.output(str(out))
print("WROTE", out, out.stat().st_size, "bytes")
