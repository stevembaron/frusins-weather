#!/usr/bin/env python3
"""Generate a self-contained static site (docs/index.html) from the race data.

The page is pure HTML/CSS/JS with the race data embedded inline, so it works on
GitHub Pages with no build step or network access. Re-run this whenever the
seed data in races.py changes:

    python3 build_site.py
"""

import json
from pathlib import Path

from races import STEVE_RACES, KELLY_RACES

OUT = Path(__file__).parent / "index.html"

FIELDS = ["name", "date", "location", "overall_place", "overall_total",
          "gender_place", "gender_total", "division_place", "division_total",
          "pace", "final_time"]


def to_records(runner, races):
    return [dict(runner=runner, **dict(zip(FIELDS, r))) for r in races]


def build():
    records = to_records("Steve", STEVE_RACES) + to_records("Kelly", KELLY_RACES)
    records.sort(key=lambda r: r["date"], reverse=True)
    data_json = json.dumps(records, indent=0, separators=(",", ":"))

    html = TEMPLATE.replace("__DATA__", data_json)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    print(f"Wrote {OUT} ({len(records)} races)")


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Baron Family Race Results</title>
<style>
  :root {
    --bg: #0f172a; --card: #1e293b; --line: #334155;
    --text: #e2e8f0; --muted: #94a3b8;
    --steve: #38bdf8; --kelly: #f472b6; --accent: #34d399;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5;
  }
  header { padding: 2rem 1rem 1rem; text-align: center; }
  h1 { margin: 0 0 .25rem; font-size: 1.8rem; }
  .sub { color: var(--muted); font-size: .95rem; }
  .wrap { max-width: 1000px; margin: 0 auto; padding: 0 1rem 3rem; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .75rem; margin: 1.5rem 0; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 1rem; text-align: center; }
  .card .num { font-size: 1.6rem; font-weight: 700; }
  .card .lbl { color: var(--muted); font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; }
  .controls { display: flex; flex-wrap: wrap; gap: .6rem; align-items: center; margin-bottom: 1rem; }
  .controls input, .controls select {
    background: var(--card); color: var(--text); border: 1px solid var(--line);
    border-radius: 8px; padding: .5rem .7rem; font-size: .9rem;
  }
  .controls input[type=search] { flex: 1; min-width: 160px; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
  .seg button { background: var(--card); color: var(--muted); border: 0; padding: .5rem .9rem; cursor: pointer; font-size: .9rem; }
  .seg button.active { background: var(--accent); color: #06281d; font-weight: 600; }
  table { width: 100%; border-collapse: collapse; font-size: .9rem; }
  th, td { padding: .6rem .5rem; text-align: left; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 600; cursor: pointer; user-select: none; white-space: nowrap; }
  th:hover { color: var(--text); }
  tbody tr:hover { background: rgba(148,163,184,.08); }
  .pill { display: inline-block; padding: .12rem .5rem; border-radius: 999px; font-size: .75rem; font-weight: 600; }
  .pill.Steve { background: rgba(56,189,248,.15); color: var(--steve); }
  .pill.Kelly { background: rgba(244,114,182,.15); color: var(--kelly); }
  .num-cell { font-variant-numeric: tabular-nums; }
  .muted { color: var(--muted); }
  footer { text-align: center; color: var(--muted); font-size: .8rem; padding: 2rem 1rem; }
  @media (max-width: 640px) {
    .hide-sm { display: none; }
  }
</style>
</head>
<body>
<header>
  <h1>🏃 Baron Family Race Results</h1>
  <div class="sub">A running history, 2003–present</div>
</header>
<div class="wrap">
  <div class="cards" id="cards"></div>

  <div class="controls">
    <div class="seg" id="runnerSeg">
      <button data-runner="All" class="active">All</button>
      <button data-runner="Steve">Steve</button>
      <button data-runner="Kelly">Kelly</button>
    </div>
    <select id="yearSel"><option value="">All years</option></select>
    <input type="search" id="search" placeholder="Search race or location…">
  </div>

  <table>
    <thead>
      <tr>
        <th data-key="runner">Runner</th>
        <th data-key="date">Date</th>
        <th data-key="name">Race</th>
        <th data-key="location" class="hide-sm">Location</th>
        <th data-key="final_time">Time</th>
        <th data-key="pace" class="hide-sm">Pace</th>
        <th data-key="overall_pct">Overall</th>
      </tr>
    </thead>
    <tbody id="rows"></tbody>
  </table>
  <p class="muted" id="count"></p>
</div>
<footer>Generated from the race-tracker database · updated automatically</footer>

<script>
const DATA = __DATA__;

const state = { runner: "All", year: "", search: "", sortKey: "date", sortDir: -1 };

function pct(p, t) { return (p && t) ? Math.round(p / t * 100) : null; }
function placeText(p, t) { return (p && t) ? `${p.toLocaleString()} of ${t.toLocaleString()} (${pct(p,t)}%)` : "—"; }

function filtered() {
  return DATA.filter(r => {
    if (state.runner !== "All" && r.runner !== state.runner) return false;
    if (state.year && !r.date.startsWith(state.year)) return false;
    if (state.search) {
      const q = state.search.toLowerCase();
      if (!r.name.toLowerCase().includes(q) && !r.location.toLowerCase().includes(q)) return false;
    }
    return true;
  });
}

function sorted(rows) {
  const k = state.sortKey, dir = state.sortDir;
  return rows.slice().sort((a, b) => {
    let av, bv;
    if (k === "overall_pct") { av = pct(a.overall_place, a.overall_total) ?? 999; bv = pct(b.overall_place, b.overall_total) ?? 999; }
    else { av = a[k]; bv = b[k]; }
    if (av < bv) return -1 * dir;
    if (av > bv) return 1 * dir;
    return 0;
  });
}

function renderCards(rows) {
  const total = rows.length;
  const years = new Set(rows.map(r => r.date.slice(0, 4)));
  const marathons = rows.filter(r => /marathon/i.test(r.name) && !/half/i.test(r.name)).length;
  const halfs = rows.filter(r => /half/i.test(r.name)).length;
  const cards = [
    ["Total races", total],
    ["Years active", years.size],
    ["Marathons", marathons],
    ["Half marathons", halfs],
  ];
  document.getElementById("cards").innerHTML = cards.map(([l, n]) =>
    `<div class="card"><div class="num">${n}</div><div class="lbl">${l}</div></div>`).join("");
}

function render() {
  const rows = sorted(filtered());
  renderCards(rows);
  document.getElementById("rows").innerHTML = rows.map(r => `
    <tr>
      <td><span class="pill ${r.runner}">${r.runner}</span></td>
      <td class="num-cell">${r.date}</td>
      <td>${r.name}</td>
      <td class="hide-sm muted">${r.location}</td>
      <td class="num-cell">${r.final_time}</td>
      <td class="hide-sm num-cell">${r.pace ? r.pace + " /mi" : "—"}</td>
      <td class="num-cell">${placeText(r.overall_place, r.overall_total)}</td>
    </tr>`).join("");
  document.getElementById("count").textContent = `${rows.length} race(s) shown`;
}

// Year dropdown
const years = [...new Set(DATA.map(r => r.date.slice(0, 4)))].sort().reverse();
const yearSel = document.getElementById("yearSel");
years.forEach(y => { const o = document.createElement("option"); o.value = y; o.textContent = y; yearSel.appendChild(o); });

// Wire controls
document.getElementById("runnerSeg").addEventListener("click", e => {
  if (e.target.tagName !== "BUTTON") return;
  state.runner = e.target.dataset.runner;
  document.querySelectorAll("#runnerSeg button").forEach(b => b.classList.toggle("active", b === e.target));
  render();
});
yearSel.addEventListener("change", e => { state.year = e.target.value; render(); });
document.getElementById("search").addEventListener("input", e => { state.search = e.target.value; render(); });
document.querySelectorAll("th[data-key]").forEach(th => th.addEventListener("click", () => {
  const k = th.dataset.key;
  if (state.sortKey === k) state.sortDir *= -1; else { state.sortKey = k; state.sortDir = 1; }
  render();
}));

render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
