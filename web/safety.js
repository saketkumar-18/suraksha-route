/* Suraksha safety model — deterministic scoring shared by web + tests.
 *
 * A route is sampled into N points; each point gets a GRID cell score built from
 * OSM-derived features (street lights, transit nodes, shops/ATMs/pharmacies,
 * road class, visibility). The route score aggregates cell scores weighted by
 * WORST-STRETCH emphasis (night safety is dominated by the darkest kilometer,
 * not the average). City crime context from NCRB scales the final band.
 *
 * All weights are explicit and documented in docs/METHODOLOGY.md.
 */
(function (global) {
  "use strict";

  // Time buckets: share of venues open, crowd weight, light weight
  var TIME_PROFILES = {
    day:   { openShare: 0.95, crowdW: 1.0,  lightW: 0.35 }, // 10:00-17:59
    early: { openShare: 0.75, crowdW: 0.9,  lightW: 0.85 }, // 18:00-20:59
    night: { openShare: 0.40, crowdW: 0.55, lightW: 1.0  }, // 21:00-23:59
    late:  { openShare: 0.15, crowdW: 0.30, lightW: 1.0  } // 00:00-05:59
  };

  // City context scale from NCRB street-crime rate (per lakh) — quartile bands
  function cityCrimeBand(streetCrimeRate) {
    if (streetCrimeRate == null) return { band: "unknown", mult: 1.0, label: "—" };
    if (streetCrimeRate < 40)  return { band: "low",   mult: 0.9, label: "Low" };
    if (streetCrimeRate < 80)  return { band: "mid",   mult: 1.0, label: "Moderate" };
    if (streetCrimeRate < 120) return { band: "high",  mult: 1.12, label: "High" };
    return { band: "veryhigh", mult: 1.25, label: "Very High" };
  }

  // Raw cell features -> 0..100 cell score (100 = safest)
  function scoreCell(f, timeKey) {
    var T = TIME_PROFILES[timeKey] || TIME_PROFILES.early;

    // Lighting: prefer pre-computed blend (lit=yes share + lamp density),
    // fall back to raw lamps-per-km for callers that only have that.
    var lighting;
    if (f.lighting != null) {
      lighting = Math.max(0, Math.min(1, f.lighting));
    } else {
      var lights = Math.max(0, f.lights_per_km || 0);
      lighting = Math.min(1, lights / 6); // 6+ lamps/km = well lit
    }

    // Open venues: shops/ATMs/pharmacies/etc per km², gated by time
    var openVenues = (f.venues_per_km2 || 0) * T.openShare;
    var venueScore = Math.min(1, openVenues / 40);        // 40+ venues/km² = lively

    // Crowd proxy: transit stops + colleges + offices -> footfall potential
    var crowd = (f.transit_per_km2 || 0) * T.crowdW + (f.activity_per_km2 || 0) * 0.5;
    var crowdScore = Math.min(1, crowd / 25);

    // Official watch: police + CCTV-flagged features are rare in OSM; bonus capped
    var watch = Math.min(1, (f.police_per_km2 || 0) / 2 + (f.cctv || 0) / 4);

    // Visibility: wide/primary roads better sightlines than service lanes
    var vis = f.visibility != null ? Math.max(0, Math.min(1, f.visibility)) : 0.5;

    var s =
      0.34 * lighting * (0.4 + 0.6 * T.lightW) +
      0.26 * venueScore +
      0.22 * crowdScore +
      0.10 * watch +
      0.08 * vis;
    return Math.round(s * 100);
  }

  // Route aggregation: emphasize worst stretches at night
  function scoreRoute(cells, timeKey) {
    if (!cells || !cells.length) return null;
    var T = TIME_PROFILES[timeKey] || TIME_PROFILES.early;
    var worstW = { day: 0.25, early: 0.4, night: 0.55, late: 0.65 }[timeKey] || 0.4;

    var mean = cells.reduce(function (a, c) { return a + c.score; }, 0) / cells.length;
    cells.sort(function (a, b) { return a.score - b.score; });
    var worst = cells.slice(0, Math.max(1, Math.ceil(cells.length * 0.25)))
                      .reduce(function (a, c) { return a + c.score; }, 0) /
                Math.max(1, Math.ceil(cells.length * 0.25));

    var base = (1 - worstW) * mean + worstW * worst;
    return { mean: Math.round(mean), worst: Math.round(worst), base: Math.round(base) };
  }

  // Final 0..100 with city crime multiplier.
  // mult > 1 = higher-crime city -> DIVIDE, so risk context LOWERS the score.
  function finalScore(routeAgg, cityBand) {
    if (!routeAgg) return null;
    var v = Math.max(0, Math.min(100, routeAgg.base / (cityBand.mult || 1)));
    return Math.round(v);
  }

  function band(score) {
    if (score == null) return { cls: "score-yellow", label: "—" };
    if (score >= 70) return { cls: "score-green", label: "Safer" };
    if (score >= 45) return { cls: "score-yellow", label: "Caution" };
    return { cls: "score-red", label: "Risky" };
  }

  var SafetyModel = {
    TIME_PROFILES: TIME_PROFILES,
    cityCrimeBand: cityCrimeBand,
    scoreCell: scoreCell,
    scoreRoute: scoreRoute,
    finalScore: finalScore,
    band: band
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = SafetyModel;
  } else {
    global.SafetyModel = SafetyModel;
  }
})(typeof window !== "undefined" ? window : this);
