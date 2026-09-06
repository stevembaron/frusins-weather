# OnTheSnow TV — live cams page (prototype)

Static prototype of a generic live-cameras page carrying the OnTheSnow TV
rotating channel. No build step, no dependencies.

## Viewing it

Open `index.html` directly, or serve the directory:

    python3 -m http.server 8000 --directory onthesnow-tv

Then http://localhost:8000/.

## Publishing

This repo already publishes to GitHub Pages: `.github/workflows/deploy-pages.yml`
uploads the repository root on every push to `main`. So merging this directory
to `main` puts the prototype at

    https://stevembaron.github.io/projects/onthesnow-tv/

with no further setup. All asset paths are relative, so it works from that
subdirectory as-is.

**stevembaron/projects is a public repo.** See the visibility note below before
merging to `main`.

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
