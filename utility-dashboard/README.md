# Home Utility Dashboard

Tracks water, electricity, and natural gas for the house — usage and spend on one page.
Static site (vanilla JS, no build step), same pattern as the other apps in this repo.

## What's on the page

- **KPI tiles** — latest month's total spend and per-utility usage, each with a
  year-over-year delta and a 12-month sparkline.
- **Monthly spend** — stacked columns (water / gas / electricity) per month, with an
  editable monthly target line (defaults to the trailing-12-month average, saved in
  the browser via `localStorage`) and an over/under count for past and projected months.
- **Usage per utility** — monthly columns for cubic feet, kWh, and Dth.
- **Year over year** — usage by calendar month with the current year highlighted
  against prior years.
- **Temperature correlation** — monthly kWh and Dth scattered against average
  temperature (gas borrows the electric bill's average temperature for the month).
- **Daily electricity** — the most recent 30 days of daily readings.
- **Projections** — the current month plus five more, shown as lighter bars on the
  spend/usage charts, a KPI tile, and a summary table.
- Every chart has hover/focus tooltips and a "View data" table underneath.
- The date-range filter (12 / 24 months / all) scopes everything except the
  daily-electricity card, which always shows the latest 30 days.

## Data

All data lives in `data.js` (`window.UTILITY_DATA`), generated from utility exports by
`tools/parse_data.js`. Raw exports are **not** committed — they contain the street
address and account numbers; `data.js` keeps only dates, usage, and dollars.

| Utility | Source | Coverage | Notes |
|---|---|---|---|
| Water | SLC Public Utilities bill export | Dec 2021 – Jun 2026 | Usage in cubic feet + full charge breakdown. Consumption month = the month the service period starts (periods run ~2nd–1st). |
| Electricity | Rocky Mountain Power exports | Jun 2024 – Jun 2026 monthly, plus last 30 days daily | Monthly file is billing truth; daily costs are the utility's rounded estimates. |
| Gas | Dominion Energy usage history + account ledger | Aug 2023 – Jul 2026 reads | Usage in Dth (actual + weather-adjusted). Costs joined from the ledger's "Billed Charges" rows by nearest bill date. Consumption month = month containing the period midpoint (the export has end dates only). |

### Known data quirks

- The water meter was replaced around April 2024 (reading drops from 7,695 to 10), so
  consumption comes from the bill's consumption column, never from reading deltas.
- June 2025 gas usage (36.1 Dth) is an outlier for that time of year; it is plotted as
  reported.
- Combined-spend bars before Jun 2024 are missing electricity (and before Aug 2023,
  gas); tooltips say "no data" for the missing utility in those months.

## How projections work

Computed at render time in `app.js` from the data itself — nothing extra to maintain.

- **Seasonal baseline (all utilities, future months):** same month last year, scaled by
  a trend factor — the last three actual months divided by the same three months a year
  earlier, clamped to 0.7–1.4. Usage and cost get separate factors.
- **Current-month electricity nowcast:** actual daily kWh month-to-date, plus the
  remaining days at the average of (a) the trailing 7-day daily rate and (b) last
  year's daily rate for this month adjusted by the usage trend factor. Cost applies
  last year's effective $/kWh for the month, adjusted by the cost trend.
- Water and gas have no daily feed, so their current month is the seasonal baseline.
- Projected marks are drawn at 40% opacity and labeled "(proj.)" in tables and
  "— projected" in tooltips, so they never pass for actuals.

## Updating the data

1. Download fresh exports (same formats as above) into one folder.
2. If there are new gas bills, add them to the `gasBills` table at the top of
   `tools/parse_data.js` (date + billed amount from the Dominion ledger).
3. Run `node tools/parse_data.js <exportFolder> data.js` — files are recognized by
   their header row, not their filename.
4. Reload the page.

## Files

- `index.html` — markup
- `styles.css` — styling (light + dark via `prefers-color-scheme`)
- `app.js` — chart rendering (SVG, no dependencies)
- `data.js` — generated data
- `tools/parse_data.js` — export parser / `data.js` generator
