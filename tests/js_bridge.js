// Test harness bridge: exposes the browser-model functions to Node tests.
// JSON.stringify drops functions, so tests need real callable shims.
const path = require("path");
const M = require(path.join(__dirname, "..", "web", "safety.js"));

const bridge = {
  TIME_PROFILES: M.TIME_PROFILES,
  scoreCell: function (f, t) { return M.scoreCell(f, t); },
  scoreRoute: function (cells, t) { return M.scoreRoute(cells, t); },
  finalScore: function (agg, band) { return M.finalScore(agg, band); },
  cityCrimeBand: function (r) { return M.cityCrimeBand(r); },
  band: function (s) { return M.band(s); },
};
module.exports = bridge;
