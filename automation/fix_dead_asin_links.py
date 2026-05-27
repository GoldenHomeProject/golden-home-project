"""DISABLED 2026-05-27 — DO NOT RUN.

Historical context (kept for the record):
This script was the April 2026 remediation for the dead-ASIN incident on
goldenhomeproject.com — 182 of 221 ASINs were 404, killing Associates
conversion. The fix at the time rewrote dead /dp/<ASIN>?tag= hrefs to
Amazon SEARCH URLs (`/s?k=...&tag=`) keyed off the product's alt text.

That fix was WRONG. User correction on 2026-05-26:
    "you ccant use search urls, you have to use the actually affilate links
     form our account or we dont get credit for the sale"

Amazon Associates does NOT credit conversions on search-URL clicks for the
goldenhomep06-20 account — only direct /dp/<ASIN>?tag= or affiliate-network
short links (sjv.io, amzn.to) pay. This script's entire output is therefore
revenue-zero.

What to use instead:
- `automation/asin_discoverer.py` — auto-discovers + verifies real ASINs
  from Trend Scout opportunities, writes to dm_keyword_registry.json vetted[]
- `automation/blog_writer.py` — only emits CTAs for ASINs that are in the
  registry; never falls back to search URLs
- For one-off dead-link audits, write a NEW script that replaces dead
  hrefs with the closest matching vetted[]-pool ASIN, not a search URL

See: ~/.claude/projects/.../feedback_ghp_no_search_urls.md
"""
from __future__ import annotations

import sys

def _refuse_to_run() -> int:
    print(
        "REFUSING TO RUN: fix_dead_asin_links.py was disabled 2026-05-27.\n"
        "\n"
        "Its remediation strategy (rewrite dead ASINs to Amazon /s?k= search\n"
        "URLs) does not pay this Associates account. See module docstring and\n"
        "feedback_ghp_no_search_urls.md for the full context.\n"
        "\n"
        "Use automation/asin_discoverer.py to grow the vetted ASIN pool and\n"
        "write a new remediation that rewrites dead links to vetted-pool ASINs.\n",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(_refuse_to_run())


# Everything below is preserved as dead reference code so the original
# (search-URL-emitting) implementation is recoverable if we ever need to
# audit what was historically generated. It is unreachable.
import argparse  # noqa: E402
import pathlib  # noqa: E402
import re  # noqa: E402
from urllib.parse import quote_plus  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROD = ROOT / "products"
DEAD_FILE = pathlib.Path("/tmp/ghp_dead_asins.txt")
TAG = "goldenhomep06-20"

HREF_RE = re.compile(
    r'(href="https://www\.amazon\.com/dp/)([A-Z0-9]{10})(\?tag=' + re.escape(TAG) + r'")'
)
IMG_RE = re.compile(
    r'(src="https://m\.media-amazon\.com/images/P/)([A-Z0-9]{10})(\.01\._SCLZZZZZZZ_SX300_\.jpg")'
)
IMG_FULL_RE = re.compile(
    r'<img[^>]+P/([A-Z0-9]{10})\.01[^>]+alt="([^"]+)"',
    re.DOTALL,
)


def search_url(product_name: str) -> str:  # noqa: F811
    # Retained for reference only — emits a URL that DOES NOT PAY this account.
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

# Original entry point (now unreachable — see top-of-file refusal):
# if __name__ == "__main__":
#     sys.exit(main())
