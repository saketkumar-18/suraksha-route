"""FINAL parser: build cities_master_53.csv for all 53 NCRB metropolitan cities.

Sources (CII 2023, NCRB via OpenCity CKAN):
  A) cii2023_vol1.pdf p316  — Table 3B.1: 19 major metros, totals 2021-23 + population.
  B) cii2023_vol1.pdf p317-332 — Table 3B.2: 19 major metros, head-wise columns.
  C) headwise_citywise_2023.pdf — Table 3B.2 for the other 34 metros.
  D) citywise_2021_2023.pdf — Table 3B.1 for the other 34 metros.

Strategy: generic parser keyed by the bracketed column ids printed in each
page's header (e.g. '[24] [25] [26]'), so column drift between pages is
impossible. Names may be inline ('5 Delhi City ...') or wrapped on the line
above ('  Ahmedabad' / '1 <nums>'); both handled.

Global column ids of interest:
  rape I = 63, K&A women I = 24, assault-354 I = 81, insult-509 I = 90,
  total IPC I = 99, total SLL I = 159, total all I = 162, rate/lakh = 164.
"""
import re
from pathlib import Path

import pdfplumber
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
PROC.mkdir(parents=True, exist_ok=True)

INLINE_RE = re.compile(
    r"^\s*(\d{1,2})\s+([A-Za-z][A-Za-z .&()'\-]*?)\s+((?:\d+(?:\.\d+)?[ ]*)+)$"
)
NUMS_RE = re.compile(r"^\s*(\d{1,2})\s+((?:\d+(?:\.\d+)?[ ]*)+)$")
NAME_RE = re.compile(r"^\s{6,}([A-Za-z][A-Za-z .&()'\-]*?)\s*$")
BRACKET_RE = re.compile(r"\[(\d+)\]")


def page_rows(page):
    """Return list of (sl, city, {colid: value}) using bracket header mapping."""
    lines = [ln.replace(",", "") for ln in (page.extract_text(layout=True) or "").split("\n")]
    # find bracket header line
    col_ids = None
    for ln in lines:
        ids = BRACKET_RE.findall(ln)
        if len(ids) >= 5:
            col_ids = [int(x) for x in ids]
            break
    if not col_ids:
        return []
    data_cols = col_ids[2:]  # first two ids are SL and City

    rows = []
    pending_name = None
    for ln in lines:
        mi = INLINE_RE.match(ln.rstrip())
        mn = NUMS_RE.match(ln.rstrip())
        mw = NAME_RE.match(ln.rstrip())
        if mw and not mn:
            n = mw.group(1).strip()
            if n and "(" not in n and n.upper() != "SL":
                pending_name = n
            continue
        if mi:  # inline name
            sl = int(mi.group(1)); city = mi.group(2).strip()
            nums = [float(x) for x in mi.group(3).split()]
        elif mn:  # wrapped name
            sl = int(mn.group(1)); city = pending_name or f"?{sl}"
            nums = [float(x) for x in mn.group(2).split()]
        else:
            continue
        if "TOTAL" in city.upper():
            continue
        d = dict(zip(data_cols, nums))
        rows.append((sl, city, d))
        pending_name = None
    return rows


def collect(pdf_path, pages, wanted):
    """wanted: {field: global col id}. Returns {city: {field: value}}."""
    out = {}
    with pdfplumber.open(pdf_path) as pdf:
        for pno in pages:
            for sl, city, d in page_rows(pdf.pages[pno]):
                rec = out.setdefault(city, {})
                for f, cid in wanted.items():
                    if cid in d and d[cid] is not None:
                        rec[f] = d[cid]
    return out


def main():
    # A+B: Vol 1 (19 major metros)
    vol1 = RAW / "cii2023_vol1.pdf"
    t31 = collect(vol1, [316], {
        "cases_2021": 3, "cases_2022": 4, "cases_2023": 5,
        "population_lakhs": 6, "rate_total": 7, "chargesheet_rate": 8,
    })
    t32_big = collect(vol1, range(317, 333), {
        "rape": 63, "kidnap_abduct": 24, "assault_354": 81, "insult_509": 90,
        "total_ipc": 99, "total_sll": 159, "total_crimes": 162, "rate_all": 164,
    })

    # C+D: standalone (34 other metros)
    hw = RAW / "headwise_citywise_2023.pdf"
    t32_rest = collect(hw, range(0, 16), {
        "rape": 63, "kidnap_abduct": 24, "assault_354": 81, "insult_509": 90,
        "total_ipc": 99, "total_sll": 159, "total_crimes": 162, "rate_all": 164,
    })
    cw = RAW / "citywise_2021_2023.pdf"
    t31_rest = collect(cw, [0], {
        "cases_2021": 3, "cases_2022": 4, "cases_2023": 5,
        "population_lakhs": 6, "rate_total": 7, "chargesheet_rate": 8,
    })

    cities = set(t31) | set(t32_big) | set(t32_rest) | set(t31_rest)
    recs = []
    for c in sorted(cities):
        if c.startswith("?") or c.upper() == "TOTAL CITIES":
            continue
        rec = {"city": c}
        for src in (t31.get(c, {}), t31_rest.get(c, {}),
                    t32_big.get(c, {}), t32_rest.get(c, {})):
            rec.update({k: v for k, v in src.items() if v is not None})
        recs.append(rec)

    df = pd.DataFrame(recs)
    # keep rows with population and at least one crime head
    df = df[df["population_lakhs"].notna()].copy()
    df = df[df["total_crimes"].notna()].copy()

    df["street_crime"] = df[["rape", "kidnap_abduct", "assault_354", "insult_509"]].fillna(0).sum(axis=1)
    df["street_crime_rate"] = df["street_crime"] / df["population_lakhs"]
    df["street_share_pct"] = 100 * df["street_crime"] / df["total_crimes"]
    df["rape_rate"] = df["rape"].fillna(0) / df["population_lakhs"]
    df["kidnap_rate"] = df["kidnap_abduct"].fillna(0) / df["population_lakhs"]
    df["assault_rate"] = df["assault_354"].fillna(0) / df["population_lakhs"]

    out = PROC / "cities_master_53.csv"
    df = df.sort_values("street_crime_rate", ascending=False).reset_index(drop=True)
    df.to_csv(out, index=False)
    print(f"cities: {len(df)} -> {out}")
    cols = ["city", "cases_2023", "population_lakhs", "rape", "kidnap_abduct",
            "assault_354", "insult_509", "street_crime", "total_crimes",
            "street_crime_rate", "chargesheet_rate"]
    print(df[cols].to_string())


if __name__ == "__main__":
    main()
