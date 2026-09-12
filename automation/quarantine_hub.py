#!/usr/bin/env python3
"""quarantine_hub.py — take a mislabelled hub page out of circulation, non-destructively.

Why this exists (2026-09-12)
----------------------------
`best-blackout-curtains.html` went live titled "Best Blackout Curtains: 6 Picks Under
$35" listing four bedside table lamps, a hair towel wrap and a pack of washcloths —
not one window treatment. The picks came from Amazon's Window Treatments best-seller
node, which is bleeding products from neighbouring charts, and the old guard only
checked which node a product came from, never what it was.

`category_identity.in_category` now stops that at generation time. But a guard that
merely refuses to publish leaves the ALREADY-published lie live forever — the page
stops being refreshed and the stale false version keeps taking traffic. Refusing to
write a new lie is not the same as withdrawing the old one.

So when a hub cannot be rebuilt honestly, quarantine it:
  * noindex,nofollow so search engines drop it
  * replace the false product table with an honest notice
  * pull it from links.html and sitemap.xml so we stop sending traffic

NOTHING IS DELETED. The file stays in git and on disk, and the daily pipeline will
republish it in full the moment the category can fill honestly again.

    python3 automation/quarantine_hub.py best-blackout-curtains --reason "..."
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "blog" / "posts"

NOTICE = (
    '<div class="updated-notice" style="background:#fff8e1;border:1px solid #f0d58c;'
    'padding:14px 16px;border-radius:8px;margin:0 0 20px">'
    '<strong>This roundup is being rebuilt.</strong> The picks previously shown here '
    'did not match the topic of the page, so they have been removed rather than left '
    'up. We publish a pick only when it genuinely belongs on the page and its rating '
    'and review count have been read off the live listing. This page will return once '
    'it can be filled honestly.</div>'
)


def quarantine(slug: str, reason: str = "") -> int:
    page = POSTS / f"{slug}.html"
    if not page.exists():
        print(f"  [quarantine] {slug}: no such page")
        return 1
    html = page.read_text()
    changed = []

    if 'name="robots"' not in html:
        html = html.replace("<head>", '<head>\n<meta name="robots" content="noindex,nofollow">', 1)
        changed.append("noindex")

    # Drop the product table — it is the part that actually misleads.
    new, n = re.subn(r'<table class="cmp">.*?</table>', NOTICE, html, count=1, flags=re.S)
    if n:
        html = new
        changed.append("table replaced")
    elif "updated-notice" not in html:
        html = re.sub(r"(</h1>)", r"\1\n  " + NOTICE, html, count=1)
        changed.append("notice added")

    # Product cards repeat the same claims further down.
    new, n = re.subn(r'<section class="post-section">\s*<div class="product-card">.*?</section>',
                     "", html, flags=re.S)
    if n:
        html = new
        changed.append(f"{n} product card(s) removed")

    # The ItemList JSON-LD is the worst offender and the easiest to miss: it is
    # invisible on the page but it is exactly what Google reads to build a rich
    # result, so leaving it would let "Best Blackout Curtains" surface in search
    # with six bedside table lamps listed under it. Strip any ld+json block that
    # carries the product list; leave Article/Breadcrumb blocks alone.
    def _drop_itemlist(m):
        return "" if '"ItemList"' in m.group(0) else m.group(0)

    new, n = re.subn(r'<script type="application/ld\+json">.*?</script>',
                     _drop_itemlist, html, flags=re.S)
    if new != html:
        html = new
        changed.append("ItemList JSON-LD removed")

    page.write_text(html)

    # Stop sending traffic: sitemap + links page.
    sm = ROOT / "sitemap.xml"
    if sm.exists():
        s = sm.read_text()
        s2 = re.sub(r"\s*<url>(?:(?!</url>).)*?" + re.escape(slug) + r"(?:(?!</url>).)*?</url>",
                    "", s, flags=re.S)
        if s2 != s:
            sm.write_text(s2)
            changed.append("removed from sitemap")

    lk = ROOT / "links.html"
    if lk.exists():
        s = lk.read_text()
        s2 = re.sub(r"\s*<li>(?:(?!</li>).)*?" + re.escape(slug) + r"(?:(?!</li>).)*?</li>",
                    "", s, flags=re.S)
        if s2 == s:
            s2 = re.sub(r'\s*<a[^>]*' + re.escape(slug) + r'[^>]*>.*?</a>', "", s, flags=re.S)
        if s2 != s:
            lk.write_text(s2)
            changed.append("removed from links.html")

    print(f"  [quarantine] {slug}: {', '.join(changed) or 'no change needed'}")
    if reason:
        print(f"               reason: {reason}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--reason", default="")
    a = ap.parse_args()
    return quarantine(a.slug, a.reason)


if __name__ == "__main__":
    raise SystemExit(main())
