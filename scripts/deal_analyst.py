#!/usr/bin/env python3
"""Deal analyst: turn scraped deal data into a judgment-based morning brief.

The deal monitor (scripts/deal_monitor.py) collects and ranks raw listings by
rules. This script does the part rules can't: it sends the day's deals, their
price history, and your preferences to Claude and asks for actual judgment —
is this a real discount, does it fit, is it worth acting on today — then
writes a short markdown brief.

Usage:
    python3 scripts/deal_analyst.py             # write data/deal_brief.md
    python3 scripts/deal_analyst.py --dry-run   # show the assembled prompt, no API call

Requires the `anthropic` package and an ANTHROPIC_API_KEY environment variable
(only for the live call — `--dry-run` works without either).
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SKI_DEALS = DATA_DIR / "deals.json"
CLOTHING_DEALS = DATA_DIR / "clothing_deals.json"
PREFERENCES = ROOT / "config" / "deal_preferences.json"
BRIEF_OUTPUT = DATA_DIR / "deal_brief.md"
BRIEF_ARCHIVE_DIR = DATA_DIR / "briefs"
WEB_BRIEF_OUTPUT = ROOT / "deal-brief" / "index.html"

MODEL = "claude-fable-5"
MAX_OUTPUT_TOKENS = 8000

SYSTEM_PROMPT = """\
You are a personal gear-deal analyst for one household. Each morning you receive
the day's scraped ski and clothing deals (with per-item price history) plus the
owner's preferences, and you produce a short brief of what is actually worth
acting on.

Apply real judgment, not keyword matching:

- Question the discount. A large percent off an inflated MSRP is not a deal.
  Use the 90-day low/high and trend data: a price at or near its tracked low is
  meaningful; a "40% off" that has sat at the same price for weeks is not news.
- Check fit. Ski lengths must match the owner's sizes (or family sizes — say
  which). Clothing must match the listed clothing sizes. If size data is
  missing, say so rather than assuming.
- Spot model-year closeouts. Last season's model at a deep discount can be a
  great buy — flag it as such, but note when a listing looks like an old model
  at an unimpressive price.
- Weigh urgency honestly. "New low + in stock + watch-term brand" is act-now.
  A small price wiggle on something plentiful is not.
- Respect the budget caps and muted terms in the preferences.

Output format (markdown):

1. `# Gear brief — <date>`
2. `## Act now` — at most 3 items. For each: a one-line verdict with the price,
   why it's actually good (cite price history), the size situation, and the
   link. If nothing clears the bar, write exactly one line saying so.
3. `## Worth watching` — at most 5 items, one line each, with what would change
   your verdict (e.g. "buy if it drops below $300").
4. `## Notes` — only if needed: data problems (failed sources, stale/cached
   data), or a watch-term item that disappeared.

Keep the whole brief under ~350 words. Do not pad. Do not restate the input.
An empty "Act now" section on a quiet day is the correct answer, not a failure.
"""


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def fmt_price(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "?"


def deal_line(deal: dict[str, Any], category: str) -> str:
    parts = [f"[{category}] {deal.get('title', 'Untitled')}", fmt_price(deal.get("current_price"))]

    original = deal.get("original_price")
    discount = deal.get("discount_percent")
    if original:
        label = f"was {fmt_price(original)}"
        if discount:
            label += f", {discount:.0f}% off"
        parts.append(label)

    sizes = deal.get("sizes")
    if sizes:
        parts.append("sizes " + ", ".join(str(s) for s in sizes))

    stock = deal.get("stock_status")
    if stock:
        parts.append(stock.replace("_", " "))

    trend = deal.get("price_trend")
    change = deal.get("price_change")
    if trend in ("up", "down") and change is not None:
        parts.append(f"{trend} {fmt_price(abs(change))} vs prior day")
    elif trend == "new":
        parts.append("newly tracked")

    lowest, highest = deal.get("lowest_price"), deal.get("highest_price")
    if lowest is not None and highest is not None and lowest != highest:
        parts.append(f"90d range {fmt_price(lowest)}-{fmt_price(highest)}")

    first_seen = str(deal.get("first_seen_at") or "")[:10]
    if first_seen:
        parts.append(f"first seen {first_seen}")

    if deal.get("is_cached"):
        parts.append("CACHED (source failed today, price may be stale)")

    parts.append(str(deal.get("source", "")))
    parts.append(str(deal.get("url", "")))
    return "- " + " | ".join(parts)


def build_user_prompt(max_deals_per_category: int) -> tuple[str, dict[str, int]]:
    sections: list[str] = []
    stats = {"ski": 0, "clothing": 0, "errors": 0}

    preferences = load_json(PREFERENCES) or {}
    sections.append("## Owner preferences\n```json\n" + json.dumps(preferences, indent=2) + "\n```")

    for label, path in (("ski", SKI_DEALS), ("clothing", CLOTHING_DEALS)):
        payload = load_json(path)
        if not payload:
            sections.append(f"## {label.title()} deals\n(no data file — monitor has not run)")
            continue

        deals = payload.get("deals", [])[:max_deals_per_category]
        stats[label] = len(deals)
        lines = [deal_line(deal, label) for deal in deals]
        generated = payload.get("generated_at", "unknown")
        sections.append(
            f"## {label.title()} deals (scraped {generated}, {len(deals)} shown)\n" + "\n".join(lines)
        )

        errors = payload.get("errors", [])
        if errors:
            stats["errors"] += len(errors)
            error_lines = [
                f"- {error.get('source')}: {error.get('error')}" for error in errors if isinstance(error, dict)
            ]
            sections.append(f"## {label.title()} source failures today\n" + "\n".join(error_lines))

        disappeared = payload.get("disappeared_deals", [])
        if disappeared:
            gone_lines = [
                f"- {item.get('title')} ({fmt_price(item.get('current_price'))}, last seen {str(item.get('last_seen_at',''))[:10]}, {item.get('source')})"
                for item in disappeared
                if isinstance(item, dict)
            ]
            sections.append(f"## Recently disappeared {label} listings\n" + "\n".join(gone_lines))

    today = datetime.now().astimezone().strftime("%A, %B %-d, %Y")
    header = f"Today is {today}. Write the morning gear brief from the data below.\n"
    return header + "\n\n".join(sections), stats


def run_analysis(user_prompt: str) -> str:
    try:
        import anthropic
    except ImportError:
        sys.exit("The 'anthropic' package is required for a live run: pip install anthropic")

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
        print()
        message = stream.get_final_message()

    return "".join(block.text for block in message.content if block.type == "text").strip()


def write_brief(brief: str) -> None:
    BRIEF_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    BRIEF_OUTPUT.write_text(brief + "\n", encoding="utf-8")
    BRIEF_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive = BRIEF_ARCHIVE_DIR / f"{datetime.now().astimezone():%Y-%m-%d}.md"
    archive.write_text(brief + "\n", encoding="utf-8")
    WEB_BRIEF_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    WEB_BRIEF_OUTPUT.write_text(render_brief_html(brief), encoding="utf-8")
    print(f"\nWrote {BRIEF_OUTPUT}")
    print(f"Wrote {archive}")
    print(f"Wrote {WEB_BRIEF_OUTPUT}")


INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
BARE_URL_RE = re.compile(r'(?<!["(>])(https?://[^\s<,]+)')
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def markdown_inline(value: str) -> str:
    value = html.escape(value, quote=False)
    value = INLINE_LINK_RE.sub(r'<a href="\2">\1</a>', value)
    value = BARE_URL_RE.sub(r'<a href="\1">\1</a>', value)
    return BOLD_RE.sub(r"<strong>\1</strong>", value)


def markdown_to_html(markdown: str) -> str:
    """Render the brief's constrained markdown (headings, lists, links, bold)."""
    blocks: list[str] = []
    list_items: list[str] = []

    def flush_list() -> None:
        if list_items:
            blocks.append("<ul>\n" + "\n".join(list_items) + "\n</ul>")
            list_items.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading:
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{markdown_inline(heading.group(2))}</h{level}>")
        elif stripped.startswith(("- ", "* ")):
            list_items.append(f"  <li>{markdown_inline(stripped[2:])}</li>")
        else:
            flush_list()
            blocks.append(f"<p>{markdown_inline(stripped)}</p>")
    flush_list()
    return "\n".join(blocks)


def render_brief_html(brief: str) -> str:
    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Gear brief</title>
  <style>
    :root {{ --ink: #232a31; --soft: #5d6a76; --line: #dce3e9; --accent: #1f6f43; }}
    body {{ margin: 0; padding: 24px 16px 48px; background: #f4f6f8; color: var(--ink);
           font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    main {{ max-width: 720px; margin: 0 auto; background: #fff; border: 1px solid var(--line);
            border-radius: 14px; padding: 26px 28px; }}
    h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
    h2 {{ font-size: 1.05rem; margin: 22px 0 8px; color: var(--accent); text-transform: uppercase;
          letter-spacing: 0.04em; border-bottom: 1px solid var(--line); padding-bottom: 4px; }}
    ul {{ margin: 0; padding-left: 20px; }}
    li {{ margin: 8px 0; }}
    a {{ color: var(--accent); }}
    .meta {{ color: var(--soft); font-size: 0.85rem; margin-top: 26px; }}
  </style>
</head>
<body>
  <main>
{markdown_to_html(brief)}
    <p class="meta">Generated {generated} by scripts/deal_analyst.py ({MODEL}). <a href="../ski-deals/">Full deal table</a></p>
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="print the assembled prompt and exit without calling the API")
    parser.add_argument("--max-deals", type=int, default=120, help="max deals per category to include (default: 120)")
    parser.add_argument(
        "--render-only",
        metavar="BRIEF_MD",
        help="skip analysis; render an existing brief markdown file to all outputs (used by CI, where Claude Code writes the brief)",
    )
    args = parser.parse_args()

    if args.render_only:
        brief = Path(args.render_only).read_text(encoding="utf-8").strip()
        if not brief:
            sys.exit(f"{args.render_only} is empty; not writing output.")
        write_brief(brief)
        return

    user_prompt, stats = build_user_prompt(args.max_deals)

    if args.dry_run:
        print(user_prompt)
        print(
            f"\n--- dry run: {stats['ski']} ski deals, {stats['clothing']} clothing deals, "
            f"{stats['errors']} source errors, ~{len(user_prompt) // 4} input tokens ---",
            file=sys.stderr,
        )
        return

    if stats["ski"] == 0 and stats["clothing"] == 0:
        sys.exit("No deal data found. Run `make deals` / `make clothing-deals` first.")

    brief = run_analysis(user_prompt)
    if not brief:
        sys.exit("Model returned an empty brief; not writing output.")
    write_brief(brief)


if __name__ == "__main__":
    main()
