# Pool Days Tracker

Log every day you swim and capture that day's weather, so you can spot trends across the season.

## Features

- **Log a pool day** with the date and an optional note. Duplicate dates are blocked.
- **Automatic weather** for each logged day from [Open-Meteo](https://open-meteo.com/) (no API key): daily high/low temperature, conditions, and rainfall.
- **Trends**: season stats (total days, average high, warmest day, rainy days), pool days by month, and daily high temperature per pool day.
- **Season filter** to view a single year or all seasons.
- **Persistent storage** in the browser via `localStorage`.
- **Backup**: export your log to JSON and import it on another device — that's how you keep your phone and laptop in sync, since a static GitHub Pages site has no shared backend.

## Weather location

Defaults to the Perrys Hollow / Salt Lake City area (`40.78, -111.83`). Change it in
**Settings & backup** by entering `latitude, longitude`. New days use the saved location;
press ↻ on an existing day to refetch its weather.

## Files

- `index.html` — markup
- `styles.css` — styling
- `app.js` — logging, storage, weather, and charts (vanilla JS, no build step)

Part of the GitHub Pages site; lives in its own folder so it can't collide with other apps.
