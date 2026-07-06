# JWST-VENUS.github.io

Public website of the JWST VENUS Treasury survey: https://jwst-venus.github.io/

## Structure

- `index.html` - landing page (full-screen slideshow of VENUS NIRCam RGB images in `cover_image/venus/`)
- `about.html`, `news.html`, `team.html`, `data.html`, `events.html` - content pages
- `pubs.html` - publications page (cards with key figures; data driven, see below)
- `assets/` - theme (HTML5 UP "Spectral") CSS/JS
- `icon/` - logos and favicons

## Publications automation

`pubs.html` renders `pubs/pubs.json`, which is regenerated daily from the public
ADS library by a GitHub Action (`.github/workflows/update-publications.yml`,
running `scripts/update_pubs.py`). For each new paper with an arXiv id, the
script also downloads the first figure of the arXiv HTML version into
`pubs/figures/<arxiv_id>.jpg` as a default key figure.

To curate an entry (better figure, custom 1-2 sentence blurb, or hide it),
edit `pubs/overrides.json` - the automation never touches that file.
Adding a paper to the site = add it to the ADS library
(https://ui.adsabs.harvard.edu/public-libraries/81Jnu02bT_-A-8TngvUXPA);
it appears on the site after the next workflow run (or trigger the workflow
manually from the Actions tab).

Notes:
- No API token is required (the script falls back to the anonymous ADS UI
  token), but a personal ADS token can be set as the `ADS_API_TOKEN`
  repository secret for a more robust path.
- GitHub disables scheduled workflows after ~60 days without repository
  activity; a manual run from the Actions tab re-enables them.
