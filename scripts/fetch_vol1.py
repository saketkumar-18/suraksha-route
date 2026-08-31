"""Download CII 2023 Vol 1 (contains Chapter 3B: Crime Against Women — Metro Cities)."""
import requests
from pathlib import Path

UA = {"User-Agent": "suraksha-route/1.0 (research)"}
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

r = requests.get(
    "https://data.opencity.in/api/3/action/package_show",
    params={"id": "crime-in-india-2023"},
    headers=UA,
    timeout=60,
)
r.raise_for_status()
resources = r.json()["result"]["resources"]
vol1 = [x for x in resources if (x.get("name") or "").strip() == "Crime in India - Vol 1 - 2023"]
if not vol1:
    print("Vol 1 not found"); raise SystemExit(1)
url = vol1[0]["url"]
print("url:", url)
dest = RAW / "cii2023_vol1.pdf"
with requests.get(url, headers=UA, timeout=600, stream=True) as dl:
    dl.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in dl.iter_content(1 << 16):
            f.write(chunk)
print("saved", dest, dest.stat().st_size, "bytes")
