#!/usr/bin/env python3
"""Generate a self-contained static site (index.html) from the race data.

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
<title>The Baron Race Log</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Oswald:wght@500;600;700&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --paper: #f3ece0;
    --card: #fbf7ef;
    --ink: #1c1b19;
    --muted: #8a8170;
    --line: #ddd3c1;
    --steve: #1f5673;
    --kelly: #b23a6e;
    --flag: #e0502a;
    --display: "Oswald", "Arial Narrow", sans-serif;
    --body: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
    --mono: "Roboto Mono", ui-monospace, "SF Mono", Menlo, monospace;
  }
  * { box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    margin: 0; background: var(--paper); color: var(--ink);
    font-family: var(--body); line-height: 1.55;
  }
  .checker {
    height: 14px;
    background-image:
      linear-gradient(45deg, var(--ink) 25%, transparent 25%, transparent 75%, var(--ink) 75%),
      linear-gradient(45deg, var(--ink) 25%, transparent 25%, transparent 75%, var(--ink) 75%);
    background-size: 14px 14px;
    background-position: 0 0, 7px 7px;
  }
  header { max-width: 1040px; margin: 0 auto; padding: 2.4rem 1.25rem 1rem; }
  .kicker {
    font-family: var(--mono); font-size: .72rem; letter-spacing: .35em;
    text-transform: uppercase; color: var(--flag); font-weight: 500; margin-bottom: .4rem;
  }
  h1 {
    font-family: var(--display); font-weight: 700; font-size: clamp(2.4rem, 7vw, 4.2rem);
    line-height: .95; letter-spacing: .01em; text-transform: uppercase; margin: 0;
  }
  .tagline { color: var(--muted); font-size: 1rem; margin-top: .5rem; max-width: 46ch; }

  .wrap { max-width: 1040px; margin: 0 auto; padding: 0 1.25rem 4rem; }

  .stats {
    display: flex; flex-wrap: wrap; gap: 0; margin: 1.75rem 0 2rem;
    border-top: 2px solid var(--ink); border-bottom: 2px solid var(--ink);
  }
  .stat { flex: 1 1 120px; padding: 1rem .5rem 1.1rem; text-align: center; border-right: 1px solid var(--line); }
  .stat:last-child { border-right: 0; }
  .stat-num { display: block; font-family: var(--display); font-weight: 700; font-size: 2.6rem; line-height: 1; }
  .stat-lbl { display: block; font-size: .68rem; letter-spacing: .18em; text-transform: uppercase; color: var(--muted); margin-top: .4rem; }

  .controls { display: flex; flex-wrap: wrap; gap: .7rem; align-items: center; margin-bottom: 1.4rem; }
  .seg { display: inline-flex; border: 2px solid var(--ink); border-radius: 2px; overflow: hidden; }
  .seg button {
    background: transparent; color: var(--ink); border: 0; border-right: 1px solid var(--ink);
    padding: .5rem 1.05rem; cursor: pointer; font-family: var(--display); font-weight: 600;
    font-size: .9rem; letter-spacing: .08em; text-transform: uppercase;
  }
  .seg button:last-child { border-right: 0; }
  .seg button.active { background: var(--ink); color: var(--paper); }
  select, input[type=search] {
    font-family: var(--body); font-size: .9rem; color: var(--ink);
    background: var(--card); border: 1px solid var(--ink); border-radius: 2px; padding: .55rem .7rem;
  }
  input[type=search] { flex: 1; min-width: 170px; }

  .table-wrap { border: 2px solid var(--ink); border-radius: 2px; background: var(--card); overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: .92rem; }
  thead th {
    font-family: var(--display); font-weight: 600; text-transform: uppercase;
    font-size: .72rem; letter-spacing: .12em; color: var(--ink);
    text-align: left; padding: .8rem .7rem; border-bottom: 2px solid var(--ink);
    cursor: pointer; user-select: none; white-space: nowrap; background: var(--paper);
  }
  thead th:hover { color: var(--flag); }
  tbody td { padding: .72rem .7rem; border-bottom: 1px solid var(--line); vertical-align: middle; }
  tbody tr:last-child td { border-bottom: 0; }
  tbody tr:hover { background: #fffdf7; }

  .bib {
    font-family: var(--mono); font-size: .68rem; font-weight: 500; letter-spacing: .06em;
    text-transform: uppercase; padding: .2rem .5rem; border-radius: 2px; color: #fff; white-space: nowrap;
  }
  .bib.Steve { background: var(--steve); }
  .bib.Kelly { background: var(--kelly); }

  .race-name { font-weight: 600; }
  .mono { font-family: var(--mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
  .time { font-family: var(--mono); font-weight: 500; font-size: 1rem; }
  .muted { color: var(--muted); }

  .rank { min-width: 150px; }
  .rank-txt { font-family: var(--mono); font-size: .8rem; display: block; }
  .rank-bar { display: block; height: 5px; margin-top: .35rem; background: var(--line); border-radius: 999px; overflow: hidden; }
  .rank-bar i { display: block; height: 100%; background: var(--flag); }

  .count { color: var(--muted); font-size: .85rem; margin-top: 1rem; font-family: var(--mono); }
  footer {
    max-width: 1040px; margin: 0 auto; padding: 1.5rem 1.25rem 3rem;
    color: var(--muted); font-size: .78rem; font-family: var(--mono); letter-spacing: .03em;
    display: flex; justify-content: space-between; flex-wrap: wrap; gap: .5rem;
    border-top: 1px solid var(--line);
  }
  .legend { display: inline-flex; gap: 1rem; }
  .legend span { display: inline-flex; align-items: center; gap: .35rem; }
  .dot { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
  .dot.Steve { background: var(--steve); } .dot.Kelly { background: var(--kelly); }

  @media (max-width: 680px) { .hide-sm { display: none; } }
</style>
</head>
<body>
<div class="checker"></div>
<header>
  <div class="kicker">Est. 2003 &nbsp;&bull;&nbsp; Salt Lake to Charleston</div>
  <h1>The Baron<br>Race Log</h1>
  <p class="tagline">Two runners, two decades, every start line on record &mdash; from neighborhood 5Ks to full marathons.</p>
</header>
<div class="wrap">
  <div class="stats" id="cards"></div>

  <div class="controls">
    <div class="seg" id="runnerSeg">
      <button data-runner="All" class="active">All</button>
      <button data-runner="Steve">Steve</button>
      <button data-runner="Kelly">Kelly</button>
    </div>
    <select id="yearSel"><option value="">All years</option></select>
    <input type="search" id="search" placeholder="Search race or place…">
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th data-key="runner">Runner</th>
          <th data-key="date">Date</th>
          <th data-key="name">Race</th>
          <th data-key="location" class="hide-sm">Where</th>
          <th data-key="final_time">Time</th>
          <th data-key="pace" class="hide-sm">Pace</th>
          <th data-key="overall_pct">Overall finish</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
  <p class="count" id="count"></p>
</div>
<footer>
  <span class="legend">
    <span><i class="dot Steve"></i> Steve</span>
    <span><i class="dot Kelly"></i> Kelly</span>
  </span>
  <span>Generated from the race-tracker database</span>
</footer>

<script>
const DATA = __DATA__;

const state = { runner: "All", year: "", search: "", sortKey: "date", sortDir: -1 };

function pct(p, t) { return (p && t) ? Math.round(p / t * 100) : null; }

function rankCell(p, t) {
  if (!p || !t) return '<span class="muted mono">&mdash;</span>';
  const beat = 100 - pct(p, t);              // % of the field finished behind
  return `<div class="rank">
    <span class="rank-txt">${p.toLocaleString()} / ${t.toLocaleString()}</span>
    <span class="rank-bar"><i style="width:${beat}%"></i></span>
  </div>`;
}

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
  const years = new Set(rows.map(r => r.date.slice(0, 4)));
  const marathons = rows.filter(r => /marathon/i.test(r.name) && !/half/i.test(r.name)).length;
  const halfs = rows.filter(r => /half/i.test(r.name)).length;
  const cards = [
    ["Races", rows.length],
    ["Years", years.size],
    ["Marathons", marathons],
    ["Halfs", halfs],
  ];
  document.getElementById("cards").innerHTML = cards.map(([l, n]) =>
    `<div class="stat"><span class="stat-num">${n}</span><span class="stat-lbl">${l}</span></div>`).join("");
}

function render() {
  const rows = sorted(filtered());
  renderCards(rows);
  document.getElementById("rows").innerHTML = rows.map(r => `
    <tr>
      <td><span class="bib ${r.runner}">${r.runner}</span></td>
      <td class="mono muted">${r.date}</td>
      <td class="race-name">${r.name}</td>
      <td class="hide-sm muted">${r.location}</td>
      <td class="time">${r.final_time}</td>
      <td class="hide-sm mono muted">${r.pace ? r.pace : "&mdash;"}</td>
      <td>${rankCell(r.overall_place, r.overall_total)}</td>
    </tr>`).join("");
  document.getElementById("count").textContent = `${rows.length} race${rows.length === 1 ? "" : "s"} shown`;
}

const years = [...new Set(DATA.map(r => r.date.slice(0, 4)))].sort().reverse();
const yearSel = document.getElementById("yearSel");
years.forEach(y => { const o = document.createElement("option"); o.value = y; o.textContent = y; yearSel.appendChild(o); });

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
