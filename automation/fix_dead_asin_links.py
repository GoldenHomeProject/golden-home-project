"""Remediate dead-ASIN affiliate links in products/*.html.

Background: a Chrome verification of the 221 unique ASINs on goldenhomeproject.com
returned 182 dead (82%) — they 404 on Amazon. This explains the 0/902 (0%)
conversion rate on Amazon Associates: most clicks land on "Page Not Found".

Fix: replace every dead /dp/{ASIN}?tag=goldenhomep06-20 link with an Amazon
SEARCH url keyed off the product's `alt` text — same affiliate tag, lands on
real live listings, drops the 24h cookie, and any qualifying purchase still
earns commission. Allowed under Amazon Associates Operating Agreement
(search-result destinations with a valid tag are explicitly permitted).

Also rewrites the matching <img src=...{ASIN}.jpg...> to '' so the existing
onerror display:none kicks in cleanly (no flash of broken image).

Usage:
    python automation/fix_dead_asin_links.py        # dry run, prints summary
    python automation/fix_dead_asin_links.py --apply # writes changes
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from urllib.parse import quote_plus

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROD = ROOT / "products"
DEAD_FILE = pathlib.Path("/tmp/ghp_dead_asins.txt")
TAG = "goldenhomep06-20"

# Regex captures: <a href="https://www.amazon.com/dp/{ASIN}?tag=...">
HREF_RE = re.compile(
    r'(href="https://www\.amazon\.com/dp/)([A-Z0-9]{10})(\?tag=' + re.escape(TAG) + r'")'
)
# Regex captures: <img src="https://m.media-amazon.com/images/P/{ASIN}.01...
IMG_RE = re.compile(
    r'(src="https://m\.media-amazon\.com/images/P/)([A-Z0-9]{10})(\.01\._SCLZZZZZZZ_SX300_\.jpg")'
)
# Find alt= for a given ASIN: alt="Product Name" appears on the same image tag
# We'll build asin -> product name map per file by scanning <img> tags.
IMG_FULL_RE = re.compile(
    r'<img[^>]+P/([A-Z0-9]{10})\.01[^>]+alt="([^"]+)"',
    re.DOTALL,
)


def search_url(product_name: str) -> str:
    return f'https://www.amazon.com/s?k={quote_plus(product_name)}&tag={TAG}'


def fix_file(path: pathlib.Path, dead: set[str]) -> tuple[int, int]:
    text = path.read_text()
    asin_to_name: dict[str, str] = {}
    for m in IMG_FULL_RE.finditer(text):
        asin_to_name.setdefault(m.group(1), m.group(2))

    rewrites = 0
    img_blanked = 0

    def replace_href(m: re.Match) -> str:
        nonlocal rewrites
        asin = m.group(2)
        if asin not in dead:
            return m.group(0)
        name = asin_to_name.get(asin, "home goods")
        rewrites += 1
        # Replace whole href value, not just the inside parts
        return f'href="{search_url(name)}"'

    new_text = HREF_RE.sub(replace_href, text)

    def replace_img(m: re.Match) -> str:
        nonlocal img_blanked
        asin = m.group(2)
        if asin not in dead:
            return m.group(0)
        img_blanked += 1
        # Set src to empty data-uri so onerror fires and image hides cleanly
        return 'src=""'

    new_text = IMG_RE.sub(replace_img, new_text)

    if rewrites or img_blanked:
        if APPLY:
            path.write_text(new_text)
    return rewrites, img_blanked


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = p.parse_args()
    global APPLY
    APPLY = args.apply

    dead = set(DEAD_FILE.read_text().split())
    if not dead:
        print("No dead ASINs loaded.", file=sys.stderr)
        return 1

    total_rewrites = 0
    total_imgs = 0
    files_touched = 0
    for path in sorted(PROD.glob("post-*.html")):
        r, i = fix_file(path, dead)
        if r or i:
            files_touched += 1
            print(f"  {path.name}: {r} hrefs rewritten, {i} images blanked")
            total_rewrites += r
            total_imgs += i

    mode = "APPLIED" if APPLY else "DRY RUN"
    print()
    print(f"[{mode}] {files_touched} files would be modified")
    print(f"  {total_rewrites} dead-ASIN affiliate hrefs rewritten -> Amazon search URLs (tag preserved)")
    print(f"  {total_imgs} broken product images blanked")
    if not APPLY:
        print("\nRe-run with --apply to write changes.")
    return 0


APPLY = False

if __name__ == "__main__":
    sys.exit(main())
