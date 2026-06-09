# Deal Monitor

This project includes a local deal monitor that can check retailer URLs for deal pages without API access.

## How It Works

- Add retailer category, sale, search, or product URLs to a config file in `config/`.
- Run `python3 scripts/deal_monitor.py` for skis or `python3 scripts/deal_monitor.py --config config/clothing_deal_sources.json` for clothing.
- Open `data/deals.html` or `data/clothing_deals.html` for a readable report.
- Open `ski-deals/index.html` or `clothing-deals/index.html` for the web-published version.
- Check `data/deal_report.md` or `data/clothing_deal_report.md` for a compact summary.
- Check the matching `*.json` output if you want raw structured output later.

The monitor looks for product metadata and linked text with prices, filters by the configured keywords, ranks the best-looking deals, and writes a daily report.

Sierra and evo block plain automated requests, so their configured sources use a reader fallback. The script still tries the retailer URL first, then falls back to a readable copy of the page and parses product links/prices from that.

Evo has an extra fallback: its product search runs on the public Constructor.io API, and the script caches the API key (`data/evo_constructor_key.json`) every time a page fetch succeeds. When evo's page returns a 403, the monitor queries the search API directly with the cached key instead, so results keep flowing even while the HTML page is blocked. You can also pin a key manually with a `"constructor_key"` field on the evo source in `config/deal_sources.json` (view source on any evo page and search for `constructor_index_key`).

## Add URLs

Edit a config such as `config/deal_sources.json` or `config/clothing_deal_sources.json` and add sources like this:

```json
{
  "name": "Retailer deal page",
  "url": "https://retailer.example/deals",
  "enabled": true
}
```

Good URLs are usually sale pages, clearance pages, category pages, brand searches, or individual product pages.

## Tune Results

- `keywords`: gear terms to keep.
- `exclude_keywords`: terms to ignore.
- `min_discount_percent`: minimum discount when the page exposes both original and sale price.
- `max_results_per_source`: cap noisy sources.

Some sites render prices with JavaScript after the page loads or block automated requests. Those may need a site-specific selector or a browser-based scraper later.

## Daily Use

From Terminal, run either:

```bash
make deals
make clothing-deals
```

or:

```bash
python3 scripts/deal_monitor.py
python3 scripts/deal_monitor.py --config config/clothing_deal_sources.json
```

For the easiest Mac workflow, double-click `Run Ski Deals.command` or `Run Clothing Deals.command`. Each runs the monitor and opens the matching HTML report.

## Deal Analyst (Claude brief)

After the monitors run, `make brief` sends the day's deals, their price history, and `config/deal_preferences.json` to Claude (`claude-fable-5`) and writes a short judgment-based morning brief — what's actually worth buying today, what to watch, and why (real lows vs inflated MSRPs, size fit, model-year closeouts).

```bash
pip install anthropic           # one-time
export ANTHROPIC_API_KEY=...    # or put it in your shell profile
make deals clothing-deals       # refresh data first
make brief                      # writes data/deal_brief.md + data/briefs/YYYY-MM-DD.md
```

Use `python3 scripts/deal_analyst.py --dry-run` to inspect exactly what gets sent without making an API call. The brief is intentionally honest: on a quiet day the "Act now" section says there's nothing worth acting on.

### Automated daily brief

The `External Daily Deal Refresh` workflow generates the brief automatically after each scheduled scrape using Claude Code billed against a Claude subscription — no per-call API charges. One-time setup:

1. Run `claude setup-token` anywhere you're logged in to Claude Code (requires a Pro/Max subscription) and copy the OAuth token it prints.
2. Add it as a repository secret named `CLAUDE_CODE_OAUTH_TOKEN` (GitHub repo → Settings → Secrets and variables → Actions → New repository secret).

The brief steps are best-effort — if the secret is missing or the run fails, the deal reports still publish normally. In CI, Claude Code reads the same prompt `--dry-run` produces, writes the brief, and hands it to `scripts/deal_analyst.py --render-only` for the markdown/HTML outputs. (The script's direct-API mode still exists for local use with an `ANTHROPIC_API_KEY`, but nothing in automation depends on it.)

The workflow commits the markdown plus a web version, published at:

```text
https://stevembaron.github.io/projects/deal-brief/
```

## Reports

The HTML report is sorted from lowest price to highest price:

```text
data/deals.html
data/clothing_deals.html
```

The same pages are also written to the static web app paths:

```text
ski-deals/index.html
clothing-deals/index.html
```

After committing and pushing to `main`, they will be available at:

```text
https://stevembaron.github.io/projects/ski-deals/
https://stevembaron.github.io/projects/clothing-deals/
```
