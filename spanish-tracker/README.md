# Spanish 2 Progress Tracker

A single-page calculator for tracking Molly's progress through the remaining BYU
Independent Study Spanish course and seeing whether she's on pace to finish by a deadline.

- **Second-Year Spanish, Part 2 — SPAN 2B** ([SPAN-043](https://is.byu.edu/catalog/course/SPAN-043/lbg:10000394)) — tracked by **lesson** (16 modules → 47 lessons).

Part 1 (SPAN 2A) is complete and no longer tracked here.

## What it does

- **Check lessons off** with three states — not started → in progress → done — so a
  half-finished lesson counts as half. Each lesson shows badges for its graded work,
  with **100-point Speaking/Writing Tests, the Final Speaking Test, and the proctored
  Final Exam flagged (⚑)** so the high-stakes pieces can't be missed.
- **Live snapshot**: lessons done, lessons left, days to the goal date, and the pace Molly
  needs to keep.
- **On track? (real pace)**: as she checks lessons off, it logs the date and projects her
  finish from her *actual* pace, compares it to the goal, and flags a stall if nothing's been
  completed in a week.
- **Headline banner** that turns green / amber / red based on how demanding that pace is.
- **What-if calculator**: enter how many lessons per week Molly can realistically do and it
  projects her finish date, then tells you whether she beats the goal (and what pace she'd
  need if not).
- **Big goal countdown** front-and-center, a **day-streak counter** that rewards steady
  work, and a **confetti burst** when she completes a flagged milestone (a Speaking/Writing
  Test or the Final Exam).
- **Withdrawal-deadline countdown** so the drop decision doesn't sneak up.
- **Saves automatically** in the browser via `localStorage`. **Export / import** JSON to
  sync between a phone and a laptop.

## Defaults (edit anytime)

- Seeded to Molly's real position: **Part 2 through Module 3, Lesson 1 done, Module 3
  Lesson 2 in progress**.
- Goal date: **Aug 14, 2026** · Withdrawal deadline: **Jul 29, 2026**.

## Usage

Open `index.html` in any browser — no build step, no internet needed. It also serves from
the GitHub Pages site at `/spanish-tracker/` once merged to `main`.

## Files

- `index.html` — the whole app (markup, styles, and vanilla JS inlined, so the file is
  self-contained and easy to share or double-click).
