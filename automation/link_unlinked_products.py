#!/usr/bin/env python3
"""link_unlinked_products.py — turn "still vetting" placeholders into real,
verified affiliate links.

The blog writer runs in GitHub Actions, where Amazon bot-walls the runner IP, so it
can only link products that already sit in the vetted registry. When Claude
recommends a genuinely better product that isn't in the pool, the section ships with
a `cta-disabled` placeholder and the post earns nothing — the same zero-affiliate-link
failure that hit the June posts. Search demand without a payable link is worthless.

This closes the loop from the Pi's residential IP: find placeholder sections, pull
the product name out of the heading, search Amazon for it, VERIFY the listing is live
via /dp/, and only then rewrite the placeholder into a real CTA and add the ASIN to
the vetted pool for future posts.

Deliberately conservative — a wrong link is worse than no link (see the April
dead-ASIN incident, where 82% of hrefs were hallucinated and converted 0/902):
  * the search result's title must genuinely overlap the requested product name
  * the /dp/ page must render a real product title (verify_dp)
  * anything uncertain keeps its placeholder

    python3 automation/link_unlinked_products.py [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from asin_discoverer import REGISTRY_PATH, UA, search_amazon, verify_dp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "blog" / "posts"
TAG = "goldenhomep06-20"

PLACEHOLDER = re.compile(
    r'<p class="cta-disabled">.*?</p>', re.S)
SECTION = re.compile(
    r'<section class="post-section">\s*<h2>(?P<h2>.*?)</h2>(?P<body>.*?)</section>', re.S)

STOP = {"best", "the", "for", "a", "an", "and", "or", "with", "pick", "overall",
        "budget", "value", "runner", "up", "our", "top", "choice", "if", "you",
        "your", "want", "need", "on", "in", "to", "of", "most", "people"}


def product_name_from_heading(h2: str) -> str | None:
    """Headings look like 'Best Pick for Deep Drawers: YouCopia StoraFlex Dividers'.
    The product is what follows the last colon; a heading with no colon is usually a
    comparison/FAQ section with no single product to link."""
    text = re.sub(r"<[^>]+>", "", h2).strip()
    if ":" not in text:
        return None
    name = text.rsplit(":", 1)[1].strip()
    if len(name) <= 6 or NOT_A_PRODUCT.search(name) or len(tokens(name)) < 2:
        return None                # comparison/FAQ heading, nothing to link
    return name


def tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in STOP and len(w) > 2}


# Headings that survive the colon rule but name no product.
NOT_A_PRODUCT = re.compile(
    r"\b(what|which|how|why|when|comparison|compare|side-by-side|verdict|held up|"
    r"should you|buying guide|faq|conclusion|takeaway|final|summary|worth it)\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def matches(requested: str, found_title: str) -> bool:
    """Guard against linking the WRONG product.

    Token overlap alone is not enough: the first live run matched
    "G.U.S. Bamboo Adjustable Drawer Dividers" to a SpaceAid listing, because
    bamboo/drawer/dividers all overlapped while the brand did not. Recommending one
    brand and linking another is dishonest and it is how the April dead-ASIN
    incident converted 0/902. So the BRAND must match too.
    """
    req_raw, got_raw = _norm(requested), _norm(found_title)
    req, got = tokens(req_raw), tokens(got_raw)
    if not req or len(req) < 2:
        return False
    # Brand = first distinctive token of the requested name (G.U.S. -> "gus").
    brand = next((w for w in req_raw.split() if w not in STOP and len(w) > 1), "")
    if brand and brand not in got_raw.split():
        return False
    return len(req & got) >= max(2, round(len(req) * 0.6))


def cta_html(asin: str, name: str, slug: str) -> str:
    url = (f"https://www.amazon.com/dp/{asin}?tag={TAG}"
           f"&ascsubtag=blog-{slug[:28]}")
    return (f'<p><a class="cta" href="{url}" rel="sponsored nofollow noopener" '
            f'target="_blank">Check current price on Amazon &rarr;</a></p>')


def register(entry: dict) -> None:
    reg = json.loads(REGISTRY_PATH.read_text())
    reg.setdefault("vetted", [])
    if any(v.get("asin") == entry["asin"] for v in reg["vetted"]):
        return
    reg["vetted"].append(entry)
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6, help="max products to resolve")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    targets = [p for p in sorted(POSTS.glob("*.html")) if "cta-disabled" in p.read_text()]
    if not targets:
        print("[link] no posts with unlinked sections")
        return 0
    print(f"[link] {len(targets)} post(s) with placeholders: "
          + ", ".join(p.name for p in targets[-3:]))

    from playwright.sync_api import sync_playwright

    resolved = skipped = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        for post in targets:
            html = post.read_text()
            slug = post.stem
            changed = False
            for m in SECTION.finditer(html):
                if resolved >= args.limit:
                    break
                block = m.group(0)
                if 'cta-disabled' not in block:
                    continue
                name = product_name_from_heading(m.group("h2"))
                if not name:
                    continue
                # Amazon throttles /s?k= far more aggressively than /dp/ — a burst of
                # searches in one run started timing out every time after the first
                # few. Pace them and keep --limit small; unresolved placeholders are
                # simply retried by tomorrow's run rather than hammering now.
                if resolved or skipped:
                    time.sleep(random.uniform(8, 15))
                print(f"  [search] {name[:60]}")
                hit = search_amazon(page, name)
                if not hit or not hit.get("asin"):
                    print("    no search result — keeping placeholder")
                    skipped += 1
                    continue
                if not matches(name, hit.get("title", "")):
                    print(f"    MISMATCH vs {hit.get('title','')[:50]!r} — keeping placeholder")
                    skipped += 1
                    continue
                info = verify_dp(page, hit["asin"])
                if not info or not info.get("title"):
                    print("    /dp/ did not verify — keeping placeholder")
                    skipped += 1
                    continue
                new_block = block.replace(
                    PLACEHOLDER.search(block).group(0), cta_html(hit["asin"], name, slug))
                html = html.replace(block, new_block)
                changed = True
                resolved += 1
                print(f"    LINKED {hit['asin']}  {info['title'][:52]}")
                if not args.dry_run:
                    register({
                        "asin": hit["asin"],
                        "product_name": info["title"],
                        "categories": ["blog-resolved"],
                        "affiliate_url": f"https://www.amazon.com/dp/{hit['asin']}?tag={TAG}",
                        "status": "live",
                        "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "verified_method": "link_unlinked_products/search+dp",
                        "verified_price": info.get("price") or hit.get("price"),
                        "verified_stars": str(info.get("stars") or hit.get("stars") or ""),
                        "verified_reviews": info.get("reviews") or hit.get("reviews"),
                        "discovery_source": "blog_product_resolver",
                    })
            if changed and not args.dry_run:
                post.write_text(html)
                print(f"  [write] {post.name}")

        ctx.close()
        browser.close()

    print(f"\n[link] linked={resolved} skipped={skipped}"
          + ("  (--dry-run, nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
