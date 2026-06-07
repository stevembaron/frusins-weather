#!/usr/bin/env python3
"""Generate a self-contained static site (index.html) from the race data.

The page is pure HTML/CSS/JS with the race data embedded inline, so it works on
GitHub Pages with no build step or network access. Re-run this whenever the
seed data in races.py changes:

    python3 build_site.py
"""

import json
from pathlib import Path

from races import load_races

OUT = Path(__file__).parent / "index.html"


def _minutes(t):
    """Total minutes from 'H:MM:SS' or 'M:SS'."""
    parts = [int(x) for x in t.split(":")]
    h, m, s = ([0] + parts)[-3:] if len(parts) < 3 else parts
    return h * 60 + m + s / 60


def _pace_minutes(p):
    m, s = [int(x) for x in p.split(":")]
    return m + s / 60


def classify(pace, final_time):
    """Infer the actual race distance from time ÷ pace, since race names are
    unreliable (e.g. a '...Marathon & Half & 5K' event where the runner ran
    the full, or a '...Marathon' where they ran the half)."""
    if not pace or not final_time:
        return "Other"
    dist = _minutes(final_time) / _pace_minutes(pace)
    if 24 <= dist <= 28:
        return "Full"
    if 12 <= dist <= 14.5:
        return "Half"
    return "Other"


def build():
    records = [dict(r) for r in load_races()]
    for rec in records:
        rec["kind"] = classify(rec.get("pace"), rec.get("final_time"))
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
  .wrap { max-width: 1040px; margin: 0 auto; padding: 1.25rem 1.25rem 4rem; }

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

  .btn-add {
    font-family: var(--display); font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
    font-size: .85rem; background: var(--flag); color: #fff; border: 2px solid var(--flag);
    border-radius: 2px; padding: .5rem 1rem; cursor: pointer;
  }
  .btn-add:hover { background: #c8421f; border-color: #c8421f; }

  .banner { background: #fff5e2; border: 2px solid var(--flag); border-radius: 2px; padding: 1rem 1.1rem; margin-bottom: 1.3rem; }
  .banner h3 { margin: 0 0 .35rem; font-family: var(--display); text-transform: uppercase; letter-spacing: .05em; font-size: 1rem; }
  .banner p { margin: .3rem 0 .6rem; font-size: .88rem; }
  .banner code { font-family: var(--mono); font-size: .8rem; background: var(--card); padding: .05rem .3rem; border-radius: 2px; }
  .banner textarea { width: 100%; min-height: 70px; font-family: var(--mono); font-size: .76rem; background: var(--card); border: 1px solid var(--line); border-radius: 2px; padding: .55rem; color: var(--ink); resize: vertical; }
  .banner .row { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .55rem; }
  .banner .row button { font-family: var(--body); font-size: .82rem; border: 1px solid var(--ink); background: var(--ink); color: var(--paper); border-radius: 2px; padding: .42rem .8rem; cursor: pointer; }
  .banner .row button.ghost { background: transparent; color: var(--ink); }

  .tag-local {
    display: inline-block; margin-left: .45rem; font-family: var(--mono); font-size: .58rem;
    text-transform: uppercase; letter-spacing: .08em; color: var(--flag);
    border: 1px solid var(--flag); border-radius: 2px; padding: .03rem .3rem; vertical-align: middle;
  }

  .overlay { position: fixed; inset: 0; background: rgba(28,27,25,.55); display: none; align-items: flex-start; justify-content: center; padding: 2rem 1rem; overflow: auto; z-index: 50; }
  .overlay.open { display: flex; }
  .modal { background: var(--paper); border: 2px solid var(--ink); border-radius: 3px; max-width: 540px; width: 100%; padding: 1.4rem; }
  .modal h2 { font-family: var(--display); text-transform: uppercase; margin: 0 0 .3rem; font-size: 1.5rem; }
  .hint { font-size: .82rem; color: var(--muted); margin: 0 0 1rem; }
  .field { margin-bottom: .8rem; }
  .field label { display: block; font-size: .68rem; text-transform: uppercase; letter-spacing: .1em; color: var(--muted); margin-bottom: .25rem; }
  .field input, .field select { width: 100%; font-family: var(--body); font-size: .95rem; padding: .5rem .6rem; border: 1px solid var(--ink); border-radius: 2px; background: var(--card); color: var(--ink); }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: .7rem; }
  .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: .7rem; }
  .place-pair { display: flex; align-items: center; gap: .3rem; }
  .place-pair input { width: 100%; }
  .place-pair span { color: var(--muted); }
  .modal-actions { display: flex; justify-content: flex-end; gap: .6rem; margin-top: 1.1rem; }
  .modal-actions button { font-family: var(--display); text-transform: uppercase; letter-spacing: .05em; font-size: .85rem; padding: .55rem 1.1rem; border-radius: 2px; cursor: pointer; border: 2px solid var(--ink); }
  .modal-actions .save { background: var(--ink); color: var(--paper); }
  .modal-actions .cancel { background: transparent; color: var(--ink); }

  @media (max-width: 680px) { .hide-sm { display: none; } .grid3 { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="wrap">
  <div class="controls">
    <div class="seg" id="runnerSeg">
      <button data-runner="All" class="active">All</button>
      <button data-runner="Steve">Steve</button>
      <button data-runner="Kelly">Kelly</button>
    </div>
    <select id="yearSel"><option value="">All years</option></select>
    <input type="search" id="search" placeholder="Search race or place…">
    <button id="addBtn" class="btn-add" type="button">+ Add race</button>
  </div>

  <div class="banner" id="banner" hidden></div>

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

<div class="overlay" id="overlay">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
    <h2 id="modalTitle">Add a race</h2>
    <p class="hint">Saved to this browser instantly. To publish it to the live site for good, use the box that appears after saving.</p>
    <form id="addForm">
      <div class="grid2">
        <div class="field">
          <label>Runner</label>
          <select name="runner"><option>Steve</option><option>Kelly</option></select>
        </div>
        <div class="field">
          <label>Date</label>
          <input type="date" name="date" required>
        </div>
      </div>
      <div class="field">
        <label>Race name</label>
        <input name="name" required placeholder="e.g. Cooper River Bridge Run">
      </div>
      <div class="field">
        <label>Location</label>
        <input name="location" placeholder="e.g. Chicago, IL, USA">
      </div>
      <div class="grid2">
        <div class="field">
          <label>Finish time</label>
          <input name="final_time" required placeholder="1:53:19 or 29:08">
        </div>
        <div class="field">
          <label>Pace (min/mi)</label>
          <input name="pace" placeholder="9:30">
        </div>
      </div>
      <div class="grid3">
        <div class="field"><label>Overall</label><div class="place-pair"><input name="overall_place" type="number" min="1" placeholder="place"><span>/</span><input name="overall_total" type="number" min="1" placeholder="field"></div></div>
        <div class="field"><label>Gender</label><div class="place-pair"><input name="gender_place" type="number" min="1" placeholder="place"><span>/</span><input name="gender_total" type="number" min="1" placeholder="field"></div></div>
        <div class="field"><label>Division</label><div class="place-pair"><input name="division_place" type="number" min="1" placeholder="place"><span>/</span><input name="division_total" type="number" min="1" placeholder="field"></div></div>
      </div>
      <div class="modal-actions">
        <button type="button" class="cancel" id="cancelBtn">Cancel</button>
        <button type="submit" class="save">Save race</button>
      </div>
    </form>
  </div>
</div>

<script>
const BASE = __DATA__;
const LS_KEY = "baronRaceLog.local.v1";

function loadLocal() { try { return JSON.parse(localStorage.getItem(LS_KEY)) || []; } catch (e) { return []; } }
function saveLocal(list) { localStorage.setItem(LS_KEY, JSON.stringify(list)); }
let local = loadLocal();
const allRaces = () => BASE.concat(local);

const state = { runner: "All", year: "", search: "", sortKey: "date", sortDir: -1 };

function pct(p, t) { return (p && t) ? Math.round(p / t * 100) : null; }
function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function parseMinutes(t) { const p = String(t).split(":").map(Number); let h, m, s; if (p.length === 3) { [h, m, s] = p; } else { h = 0; [m, s] = p; } return h * 60 + m + (s || 0) / 60; }
function paceMinutes(p) { const a = String(p).split(":").map(Number); return a[0] + (a[1] || 0) / 60; }
function classify(pace, time) {
  if (!pace || !time) return "Other";
  const d = parseMinutes(time) / paceMinutes(pace);
  if (!isFinite(d) || d <= 0) return "Other";
  if (d >= 24 && d <= 28) return "Full";
  if (d >= 12 && d <= 14.5) return "Half";
  return "Other";
}

function rankCell(p, t) {
  if (!p || !t) return '<span class="muted mono">&mdash;</span>';
  const beat = 100 - pct(p, t);              // % of the field finished behind
  return `<div class="rank">
    <span class="rank-txt">${p.toLocaleString()} / ${t.toLocaleString()}</span>
    <span class="rank-bar"><i style="width:${beat}%"></i></span>
  </div>`;
}

function filtered() {
  return allRaces().filter(r => {
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
  const marathons = rows.filter(r => r.kind === "Full").length;
  const halfs = rows.filter(r => r.kind === "Half").length;
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
  document.getElementById("rows").innerHTML = rows.map(r => `
    <tr>
      <td><span class="bib ${r.runner}">${esc(r.runner)}</span></td>
      <td class="mono muted">${esc(r.date)}</td>
      <td class="race-name">${esc(r.name)}${r._local ? '<span class="tag-local">unsaved</span>' : ""}</td>
      <td class="hide-sm muted">${esc(r.location)}</td>
      <td class="time">${esc(r.final_time)}</td>
      <td class="hide-sm mono muted">${r.pace ? esc(r.pace) : "&mdash;"}</td>
      <td>${rankCell(r.overall_place, r.overall_total)}</td>
    </tr>`).join("");
  document.getElementById("count").textContent = `${rows.length} race${rows.length === 1 ? "" : "s"} shown`;
}

const yearSel = document.getElementById("yearSel");
function refreshYears() {
  const cur = yearSel.value;
  const ys = [...new Set(allRaces().map(r => r.date.slice(0, 4)))].sort().reverse();
  yearSel.innerHTML = '<option value="">All years</option>' + ys.map(y => `<option value="${y}">${y}</option>`).join("");
  yearSel.value = cur;
}

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

// --- Add a race (stored in this browser; publish via the banner) ---
const overlay = document.getElementById("overlay");
const openModal = () => overlay.classList.add("open");
const closeModal = () => { overlay.classList.remove("open"); document.getElementById("addForm").reset(); };
document.getElementById("addBtn").addEventListener("click", openModal);
document.getElementById("cancelBtn").addEventListener("click", closeModal);
overlay.addEventListener("click", e => { if (e.target === overlay) closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

function qarg(s) { return '"' + String(s).replace(/"/g, '\\"') + '"'; }
function cliCommand(r) {
  const p = ["python3 races.py add", "--runner " + r.runner, "--name " + qarg(r.name), "--date " + r.date];
  if (r.location) p.push("--location " + qarg(r.location));
  p.push("--time " + r.final_time);
  if (r.pace) p.push("--pace " + r.pace);
  if (r.overall_place && r.overall_total) p.push("--overall " + qarg(r.overall_place + " of " + r.overall_total));
  if (r.gender_place && r.gender_total) p.push("--gender " + qarg(r.gender_place + " of " + r.gender_total));
  if (r.division_place && r.division_total) p.push("--division " + qarg(r.division_place + " of " + r.division_total));
  return p.join(" ");
}

function renderBanner() {
  const b = document.getElementById("banner");
  if (!local.length) { b.hidden = true; b.innerHTML = ""; return; }
  b.hidden = false;
  const cmds = local.map(cliCommand).join("\n");
  b.innerHTML =
    `<h3>${local.length} unsaved race${local.length === 1 ? "" : "s"} &mdash; saved only in this browser</h3>` +
    `<p>They show in the table below on this device only. To publish them to the live site permanently, send these lines to Claude, or run them inside the <code>race-tracker</code> folder:</p>` +
    `<textarea readonly>${esc(cmds)}</textarea>` +
    `<div class="row"><button id="copyCmds" type="button">Copy commands</button>` +
    `<button id="clearLocal" class="ghost" type="button">Remove unsaved races</button></div>`;
  document.getElementById("copyCmds").addEventListener("click", () => {
    navigator.clipboard.writeText(cmds).then(() => {
      const x = document.getElementById("copyCmds"); x.textContent = "Copied!";
      setTimeout(() => { x.textContent = "Copy commands"; }, 1500);
    });
  });
  document.getElementById("clearLocal").addEventListener("click", () => {
    if (confirm("Remove your unsaved races from this browser? Anything already published stays.")) {
      local = []; saveLocal(local); refreshYears(); renderBanner(); render();
    }
  });
}

document.getElementById("addForm").addEventListener("submit", e => {
  e.preventDefault();
  const f = new FormData(e.target);
  const g = k => { const v = (f.get(k) || "").toString().trim(); return v === "" ? null : v; };
  const gi = k => { const v = g(k); return v === null ? null : parseInt(v.replace(/,/g, ""), 10); };
  const rec = {
    runner: g("runner") || "Steve",
    name: g("name"), date: g("date"), location: g("location") || "",
    overall_place: gi("overall_place"), overall_total: gi("overall_total"),
    gender_place: gi("gender_place"), gender_total: gi("gender_total"),
    division_place: gi("division_place"), division_total: gi("division_total"),
    pace: g("pace"), final_time: g("final_time"), _local: true
  };
  rec.kind = classify(rec.pace, rec.final_time);
  local.push(rec); saveLocal(local);
  refreshYears(); renderBanner(); render();
  closeModal();
});

refreshYears();
renderBanner();
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
