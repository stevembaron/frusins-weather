# Spanish 2 Progress Tracker

A single-page calculator for tracking a student's progress through BYU Independent
Study **Spanish 2** (two courses, 15 modules each) and seeing whether she's on pace
to finish by a deadline.

The two courses:

- **Part 1 — SPAN 2A** ([SPAN-051](https://is.byu.edu/catalog/course/SPAN-051/lbg:10000291))
- **Part 2 — SPAN 2B** ([SPAN-043](https://is.byu.edu/catalog/course/SPAN-043/lbg:10000394))

## What it does

- **Check off modules** with three states — not started → in progress → done — so a
  half-finished module counts as half.
- **Live snapshot**: modules done, modules left, days to the goal date, and the pace
  (modules/week) she needs to keep.
- **Headline banner** that turns green / amber / red based on how demanding that pace is.
- **What-if calculator**: enter how many modules per week she can realistically do and it
  projects her finish date, then tells her if she beats the goal (and what pace she'd need
  if not).
- **Withdrawal-deadline countdown** so the drop decision doesn't sneak up.
- **Saves automatically** in the browser via `localStorage`. **Export / import** JSON to
  sync between a phone and a laptop.

## Defaults (edit anytime)

- Seeded to her real position: Part 1 Modules 1–5 done, Module 6 in progress.
- Goal date: **Aug 14, 2026** · Withdrawal deadline: **Jul 29, 2026**.

## Usage

Open `index.html` in any browser — no build step, no internet needed. It also serves from
the GitHub Pages site at `/spanish-tracker/` once merged to `main`.

## Files

- `index.html` — the whole app (markup, styles, and vanilla JS inlined, so the file is
  self-contained and easy to share or double-click).
