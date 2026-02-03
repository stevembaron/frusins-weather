# Frusins Weather

A modern, light-themed weather dashboard for four saved locations, powered by Open-Meteo (no API key required).

## Features

- Primary location picker with saved default (`localStorage`)
- Live current conditions for all four locations
- 5-day forecast cards for the selected primary location
- Side-by-side comparison cards across all locations
- 24-hour temperature comparison chart
- 24-hour precipitation timeline for the primary location

## Run locally

This is a static web app.

1. Open `index.html` directly in your browser, or
2. Serve the folder with any static server (example):

```bash
python3 -m http.server 8080
```

Then visit `http://localhost:8080`.

## Deploy

This repo includes a GitHub Actions workflow that deploys the site to GitHub Pages on every push to `main`.

