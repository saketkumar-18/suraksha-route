/* Suraksha app — map, routing, scoring, UI. */
(function () {
  "use strict";

  var state = {
    city: null,
    timeKey: "early",
    pinMode: null,          // 'from' | 'to' | null
    from: null, to: null,   // [lat, lng]
    routes: [],
    selected: null,
    gridLayer: null,
    routeLayers: [],
    fromMarker: null, toMarker: null,
    circles: []
  };

  var OSRM = "https://router.project-osrm.org";
  var OVERPASS = "https://overpass-api.de/api/interpreter";
  var gridCache = {}; // city -> GeoJSON FeatureCollection

  var map = L.map("map", { zoomControl: true, attributionControl: true }).setView([28.6139, 77.209], 12);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd", maxZoom: 20
  }).addTo(map);

  // ---------- helpers ----------
  function $(id) { return document.getElementById(id); }
  function fmtKm(m) { return (m / 1000).toFixed(1) + " km"; }
  function fmtMin(s) { return Math.round(s / 60) + " min"; }
  function toast(msg) {
    var t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add("show"); }, 10);
    setTimeout(function () { t.classList.remove("show"); setTimeout(function(){ t.remove(); }, 300); }, 2600);
  }

  // ---------- city selector ----------
  function initCities() {
    var sel = $("citySelect");
    var cities = (window.CITIES || []).filter(function (c) { return c.center; });
    cities.forEach(function (c) {
      var o = document.createElement("option");
      o.value = c.name;
      o.textContent = c.name;
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () { setCity(sel.value); });
    if (cities.length) setCity(cities[0].name);
  }

  function setCity(name) {
    state.city = (window.CITIES || []).find(function (c) { return c.name === name; });
    if (!state.city) return;
    map.setView(state.city.center, 12);
    clearRoutes();
    renderCityCard();
    loadGrid(state.city);
  }

  function renderCityCard() {
    var c = state.city;
    $("cityTitle").textContent = c.name + " — city context";
    var cb = SafetyModel.cityCrimeBand(c.street_crime_rate);
    var html = "";
    html += stat("Crime vs women (2023)", (c.cases_latest || "—") + " cases", "NCRB CII Table 3B.1");
    html += stat("Street-crime rate", c.street_crime_rate != null ? c.street_crime_rate.toFixed(1) + " /lakh" : "—", "Rape+K&A+Assault+Insult");
    html += stat("Risk context", cb.label, "relative to 53 metros");
    html += stat("Population (2011)", (c.population_lakhs || "—") + " lakh", "NCRB");
    $("cityStats").innerHTML = html;
    $("cityNote").textContent = "City context scales route scores: " + cb.label.toLowerCase() +
      " street-crime cities multiply route risk. Scores are comparative, not absolute.";
  }

  function stat(k, v, s) {
    return '<div class="stat"><div class="k">' + k + '</div><div class="v">' + v + '</div><div class="s">' + s + "</div></div>";
  }

  // ---------- safety grid (Overpass) ----------
  function loadGrid(city) {
    if (gridCache[city.name]) { drawGrid(city.name); return; }
    $("mapLoading").classList.remove("hidden");

    var bbox = bboxAround(city.center, city.radius_km || 6);
    var q = [
      '[out:json][timeout:120];',
      '(',
      'node["highway"="street_lamp"](' + bbox + ');',
      'node["highway"="bus_stop"](' + bbox + ');',
      'node["railway"~"station|halt|tram_stop"](' + bbox + ');',
      'node["amenity"~"police|fire_station"](' + bbox + ');',
      'node["surveillance"](' + bbox + ');',
      'node["shop"](' + bbox + ');',
      'node["amenity"~"pharmacy|bank|atm|cafe|restaurant|fast_food|bar|college|hospital"](' + bbox + ');',
      'way["highway"~"^(primary|secondary|tertiary|residential|trunk|living_street)$"](' + bbox + ');',
      'way["highway"]["lit"="yes"](' + bbox + ');',
      ');out body geom qt;'
    ].join("\n");

    fetch(OVERPASS, {
      method: "POST",
      body: "data=" + encodeURIComponent(q),
      headers: { "Content-Type": "application/x-www-form-urlencoded" }
    })
      .then(function (r) { if (!r.ok) throw new Error("Overpass " + r.status); return r.json(); })
      .then(function (osm) {
        var grid = buildGrid(osm, city);
        gridCache[city.name] = grid;
        drawGrid(city.name);
        $("mapLoading").classList.add("hidden");
      })
      .catch(function (e) {
        $("mapLoading").classList.add("hidden");
        toast("Live grid unavailable (" + e.message + "). Showing routes only.");
      });
  }

  function bboxAround(center, radiusKm) {
    var dLat = radiusKm / 111;
    var dLng = radiusKm / (111 * Math.cos(center[0] * Math.PI / 180));
    var s = (center[0] - dLat).toFixed(4) + "," + (center[1] - dLng).toFixed(4) + ",";
    s += (center[0] + dLat).toFixed(4) + "," + (center[1] + dLng).toFixed(4);
    return s;
  }

  // Aggregate OSM features into a 300m cell grid with per-cell features
  function buildGrid(osm, city) {
    var cells = {};
    var CELL = 0.0032; // ~350m at equator latitude of India
    function keyOf(lat, lng) {
      return Math.floor(lat / CELL) + "_" + Math.floor(lng / CELL);
    }
    function bump(lat, lng, fields) {
      if (!lat || !lng) return;
      var k = keyOf(lat, lng);
      var c = cells[k] || (cells[k] = {
        lat: 0, lng: 0, n: 0, lights: 0, transit: 0, police: 0, cctv: 0,
        venues: 0, activity: 0, roads: 0, roadLen: 0, primary: 0, litLen: 0
      });
      for (var f in fields) c[f] += fields[f];
      c.lat += lat; c.lng += lng; c.n += 1;
    }

    (osm.elements || []).forEach(function (e) {
      if (e.type === "node") {
        var lat = e.lat, lng = e.lon;
        var t = e.tags || {};
        if (t.highway === "street_lamp") return bump(lat, lng, { lights: 1 });
        if (t.highway === "bus_stop" || t.railway) return bump(lat, lng, { transit: 1 });
        if (t.amenity === "police" || t.amenity === "fire_station") return bump(lat, lng, { police: 1 });
        if (t.surveillance) return bump(lat, lng, { cctv: 1 });
        if (t.shop) return bump(lat, lng, { venues: 1 });
        if (["pharmacy", "bank", "atm", "cafe", "restaurant", "fast_food", "bar"].indexOf(t.amenity) >= 0)
          return bump(lat, lng, { venues: 1 });
        if (["college", "hospital"].indexOf(t.amenity) >= 0) return bump(lat, lng, { activity: 1 });
        return;
      }
      if (e.type === "way" && e.geometry) {
        // way length + class + lit status
        var len = 0;
        for (var i = 1; i < e.geometry.length; i++) {
          len += turf.distance(
            [e.geometry[i - 1].lon, e.geometry[i - 1].lat],
            [e.geometry[i].lon, e.geometry[i].lat],
            { units: "kilometers" }
          );
        }
        var cls = e.tags && e.tags.highway;
        var isMain = ["primary", "trunk", "secondary"].indexOf(cls) >= 0;
        var isLit = e.tags && e.tags.lit === "yes";
        e.geometry.forEach(function (g) {
          bump(g.lat, g.lon, {
            roads: 0.001,
            roadLen: len / Math.max(1, e.geometry.length),
            primary: isMain ? 0.001 : 0,
            litLen: isLit ? len / Math.max(1, e.geometry.length) : 0
          });
        });
      }
    });

    // finalize cells -> features
    var feats = [];
    var LIT_PRIOR = 0.45; // unmapped lighting ≠ unlit (see docs/ETHICS.md)
    for (var k in cells) {
      var c = cells[k];
      var lat = c.lat / c.n, lng = c.lng / c.n;
      var areaKm2 = 0.35 * 0.35; // ~350m cells
      // c.roadLen is in KILOMETERS (turf units)
      var roadKm = c.roadLen;
      // Lighting: explicit lamp nodes (per road-km) blended with lit=yes road share.
      // OSM lamp coverage in India is sparse, so lit-share carries the signal;
      // cells with ZERO lighting info get the city-typical prior, not darkness.
      var lampScore = Math.min(1, (c.lights / Math.max(0.05, roadKm)) / 6);
      var litShare = Math.min(1, c.litLen / Math.max(0.05, roadKm));
      var lighting;
      if (c.lights > 0 || c.litLen > 0) {
        lighting = Math.max(lampScore, litShare);
      } else {
        lighting = LIT_PRIOR;
      }
      feats.push({
        type: "Feature",
        properties: {
          lighting: lighting,
          lamps: c.lights,
          road_km: roadKm,
          lit_share: litShare,
          transit_per_km2: c.transit / areaKm2,
          police_per_km2: c.police / areaKm2,
          cctv: c.cctv,
          venues_per_km2: c.venues / areaKm2,
          activity_per_km2: c.activity / areaKm2,
          visibility: Math.min(1, (c.primary / Math.max(0.002, roadKm)) * 3 + 0.35)
        },
        geometry: { type: "Point", coordinates: [lng, lat] }
      });
    }
    return { type: "FeatureCollection", features: feats };
  }

  function drawGrid(cityName) {
    if (state.gridLayer) { map.removeLayer(state.gridLayer); }
    var grid = gridCache[cityName];
    if (!grid) return;
    var timeKey = state.timeKey;
    state.gridLayer = L.layerGroup().addTo(map);
    grid.features.forEach(function (f) {
      var s = SafetyModel.scoreCell(f.properties, timeKey);
      var color = s >= 70 ? "#22c55e" : s >= 45 ? "#eab308" : "#ef4444";
      var opacity = s >= 70 ? 0.16 : s >= 45 ? 0.20 : 0.26;
      L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {
        radius: 9, color: color, weight: 1, fillColor: color, fillOpacity: opacity
      }).addTo(state.gridLayer);
    });
  }

  // ---------- geocoding (Nominatim) ----------
  function geocode(query) {
    var url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=in&q=" +
      encodeURIComponent(query + ", " + (state.city ? state.city.name : ""));
    return fetch(url, { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (js) { return js[0] ? [parseFloat(js[0].lat), parseFloat(js[0].lon)] : null; });
  }

  // ---------- routing (OSRM alternatives) ----------
  function fetchRoutes(from, to) {
    var url = OSRM + "/route/v1/driving/" +
      from[1] + "," + from[0] + ";" + to[1] + "," + to[0] +
      "?alternatives=3&overview=full&geometries=geojson&steps=false";
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error("OSRM " + r.status);
      return r.json();
    }).then(function (js) {
      if (js.code !== "Ok" || !js.routes) throw new Error("No route");
      return js.routes.map(function (r) {
        return { geometry: r.geometry.coordinates, distance: r.distance, duration: r.duration };
      });
    });
  }

  // ---------- score a route against grid ----------
  function scoreRouteAgainstGrid(route) {
    var grid = gridCache[state.city.name];
    var cells = [];
    var stepKm = 0.15;
    var line = route.geometry;
    var samples = [];
    // sample every stepKm along the polyline
    var walked = 0, acc = 0;
    for (var j = 1; j < line.length; j++) {
      var seg = turf.distance([line[j - 1][0], line[j - 1][1]], [line[j][0], line[j][1]], { units: "kilometers" });
      while (acc + seg >= stepKm && seg > 0) {
        var t = (stepKm - acc) / seg;
        var p = [line[j - 1][0] + (line[j][0] - line[j - 1][0]) * t, line[j - 1][1] + (line[j][1] - line[j - 1][1]) * t];
        samples.push(p);
        acc -= stepKm;
      }
      acc += seg;
    }

    if (!grid || !grid.features.length) {
      return { cells: samples.map(function () { return { score: 50 }; }), samples: samples };
    }

    var cellIdx = {};
    grid.features.forEach(function (f) {
      var k = f.geometry.coordinates[1].toFixed(3) + "," + f.geometry.coordinates[0].toFixed(3);
      cellIdx[k] = f;
    });

    samples.forEach(function (p) {
      // nearest cell within 250m
      var best = null, bestD = 1e9;
      for (var k in cellIdx) {
        var f = cellIdx[k];
        var d = turf.distance([p[0], p[1]], f.geometry.coordinates, { units: "kilometers" });
        if (d < bestD) { bestD = d; best = f; }
      }
      if (best && bestD < 0.25) {
        cells.push({ score: SafetyModel.scoreCell(best.properties, state.timeKey) });
      } else {
        cells.push({ score: 40 }); // no data = neutral-cautious
      }
    });
    return { cells: cells, samples: samples };
  }

  // This naive nearest-cell scan is O(N*M) — replace with a spatial index once grid > 2k cells
  // (grid for a metro is ~1200 cells, samples ~60/route, so it is fine).

  // ---------- main flow ----------
  function findRoutes() {
    if (!state.from || !state.to) { toast("Pick start and destination first"); return; }
    var btn = $("routeBtn");
    btn.disabled = true; btn.textContent = "Scoring routes…";
    clearRoutes(false);
    fetchRoutes(state.from, state.to)
      .then(function (routes) {
        state.routes = routes.map(function (r, i) {
          var scored = scoreRouteAgainstGrid(r);
          var agg = SafetyModel.scoreRoute(scored.cells, state.timeKey);
          var cb = SafetyModel.cityCrimeBand(state.city.street_crime_rate);
          var fin = SafetyModel.finalScore(agg, cb);
          return {
            idx: i, geometry: r.geometry, distance: r.distance, duration: r.duration,
            agg: agg, score: fin, band: SafetyModel.band(fin), cells: scored.cells,
            samples: scored.samples
          };
        });
        state.routes.sort(function (a, b) { return b.score - a.score; });
        renderResults();
        drawRouteLayers();
        btn.disabled = false; btn.textContent = "Find Safest Routes";
      })
      .catch(function (e) {
        toast("Routing failed: " + e.message);
        btn.disabled = false; btn.textContent = "Find Safest Routes";
      });
  }

  function renderResults() {
    $("results").classList.remove("hidden");
    var best = state.routes[0];
    $("bestCard").classList.remove("hidden");
    $("bestTitle").textContent = "Safest option — " + fmtKm(best.distance) + " · " + fmtMin(best.duration);
    $("bestMetrics").innerHTML =
      metric("Safety score", best.score + "/100", best.band.cls) +
      metric("Worst stretch", best.agg.worst + "/100", best.agg.worst < 45 ? "score-red" : best.agg.worst < 70 ? "score-yellow" : "score-green") +
      metric("Avg cell score", best.agg.mean + "/100", "") +
      metric("Vs fastest", fastestDelta(best), "");

    var list = $("routeList");
    list.innerHTML = "";
    state.routes.forEach(function (r) {
      var d = document.createElement("div");
      d.className = "route-item";
      d.innerHTML =
        '<div class="route-head"><span class="route-name">' + routeName(r) + "</span>" +
        '<span class="route-score ' + r.band.cls + '">' + r.score + "</span></div>" +
        '<div class="route-meta">' + fmtKm(r.distance) + " · " + fmtMin(r.duration) + " · " + r.band.label + "</div>" +
        '<div class="bars">' +
          bar("Avg cell score", r.agg.mean, r.agg.mean < 45 ? "#ef4444" : "#22c55e") +
          bar("Worst stretch", r.agg.worst, r.agg.worst < 45 ? "#ef4444" : "#22c55e") +
        "</div>";
      d.addEventListener("click", function () { selectRoute(r.idx); });
      list.appendChild(d);
    });
    selectRoute(best.idx, true);
  }

  function routeName(r) {
    if (r.idx === fastestIdx()) return "Fastest";
    return "Alternative " + r.idx;
  }
  function fastestIdx() {
    var f = state.routes[0];
    state.routes.forEach(function (r) { if (r.duration < f.duration) f = r; });
    return f.idx;
  }
  function fastestDelta(best) {
    var f = state.routes.filter(function (r) { return r.idx === fastestIdx(); })[0];
    if (!f || f.idx === best.idx) return "is fastest";
    var d = Math.round((best.duration - f.duration) / 60);
    return "+" + d + " min";
  }

  function metric(k, v, cls) {
    return '<div class="metric"><div class="k">' + k + '</div><div class="v ' + cls + '">' + v + "</div></div>";
  }
  function bar(label, v, color) {
    return '<div class="bar-row"><span>' + label + '</span><div class="bar-track"><div class="bar-fill" style="width:' +
      Math.max(3, Math.min(100, v)) + "%;background:" + color + '"></div></div><span>' + v + "</span></div>";
  }

  function drawRouteLayers() {
    state.routeLayers.forEach(function (l) { map.removeLayer(l); });
    state.routeLayers = [];
    state.routes.forEach(function (r) {
      var latlngs = r.geometry.map(function (c) { return [c[1], c[0]]; });
      var isBest = r === state.routes[0];
      var line = L.polyline(latlngs, {
        color: isBest ? "#22c55e" : "#64748b",
        weight: isBest ? 7 : 5,
        opacity: isBest ? 0.95 : 0.55,
        dashArray: isBest ? null : "8 8"
      }).addTo(map);
      state.routeLayers.push(line);
    });
    var all = state.routes[0].geometry.map(function (c) { return [c[1], c[0]]; });
    map.fitBounds(L.latLngBounds(all).pad(0.15));
  }

  function selectRoute(idx, scroll) {
    state.selected = idx;
    var r = state.routes.filter(function (x) { return x.idx === idx; })[0];
    state.routes.forEach(function (x, i) {
      var el = document.querySelectorAll(".route-item")[state.routes.indexOf(x)];
      if (el) el.classList.toggle("selected", x.idx === idx);
    });
    state.routeLayers.forEach(function (l, i) {
      var x = state.routes[i];
      l.setStyle({
        color: x.idx === idx ? (x === state.routes[0] ? "#22c55e" : "#8b5cf6") : "#64748b",
        weight: x.idx === idx ? 8 : 5,
        opacity: x.idx === idx ? 1 : 0.45,
        dashArray: x.idx === idx && x !== state.routes[0] ? null : (x.idx === idx ? null : "8 8")
      });
    });
    // highlight worst cells of this route
    state.circles.forEach(function (c) { map.removeLayer(c); });
    state.circles = [];
    if (state.gridLayer) map.removeLayer(state.gridLayer);
    state.gridLayer = null;
    // draw red dots on worst cells along route
    r.cells.forEach(function (c, i) {
      if (c.score < 45 && r.samples && r.samples[i]) {
        var p = r.samples[i];
        state.circles.push(
          L.circleMarker([p[1], p[0]], { radius: 6, color: "#ef4444", weight: 2, fillOpacity: 0.9, fillColor: "#ef4444" }).addTo(map)
        );
      }
    });
  }

  function clearRoutes(clearInputs) {
    state.routes = [];
    state.routeLayers.forEach(function (l) { map.removeLayer(l); });
    state.routeLayers = [];
    state.circles.forEach(function (c) { map.removeLayer(c); });
    state.circles = [];
    if (state.gridLayer) { map.removeLayer(state.gridLayer); state.gridLayer = null; }
    $("results").classList.add("hidden");
    $("bestCard").classList.add("hidden");
    $("routeList").innerHTML = "";
    if (clearInputs !== false) {
      state.from = state.to = null;
      if (state.fromMarker) { map.removeLayer(state.fromMarker); state.fromMarker = null; }
      if (state.toMarker) { map.removeLayer(state.toMarker); state.toMarker = null; }
    }
  }

  // ---------- pins / inputs ----------
  function setPin(which, latlng, label) {
    state[which] = [latlng.lat, latlng.lng];
    var input = which === "from" ? $("fromInput") : $("toInput");
    input.value = label || (latlng.lat.toFixed(5) + ", " + latlng.lng.toFixed(5));
    var icon = L.divIcon({
      className: "",
      html: which === "from"
        ? '<div style="width:14px;height:14px;border-radius:50%;background:#22c55e;border:3px solid #0b0e14;box-shadow:0 0 10px #22c55e"></div>'
        : '<div style="width:14px;height:14px;border-radius:50%;background:#ef4444;border:3px solid #0b0e14;box-shadow:0 0 10px #ef4444"></div>',
      iconSize: [20, 20], iconAnchor: [10, 10]
    });
    if (state[which + "Marker"]) map.removeLayer(state[which + "Marker"]);
    state[which + "Marker"] = L.marker(latlng, { icon: icon }).addTo(map);
    state.pinMode = null;
    $("fromPin").classList.remove("active");
    $("toPin").classList.remove("active");
    map.getContainer().style.cursor = "";
  }

  map.on("click", function (e) {
    if (state.pinMode === "from") setPin("from", e.latlng);
    else if (state.pinMode === "to") setPin("to", e.latlng);
  });

  $("fromPin").addEventListener("click", function () {
    state.pinMode = "from";
    this.classList.add("active");
    $("toPin").classList.remove("active");
    map.getContainer().style.cursor = "crosshair";
    toast("Tap the map to set your start point");
  });
  $("toPin").addEventListener("click", function () {
    state.pinMode = "to";
    this.classList.add("active");
    $("fromPin").classList.remove("active");
    map.getContainer().style.cursor = "crosshair";
    toast("Tap the map to set your destination");
  });

  function resolveInput(which) {
    var input = which === "from" ? $("fromInput") : $("toInput");
    var v = input.value.trim();
    if (!v) { toast("Enter a place or use 📍 to pick on map"); return Promise.resolve(null); }
    var coordMatch = v.match(/^(-?\d+\.\d+),\s*(-?\d+\.\d+)$/);
    if (coordMatch) return Promise.resolve([parseFloat(coordMatch[1]), parseFloat(coordMatch[2])]);
    return geocode(v).then(function (ll) {
      if (!ll) toast("Couldn't find '" + v + "' — try 📍");
      return ll;
    });
  }

  $("routeBtn").addEventListener("click", function () {
    Promise.all([resolveInput("from"), resolveInput("to")]).then(function (pts) {
      if (pts[0]) setPin("from", { lat: pts[0][0], lng: pts[0][1] });
      if (pts[1]) setPin("to", { lat: pts[1][0], lng: pts[1][1] });
      if (pts[0] && pts[1]) findRoutes();
    });
  });

  $("timeSelect").addEventListener("change", function () {
    state.timeKey = this.value;
    if (state.city) { drawGrid(state.city.name); }
    if (state.routes.length) renderResults();
  });

  // geolocate button
  $("bestGo").addEventListener("click", function () { if (state.routes.length) selectRoute(state.routes[0].idx); });

  // ---------- SOS ----------
  function openSOS() {
    $("sosModal").classList.remove("hidden");
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(function (pos) {
        var ll = pos.coords.latitude.toFixed(5) + ", " + pos.coords.longitude.toFixed(5);
        $("sosLocation").textContent = "Your location: " + ll;
        $("sosShare").onclick = function () {
          var link = "https://www.openstreetmap.org/?mlat=" + pos.coords.latitude + "&mlon=" + pos.coords.longitude + "#map=17/" + pos.coords.latitude + "/" + pos.coords.longitude;
          if (navigator.share) navigator.share({ title: "My live location", url: link }).catch(function () {});
          else { window.prompt("Copy your location link:", link); }
        };
      }, function () {
        $("sosLocation").textContent = "Location unavailable — call 112 directly.";
        $("sosShare").onclick = null;
      }, { enableHighAccuracy: true, timeout: 8000 });
    } else {
      $("sosLocation").textContent = "Geolocation unsupported — call 112 directly.";
    }
  }
  $("sosBtn").addEventListener("click", openSOS);
  $("sosClose").addEventListener("click", function () { $("sosModal").classList.add("hidden"); });

  // ---------- boot ----------
  initCities();
})();
