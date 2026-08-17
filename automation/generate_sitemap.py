#!/usr/bin/env python3
"""generate_sitemap.py — rebuild sitemap.xml from what is actually on disk.

The sitemap was hand-maintained and had drifted: 22 URLs that omitted every post
published since, while still listing dated trending roundups that now carry a
rel=canonical pointing at an evergreen page. Submitting a URL that canonicals
elsewhere is a contradictory signal — the sitemap says "index this", the page says
"no, index that one".

Rules:
  * a page whose canonical points at a DIFFERENT url is excluded (it is not canonical)
  * lastmod comes from the page's dateModified when present, else file mtime, so the
    daily-refreshed evergreen pages correctly advertise that they changed
  * evergreen category hubs get the highest priority — they are the pages meant to rank

    python3 automation/generate_sitemap.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITEMAP = ROOT / "sitemap.xml"
BASE = "https://goldenhomeproject.com"

STATIC = [("/", "1.0"), ("/blog/", "0.9"), ("/links.html", "0.5"),
          # Affiliate networks (Impact, ShareASale, Walmart) look for these before
          # approving a publisher; they are also what a reader checks before trusting
          # product recommendations.
          ("/about.html", "0.6"), ("/contact.html", "0.5"), ("/privacy.html", "0.4")]


def canonical_of(html: str) -> str | None:
    m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    return m.group(1) if m else None


def lastmod_of(path: Path, html: str) -> str:
    m = re.search(r'"dateModified":\s*"(\d{4}-\d{2}-\d{2})"', html)
    if m:
        return m.group(1)
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    entries: list[tuple[str, str, str]] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for loc, prio in STATIC:
        entries.append((BASE + loc, today, prio))

    dropped = 0
    for post in sorted((ROOT / "blog" / "posts").glob("*.html")):
        html = post.read_text()
        url = f"{BASE}/blog/posts/{post.name}"
        canon = canonical_of(html)
        if canon and canon.rstrip("/") != url.rstrip("/"):
            dropped += 1
            continue                      # consolidated into another page
        prio = "0.9" if post.stem.startswith("best-") else "0.7"
        entries.append((url, lastmod_of(post, html), prio))

    body = "\n".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{lm}</lastmod>\n"
        f"    <priority>{p}</priority>\n  </url>"
        for u, lm, p in entries)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f"{body}\n</urlset>\n")

    print(f"[sitemap] {len(entries)} urls ({dropped} excluded as non-canonical)")
    if args.dry_run:
        print("[sitemap] --dry-run, not written")
        return 0
    SITEMAP.write_text(xml)
    print(f"[sitemap] wrote {SITEMAP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
