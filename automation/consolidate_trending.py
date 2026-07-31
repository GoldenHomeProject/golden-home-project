#!/usr/bin/env python3
"""consolidate_trending.py — point the old dated trending URLs at their evergreen page.

Eight near-identical dated roundups ("6 Bath Best-Sellers Everyone's Buying Right Now")
were minted one per day. They target no search query, duplicate each other, and split
whatever ranking signal the domain has — Search Console: 108 impressions / 8 clicks in
90 days at avg position 36.9. Each category now owns ONE permanent page that targets a
real head query and refreshes daily.

GitHub Pages serves static files, so a 301 is not available. The standard static
equivalent is used instead: rel=canonical pointing at the evergreen URL (tells Google
which page should rank and consolidates the signal onto it) plus a visible banner
linking readers to the current version.

NON-DESTRUCTIVE: the original article stays exactly where it is and stays readable. Old
links keep working; only the canonical target and a banner are added.
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
BASE = "https://goldenhomeproject.com/blog/posts"

# filename fragment -> EVERGREEN key. Longest first so "home-storage"/"home-decor"
# are not swallowed by the bare "home" rule.
CAT_BY_FRAGMENT = [
    ("home-storage", "Home Storage"),
    ("home-decor", "Home Décor"),
    ("kitchen", "Kitchen"),
    ("cleaning", "Cleaning"),
    ("bath", "Bath"),
    ("coffee", "Coffee & Tea"),
    ("home", "Home"),
]

BANNER = (
    '<div class="updated-notice" style="background:#fff8e1;border:1px solid #f0d58c;'
    'padding:14px 16px;border-radius:8px;margin:0 0 20px">'
    '<strong>This roundup has moved.</strong> We now keep one continuously updated '
    'page for {label}: <a href="/blog/posts/{slug}.html">{query}</a> — refreshed daily '
    'with the current best-sellers. The snapshot below is kept for reference.</div>'
)


def category_for(name: str) -> str | None:
    for frag, cat in CAT_BY_FRAGMENT:
        if frag in name:
            return cat
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    changed = skipped = 0
    for post in sorted(POSTS.glob("*trending*best-sellers*.html")):
        cat = category_for(post.name)
        if not cat or cat not in EVERGREEN:
            print(f"  SKIP (no category) {post.name}")
            skipped += 1
            continue
        slug, query = EVERGREEN[cat]
        if post.stem == slug:
            continue                       # the evergreen page itself
        html = post.read_text()
        target = f"{BASE}/{slug}.html"
        if target in html:
            print(f"  already consolidated: {post.name}")
            continue

        new_html, n = re.subn(r'<link rel="canonical" href="[^"]*">',
                              f'<link rel="canonical" href="{target}">', html, count=1)
        if not n:
            new_html = new_html.replace("</head>", f'<link rel="canonical" href="{target}">\n</head>', 1)
        if "updated-notice" not in new_html:
            banner = BANNER.format(label=cat.lower(), slug=slug, query=query)
            new_html = re.sub(r"(<h1>.*?</h1>)", r"\1\n  " + banner.replace("\\", "\\\\"),
                              new_html, count=1, flags=re.S)
        print(f"  {post.name}  ->  {slug}.html")
        if not args.dry_run:
            post.write_text(new_html)
        changed += 1

    print(f"\n[consolidate] {changed} consolidated, {skipped} skipped"
          + ("  (--dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
