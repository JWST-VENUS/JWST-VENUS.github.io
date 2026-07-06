#!/usr/bin/env python3
"""
Update the VENUS publication list from the public ADS library.

- Fetches the JWST-VENUS public ADS library (no token required: falls back to
  the anonymous "bootstrap" token used by the ADS web UI; set ADS_API_TOKEN
  for a more robust authenticated path).
- Writes pubs/pubs.json (only when content changed, so the GitHub Action
  does not create empty commits).
- For every new paper with an arXiv id, tries to download the first figure
  of the arXiv HTML version into pubs/figures/<arxiv_id>.jpg as a default
  "key figure". Editors can replace any figure/blurb via pubs/overrides.json
  (files already present are never overwritten).

Run from the repository root:  python3 scripts/update_pubs.py
"""

import json
import os
import re
import sys
import urllib.request
import urllib.parse

LIBRARY_ID = "81Jnu02bT_-A-8TngvUXPA"
API = "https://api.adsabs.harvard.edu/v1"
BOOTSTRAP_URL = "https://ui.adsabs.harvard.edu/v1/accounts/bootstrap"
FIELDS = ("bibcode,title,author,year,pub,volume,page,doi,identifier,"
          "abstract,date,doctype,citation_count")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBS_JSON = os.path.join(REPO_ROOT, "pubs", "pubs.json")
FIG_DIR = os.path.join(REPO_ROOT, "pubs", "figures")
UA = "JWST-VENUS-website-updater (jwst-venus.github.io)"


def http_get(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.geturl()


def get_token():
    token = os.environ.get("ADS_API_TOKEN", "").strip()
    if token:
        return token
    body, _ = http_get(BOOTSTRAP_URL)
    return json.loads(body)["access_token"]


def fetch_library(token):
    headers = {"Authorization": f"Bearer {token}"}
    body, _ = http_get(f"{API}/biblib/libraries/{LIBRARY_ID}?rows=500", headers)
    lib = json.loads(body)
    bibcodes = lib["documents"]
    query = urllib.parse.urlencode({
        "q": f"docs(library/{LIBRARY_ID})",
        "fl": FIELDS,
        "rows": 500,
        "sort": "date desc",
    })
    body, _ = http_get(f"{API}/search/query?{query}", headers)
    docs = json.loads(body)["response"]["docs"]
    # keep only docs still in the library (search index can lag)
    docs = [d for d in docs if d["bibcode"] in set(bibcodes)]
    return lib["metadata"], docs


def arxiv_id_of(doc):
    for ident in doc.get("identifier", []):
        m = re.match(r"^arXiv:(\d{4}\.\d{4,5})$", ident)
        if m:
            return m.group(1)
    return None


def fetch_arxiv_first_figure(arxiv_id):
    """Return raw image bytes of the first figure in the arXiv HTML version."""
    html, final_url = http_get(f"https://arxiv.org/html/{arxiv_id}")
    html = html.decode("utf-8", "ignore")
    m = re.search(r"<figure[^>]*>.*?<img[^>]+src=\"([^\"]+)\"", html, re.S)
    if not m:
        m = re.search(r"<img[^>]+src=\"([^\"]+\.(?:png|jpe?g))\"", html)
    if not m:
        return None
    img_url = urllib.parse.urljoin(final_url + "/", m.group(1))
    body, _ = http_get(img_url)
    return body


def save_figure(raw, out_path):
    """Downscale to web size with Pillow when available; otherwise skip."""
    try:
        from io import BytesIO
        from PIL import Image
    except ImportError:
        print("  Pillow not available; skipping figure conversion", file=sys.stderr)
        return False
    img = Image.open(BytesIO(raw))
    if img.mode in ("RGBA", "P", "LA"):
        from PIL import Image as _I
        bg = _I.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    if img.width > 1200:
        img = img.resize((1200, round(img.height * 1200 / img.width)), Image.LANCZOS)
    img.save(out_path, "JPEG", quality=85)
    return True


def build_records(docs):
    records = []
    for d in docs:
        arxiv = arxiv_id_of(d)
        fig_rel = f"pubs/figures/{arxiv}.jpg" if arxiv else None
        records.append({
            "bibcode": d["bibcode"],
            "title": (d.get("title") or [""])[0],
            "authors": d.get("author") or [],
            "year": d.get("year"),
            "date": d.get("date", "")[:10],
            "pub": d.get("pub"),
            "doctype": d.get("doctype"),
            "doi": (d.get("doi") or [None])[0],
            "arxiv": arxiv,
            "citations": d.get("citation_count", 0),
            "abstract": d.get("abstract", ""),
            "figure": fig_rel if os.path.exists(os.path.join(REPO_ROOT, fig_rel or "")) else None,
        })
    return records


def main():
    token = get_token()
    meta, docs = fetch_library(token)
    print(f"Library '{meta['name']}': {len(docs)} documents")

    # download default key figures for papers that do not have one yet
    os.makedirs(FIG_DIR, exist_ok=True)
    for d in docs:
        arxiv = arxiv_id_of(d)
        if not arxiv:
            continue
        out_path = os.path.join(FIG_DIR, f"{arxiv}.jpg")
        if os.path.exists(out_path):
            continue
        try:
            raw = fetch_arxiv_first_figure(arxiv)
            if raw and save_figure(raw, out_path):
                print(f"  figure saved: {out_path}")
            else:
                print(f"  no figure found for arXiv:{arxiv}")
        except Exception as exc:  # keep going: figures are best-effort
            print(f"  figure fetch failed for arXiv:{arxiv}: {exc}", file=sys.stderr)

    payload = {
        "library": {
            "id": LIBRARY_ID,
            "name": meta["name"],
            "url": f"https://ui.adsabs.harvard.edu/public-libraries/{LIBRARY_ID}",
            "date_last_modified": meta.get("date_last_modified"),
        },
        "publications": build_records(docs),
    }
    new_text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    old_text = None
    if os.path.exists(PUBS_JSON):
        with open(PUBS_JSON, encoding="utf-8") as f:
            old_text = f.read()
    if new_text == old_text:
        print("pubs.json unchanged")
        return
    os.makedirs(os.path.dirname(PUBS_JSON), exist_ok=True)
    with open(PUBS_JSON, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"pubs.json updated ({len(docs)} publications)")


if __name__ == "__main__":
    main()
