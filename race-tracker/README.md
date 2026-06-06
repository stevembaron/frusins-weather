# Race Tracker

A running-race log for Steve & Kelly. All data lives in **`races.json`** (the
single source of truth). The website **`index.html`** is generated from it and
published via GitHub Pages at:

**https://stevembaron.github.io/projects/race-tracker/**

## Adding a race

Run the `add` command. The website rebuilds automatically.

**Quick (one line):**

```bash
python3 races.py add \
  --runner Kelly \
  --name "Some 10K" \
  --date 2025-05-10 \
  --location "Salt Lake City, UT, USA" \
  --time 52:30 \
  --pace 8:27 \
  --overall "120 of 800" \
  --gender "40 of 410" \
  --division "6 of 70"
```

Only `--name`, `--date`, and `--time` are required. `--runner` defaults to Steve.

**Interactive (it prompts you):**

```bash
python3 races.py add
```

After adding, commit and push to publish:

```bash
git add races.json index.html && git commit -m "Add race" && git push
```

…or just tell Claude "add this race: …" and it'll do all of the above.

## Other commands

```bash
python3 races.py list                  # all races
python3 races.py list -r Kelly -y 2009 # filter by runner / year
python3 races.py list -s marathon      # search name or location
python3 races.py stats                 # per-runner summary
python3 races.py delete                # pick a race to remove
python3 build_site.py                  # rebuild the website by hand
```

## How it fits together

- `races.json` — the data (edit via the CLI, committed to git)
- `races.py` — command-line tool to add/list/delete/summarize
- `build_site.py` — turns `races.json` into `index.html`
- `index.html` — the published website (auto-generated; don't edit by hand)

Marathon vs. half-marathon counts on the site are derived from each race's
actual distance (finish time ÷ pace), not the race name, since names are
unreliable.
