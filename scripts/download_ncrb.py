"""Download NCRB Crime Against Women city-level data (2022-2024) from OpenCity CKAN.

Provenance: National Crime Records Bureau 'Crime in India' reports, mirrored on
data.opencity.in (OpenCity CKAN, Government of India open data).
"""
import json
from pathlib import Path

import requests

UA = {"User-Agent": "suraksha-route/1.0 (research; contact: k.saket@op.iitg.ac.in)"}
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

WANT = {
    "crime-in-india-2024": [
        "Metropolitan Cities - Crime Against Women (IPC/BNS+SLL)",
    ],
    "crime-in-india-2023": [
        "City-wise Cases Registered 156_3 under Crimes against Women during 2023",
    ],
    "crime-in-india-2022": [
        "Crimes Against Women in Metros 2022",
    ],
}

manifest = []
for pkg, names in WANT.items():
    r = requests.get(
        "https://data.opencity.in/api/3/action/package_show",
        params={"id": pkg},
        headers=UA,
        timeout=60,
    )
    r.raise_for_status()
    resources = r.json().get("result", {}).get("resources", [])
    for res in resources:
        if (res.get("name") or "").strip() in names:
            url = res["url"]
            fmt = (res.get("format") or "").lower()
            ext = {"csv": ".csv", "xlsx": ".xlsx"}.get(fmt, ".bin")
            slug = pkg.replace("crime-in-india", "cii") + ext
            dest = RAW / slug
            print(f"downloading {res['name']} -> {dest.name}")
            with requests.get(url, headers=UA, timeout=120, stream=True) as dl:
                dl.raise_for_status()
                dest.write_bytes(dl.content)
            manifest.append(
                {
                    "package": pkg,
                    "resource": res.get("name"),
                    "format": fmt,
                    "source_url": url,
                    "local_file": str(dest.relative_to(ROOT)).replace("\\", "/"),
                    "bytes": dest.stat().st_size,
                    "license": r.json()["result"].get("license_url")
                    or r.json()["result"].get("license_title"),
                }
            )

(RAW / "download_manifest.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2)[:800])
