# External Daily Deal Scheduler

This scheduler is the external alarm clock for the daily deal reports. It uses Cloudflare Workers Cron to trigger the GitHub workflow `External Daily Deal Refresh`, which refreshes both ski and clothing reports and publishes them to GitHub Pages.

GitHub's own scheduled workflow events are best-effort and have missed morning runs. This external trigger keeps GitHub Pages as the host, but moves the daily wake-up trigger outside GitHub Actions.

## One-time setup

1. Create a GitHub fine-grained personal access token for `stevembaron/projects` with `Contents: Read and write`.
2. Install and log in to Wrangler:

```sh
npm install -g wrangler
wrangler login
```

3. Copy the example config and add the GitHub token as a secret:

```sh
cd external-scheduler
cp wrangler.toml.example wrangler.toml
wrangler secret put GITHUB_TOKEN
```

4. Deploy the worker:

```sh
wrangler deploy
```

The default cron is `5 12 * * *`, which runs at 12:05 UTC. That is 6:05 AM MDT during daylight saving time and 5:05 AM MST during standard time.

## Manual test

After deploy, open the Worker logs in Cloudflare or run:

```sh
wrangler tail
```

Then use Cloudflare's dashboard to trigger a test scheduled event, or temporarily add a `DISPATCH_SECRET` secret and POST to `/dispatch`:

```sh
wrangler secret put DISPATCH_SECRET
curl -X POST "https://<worker-subdomain>.workers.dev/dispatch" \
  -H "x-dispatch-secret: <same-secret>"
```

The GitHub Actions run should appear under `External Daily Deal Refresh`.
