#!/usr/bin/env python3
"""inject_hub_nav.py — link the evergreen category hubs from everywhere that matters.

Why (2026-08-07): Search Console reports 13 pages "Discovered - currently not indexed".
An audit found the cause — the six evergreen hubs were ORPHANS: zero links from the
homepage, zero from the blog index (regenerate_index() rebuilds that file and drops all
but the newest hub card), and zero links between each other. They existed only in
sitemap.xml. A URL that appears in a sitemap with no internal links pointing at it is
exactly what Google labels "Discovered - currently not indexed": it found the address
and decided the page wasn't important enough to crawl. Internal links are how a site
tells Google which pages matter, and we were telling it "none of them".

This injects one nav block in three places, idempotently (safe to re-run daily, which is
required because other generators rewrite index pages):
  * every hub page  -> links the other hubs, forming a crawlable cluster
  * blog/index.html -> a category row above the post feed
  * index.html      -> same, on the homepage, which holds the most authority

    python3 automation/inject_hub_nav.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trending_daily import EVERGREEN  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "blog" / "posts"
MARK_OPEN = "<!-- hub-nav:start -->"
MARK_CLOSE = "<!-- hub-nav:end -->"
BLOCK_RE = re.compile(re.escape(MARK_OPEN) + r".*?" + re.escape(MARK_CLOSE), re.S)


def all_hubs() -> list[tuple[str, str]]:
    """(slug, label) for every hub page on disk, not just the daily rotation.

    Seasonal hubs (e.g. best-dorm-room-essentials, built for the back-to-college window)
    live outside EVERGREEN, and a hub nobody links to is an orphan — the exact condition
    that left 13 pages "Discovered - currently not indexed".
    """
    hubs = {slug: query for _c, (slug, query) in EVERGREEN.items()}
    for page in sorted(POSTS.glob("best-*.html")):
        if page.stem in hubs:
            continue
        m = re.search(r"<title>([^<|]+)", page.read_text())
        label = (m.group(1).split(":")[0].strip() if m
                 else page.stem.replace("-", " ").title())
        hubs[page.stem] = label
    return sorted(hubs.items(), key=lambda kv: kv[1])



OG_MARK = "<!-- og-tags:start -->"
OG_BLOCK = (
    f'{OG_MARK}\n'
    '<meta property="og:site_name" content="Golden Home Project">\n'
    '<meta property="og:image" content="https://goldenhomeproject.com/images/og-default.jpg">\n'
    '<meta property="og:image:width" content="1200">\n'
    '<meta property="og:image:height" content="630">\n'
    '<meta name="twitter:card" content="summary_large_image">\n'
    "<!-- og-tags:end -->"
)


def ensure_og(paths, dry: bool) -> int:
    """Give every static page a share image.

    The generated hubs and posts got og:image, but the hand-written pages did not — the
    HOMEPAGE, blog index, about, contact, privacy and links all shared as a blank card.
    Those are the most-linked pages on the site, so they were the worst ones to leave
    imageless on a visual platform like Pinterest.
    """
    changed = 0
    for rel in paths:
        f = ROOT / rel
        if not f.exists():
            continue
        html = f.read_text()
        if "og:image" in html:
            continue
        if "</head>" not in html:
            print(f"  no <head> in {rel} — skipped")
            continue
        if not dry:
            f.write_text(html.replace("</head>", OG_BLOCK + "\n</head>", 1))
        print(f"  og tags -> {rel}")
        changed += 1
    return changed


def nav_html(exclude_slug: str | None, heading: str) -> str:
    links = []
    for slug, query in all_hubs():
        if slug == exclude_slug:
            continue
        label = query.title().replace(" And ", " and ")
        links.append(
            f'<a href="/blog/posts/{slug}.html" '
            f'style="display:inline-block;padding:10px 16px;margin:6px 8px 6px 0;'
            f'background:#141428;border:1px solid rgba(212,167,69,.35);border-radius:999px;'
            f'color:#f0ece4;text-decoration:none;font-size:15px">{label}</a>')
    return (
        f'{MARK_OPEN}\n<nav class="hub-nav" aria-label="Product guides" '
        f'style="margin:28px 0;padding:20px;border-top:1px solid rgba(212,167,69,.2)">\n'
        f'  <h2 style="font-size:19px;margin:0 0 12px">{heading}</h2>\n  '
        + "\n  ".join(links)
        + f'\n</nav>\n{MARK_CLOSE}')


def upsert(path: Path, block: str, anchor_re: str, after: bool, dry: bool) -> bool:
    """Replace an existing block, else insert relative to an anchor."""
    if not path.exists():
        print(f"  MISSING {path}")
        return False
    html = path.read_text()
    if BLOCK_RE.search(html):
        new = BLOCK_RE.sub(lambda _m: block, html, count=1)
    else:
        m = re.search(anchor_re, html, re.S)
        if not m:
            print(f"  no anchor in {path.name} — skipped")
            return False
        idx = m.end() if after else m.start()
        new = html[:idx] + "\n" + block + "\n" + html[idx:]
    if new == html:
        return False
    if not dry:
        path.write_text(new)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    changed = 0

    # 1. hub -> hub cluster
    for slug, _q in all_hubs():
        page = POSTS / f"{slug}.html"
        block = nav_html(exclude_slug=slug, heading="More Golden Home Project guides")
        if upsert(page, block, r'<div class="faq-section">|</body>', after=False, dry=args.dry_run):
            print(f"  hub nav -> {page.name}")
            changed += 1

    # 2. blog index, above the post feed
    block = nav_html(None, "Browse by category")
    if upsert(ROOT / "blog" / "index.html", block, r"<h1>The Blog</h1>", after=True, dry=args.dry_run):
        print("  hub nav -> blog/index.html")
        changed += 1

    # 3. homepage — the strongest internal-link source we have
    if upsert(ROOT / "index.html", block,
              r'<section class="section section-dark" id="products">', after=False,
              dry=args.dry_run):
        print("  hub nav -> index.html")
        changed += 1

    changed += ensure_og(
        ["index.html", "blog/index.html", "about.html", "contact.html",
         "privacy.html", "links.html"], args.dry_run)

    print(f"[hub-nav] {changed} file(s) updated" + ("  (--dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
