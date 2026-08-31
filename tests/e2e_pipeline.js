/* E2E pipeline test (no DOM): OSRM routes -> Overpass grid -> score.

Runs the REAL scoring logic (web/safety.js) against live OSRM + Overpass for
a Delhi route, verifying the full data path the app uses in the browser.
*/
const https = require("https");

const SafetyModel = require("../web/safety.js");

function get(url, body) {
  return new Promise((resolve, reject) => {
    const headers = { "User-Agent": "suraksha-route/1.0 (research)" };
    if (body) headers["Content-Type"] = "application/x-www-form-urlencoded";
    const req = https.request(url, { method: body ? "POST" : "GET", headers }, (res) => {
      let d = "";
      res.on("data", (c) => (d += c));
      res.on("end", () => {
        try { resolve(JSON.parse(d)); } catch (e) { reject(new Error("bad json: " + d.slice(0, 80))); }
      });
    });
    req.on("error", reject);
    req.setTimeout(120000, () => { req.destroy(new Error("timeout")); });
    if (body) req.write(body);
    req.end();
  });
}

(async () => {
  // 1. OSRM routes (Connaught Place -> Hauz Khas, Delhi)
  const osrmUrl = "https://router.project-osrm.org/route/v1/driving/77.2167,28.6327;77.0800,28.5800?alternatives=2&overview=full&geometries=geojson&steps=false";
  const osrm = await get(osrmUrl);
  if (osrm.code !== "Ok") throw new Error("OSRM failed: " + osrm.code);
  console.log("OSRM routes:", osrm.routes.length);

  // 2. Overpass grid around midpoint
  const lat = 28.6, lon = 77.21;
  const dlat = 6 / 111, dlng = 6 / (111 * Math.cos(lat * Math.PI / 180));
  const bbox = `${(lat - dlat).toFixed(4)},${(lon - dlng).toFixed(4)},${(lat + dlat).toFixed(4)},${(lon + dlng).toFixed(4)}`;
  const q = `[out:json][timeout:120];(node["highway"="street_lamp"](${bbox});node["highway"="bus_stop"](${bbox});node["railway"~"station|halt|tram_stop"](${bbox});node["amenity"~"police|fire_station"](${bbox});node["surveillance"](${bbox});node["shop"](${bbox});node["amenity"~"pharmacy|bank|atm|cafe|restaurant|fast_food|bar|college|hospital"](${bbox});way["highway"~"^(primary|secondary|tertiary|residential|trunk|living_street)$"](${bbox});way["highway"]["lit"="yes"](${bbox}););out body geom qt;`;
  const overpass = await get("https://overpass-api.de/api/interpreter", "data=" + encodeURIComponent(q));
  if (overpass.remark) throw new Error("overpass truncated: " + overpass.remark);
  console.log("overpass elements:", overpass.elements.length);

  // 3. Build grid (same math as app.js)
  const cells = {};
  const CELL = 0.0032;
  const keyOf = (la, ln) => Math.floor(la / CELL) + "_" + Math.floor(ln / CELL);
  function bump(la, ln, f) {
    if (!la || !ln) return;
    const k = keyOf(la, ln);
    const c = cells[k] || (cells[k] = { lat: 0, lng: 0, n: 0, lights: 0, transit: 0, police: 0, cctv: 0, venues: 0, activity: 0, roadLen: 0, primary: 0, litLen: 0 });
    for (const x in f) c[x] += f[x];
    c.lat += la; c.lng += ln; c.n += 1;
  }
  // turf-free haversine
  const distKm = (a, b) => { const dy = (b[1] - a[1]) * 111, dx = (b[0] - a[0]) * 111 * Math.cos(a[1] * Math.PI / 180); return Math.hypot(dx, dy); };

  overpass.elements.forEach((e) => {
    if (e.type === "node") {
      const t = e.tags || {};
      if (t.highway === "street_lamp") return bump(e.lat, e.lon, { lights: 1 });
      if (t.highway === "bus_stop" || t.railway) return bump(e.lat, e.lon, { transit: 1 });
      if (t.amenity === "police" || t.amenity === "fire_station") return bump(e.lat, e.lon, { police: 1 });
      if (t.surveillance) return bump(e.lat, e.lon, { cctv: 1 });
      if (t.shop) return bump(e.lat, e.lon, { venues: 1 });
      if (["pharmacy", "bank", "atm", "cafe", "restaurant", "fast_food", "bar"].indexOf(t.amenity) >= 0) return bump(e.lat, e.lon, { venues: 1 });
      if (["college", "hospital"].indexOf(t.amenity) >= 0) return bump(e.lat, e.lon, { activity: 1 });
      return;
    }
    if (e.type === "way" && e.geometry) {
      let len = 0;
      for (let i = 1; i < e.geometry.length; i++) len += distKm([e.geometry[i - 1].lon, e.geometry[i - 1].lat], [e.geometry[i].lon, e.geometry[i].lat]);
      const cls = e.tags && e.tags.highway;
      const isMain = ["primary", "trunk", "secondary"].indexOf(cls) >= 0;
      const isLit = e.tags && e.tags.lit === "yes";
      e.geometry.forEach((g) => bump(g.lat, g.lon, { roadLen: len / Math.max(1, e.geometry.length), primary: isMain ? len / Math.max(1, e.geometry.length) : 0, litLen: isLit ? len / Math.max(1, e.geometry.length) : 0 }));
    }
  });
  const feats = Object.values(cells).map((c) => {
    const lat2 = c.lat / c.n, lng2 = c.lng / c.n;
    const areaKm2 = 0.35 * 0.35;
    const roadKm = c.roadLen;
    const lampScore = Math.min(1, c.lights / Math.max(0.05, roadKm) / 6);
    const litShare = Math.min(1, c.litLen / Math.max(0.05, roadKm));
    const LIT_PRIOR = 0.45;
    const lighting = (c.lights > 0 || c.litLen > 0) ? Math.max(lampScore, litShare) : LIT_PRIOR;
    return {
      props: {
        lighting,
        transit_per_km2: c.transit / areaKm2, police_per_km2: c.police / areaKm2, cctv: c.cctv,
        venues_per_km2: c.venues / areaKm2, activity_per_km2: c.activity / areaKm2,
        visibility: Math.min(1, (c.primary / Math.max(0.002, roadKm)) * 3 + 0.35),
      },
      pt: [lng2, lat2],
    };
  });
  console.log("grid cells:", feats.length);

  // 4. Score each route
  const cityBand = SafetyModel.cityCrimeBand(94.7); // Delhi City street-crime rate
  const results = [];
  for (const r of osrm.routes) {
    const line = r.geometry.coordinates;
    const samples = [];
    let acc = 0;
    for (let j = 1; j < line.length; j++) {
      const seg = distKm(line[j - 1], line[j]);
      while (acc + seg >= 0.15 && seg > 0) {
        const t = (0.15 - acc) / seg;
        samples.push([line[j - 1][0] + (line[j][0] - line[j - 1][0]) * t, line[j - 1][1] + (line[j][1] - line[j - 1][1]) * t]);
        acc -= 0.15;
      }
      acc += seg;
    }
    const cellScores = samples.map((p) => {
      let best = null, bestD = 1e9;
      for (const f of feats) {
        const d = distKm([p[0], p[1]], f.pt);
        if (d < bestD) { bestD = d; best = f; }
      }
      if (best && bestD < 0.25) return { score: SafetyModel.scoreCell(best.props, "night") };
      return { score: 40 };
    });
    const agg = SafetyModel.scoreRoute(cellScores, "night");
    const fin = SafetyModel.finalScore(agg, cityBand);
    results.push({ km: (r.distance / 1000).toFixed(1), score: fin, mean: agg.mean, worst: agg.worst });
  }
  results.sort((a, b) => b.score - a.score);
  console.log("SCORED ROUTES (night, Delhi):");
  results.forEach((r, i) => console.log(`  #${i + 1}: ${r.km} km — score ${r.score}/100 (mean ${r.mean}, worst ${r.worst})`));

  if (results.length < 2) throw new Error("expected alternatives");
  const best = results[0];
  if (typeof best.score !== "number" || best.score <= 0) throw new Error("invalid score");
  console.log("E2E_PIPELINE_OK");
})().catch((e) => { console.error("E2E FAILED:", e.message); process.exit(1); });
