# OnTheSnow TV — live cams page (prototype)

Static prototype of a generic live-cameras page carrying the OnTheSnow TV
rotating channel. No build step, no dependencies.

## Viewing it

The current build is published as a private Claude artifact, which is how this
gets reviewed:

    https://claude.ai/code/artifact/e49d5611-6775-492f-a310-04afb5117982

That page is self-contained — the channel video and camera stills are embedded
in it — and it is a snapshot, so it does not track edits made here. It is
private to the owner's account and shares by invitation from the page's share
menu, rather than by public URL.

To work on the page itself, open `index.html` directly or serve the directory:

    python3 -m http.server 8000 --directory ots

Then http://localhost:8000/.

## Publishing

Deliberately not published to the web. This directory lives on a branch and
should stay off `main`: `.github/workflows/deploy-pages.yml` uploads the whole
repository root to GitHub Pages on every push to `main`, and
**stevembaron/projects is a public repo**, so merging it would put the brand
assets at a crawlable URL. See the last note below.

## Contents

    index.html            the page
    assets/channel.mp4    72s: 2.6s concept card + 7 cameras at 10s (1280x720)
    assets/poster.jpg     video poster frame
    assets/thumb_*.jpg    camera thumbnails
    assets/onthesnow-logo.png

## Notes

- Webcam frames were captured in September, so the mountains are green.
- Conditions values in the video overlay are placeholder, not live data.
- Granite Peak and Appalachian carry the resort's own burned-in branding;
  the overlay is positioned per-camera to work around it.
- The video has no audio track. A real YouTube Live ingest needs one.
- This is a private prototype using OnTheSnow brand assets. It should not be
  publicly reachable until the brand team has signed off — keep it on a branch,
  or move it to a private repo, rather than merging it to `main` where the Pages
  workflow will publish it.
