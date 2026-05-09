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
