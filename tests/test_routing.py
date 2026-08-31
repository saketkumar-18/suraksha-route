"""Routing-engine tests against live OSRM (marked network — skipped if unreachable)."""
import json
import urllib.request

import pytest

ROOT = __file__

OSRM = "https://router.project-osrm.org"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "suraksha-route-tests"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


@pytest.mark.parametrize("a,b", [
    ((28.6139, 77.2090), (28.6300, 77.2167)),   # Delhi center -> north
    ((26.1445, 91.7362), (26.1800, 91.7500)),   # Guwahati (city not in 53; tests engine only)
])
def test_osrm_alternatives(a, b):
    try:
        js = _get(f"{OSRM}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}?alternatives=2&overview=false")
    except Exception as e:
        pytest.skip(f"OSRM unreachable: {e}")
    assert js["code"] == "Ok"
    assert len(js["routes"]) >= 1
    r0 = js["routes"][0]
    assert r0["distance"] > 100 and r0["duration"] > 30
