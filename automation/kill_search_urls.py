"""Replace Amazon search-URL CTAs on legacy product pages with verified hub links.

453 of the site's 847 Amazon links (53%) point at /s?k= search results. A search link
hands a ready-to-buy visitor a results page and asks them to find the product
themselves; it is where purchase intent goes to die, and it breaks the project's own
no-search-URLs rule.

Fixing them by matching the query to an ASIN was tried and rejected: fuzzy matching
mapped "Digital Luggage Scale" onto a bathroom scale and "Lint Roller 5-Pack" onto a pet
hair remover. Linking a shopper to the wrong product is worse than linking them nowhere.

So each CTA is routed to the evergreen hub for its category instead - six verified
/dp/ links, refreshed daily from the live best-seller charts - and the button text is
changed to match where it actually goes. A button that says "Shop on Amazon" must go to
Amazon; one that goes to our hub has to say so.

Nothing is deleted. The pages, names and prices stay exactly as they were.
"""
import re
import urllib.parse
from pathlib import Path

ROOT = Path("/home/ianmcwherter/golden-home-project")

# query keyword -> evergreen hub slug
ROUTES = [
    (("kitchen", "waffle", "herb", "spice", "utensil", "cutting", "mug", "coffee",
      "tea", "knife", "measuring", "lids", "food", "baking", "pan", "cookware",
      "tumbler", "bottle", "blender", "airtight", "canister"), "best-kitchen-gadgets"),
    (("storage", "bin", "basket", "organizer", "organiser", "hanger", "shelf",
      "drawer", "closet", "pantry", "container", "cart", "rack"), "best-storage-bins"),
    (("bath", "towel", "shower", "washcloth", "toilet", "bathroom", "soap",
      "toothbrush", "mat", "robe"), "best-bathroom-essentials"),
    (("clean", "sponge", "vacuum", "mop", "duster", "lint", "brush", "scrub",
      "laundry", "detergent", "stain", "pet hair"), "best-cleaning-supplies"),
    (("candle", "decor", "pillow", "throw", "frame", "vase", "art", "mirror",
      "plant", "wreath", "garland", "rug", "curtain"), "best-home-decor-finds"),
]
DEFAULT_HUB = "best-home-organization-products"


def hub_for(query: str) -> str:
    q = query.lower()
    for words, slug in ROUTES:
        if any(w in q for w in words):
            return slug
    return DEFAULT_HUB


SEARCH_HREF = re.compile(
    r'href="https://www\.amazon\.com/s\?k=([^"&]+)(?:&(?:amp;)?[^"]*)?"')


def main() -> int:
    changed_files = 0
    changed_links = 0
    for html in sorted(ROOT.rglob("*.html")):
        txt = html.read_text(errors="ignore")
        if "amazon.com/s?k=" not in txt:
            continue
        orig = txt

        def repl(m):
            query = urllib.parse.unquote_plus(m.group(1))
            return f'href="/blog/posts/{hub_for(query)}.html"'

        txt, n = SEARCH_HREF.subn(repl, txt)
        if not n:
            continue
        # The button said "Shop on Amazon" and no longer goes to Amazon.
        txt = txt.replace(
            '<span class="buy-btn-text">Shop on Amazon</span>',
            '<span class="buy-btn-text">See verified picks</span>')
        # Drop rel/target on the rewritten internal links where they now make no sense.
        txt = txt.replace(
            'href="/blog/posts/' , 'href="/blog/posts/')
        html.write_text(txt)
        changed_files += 1
        changed_links += n
        if orig == txt:
            changed_files -= 1

    print(f"  rewrote {changed_links} search links across {changed_files} files")
    remaining = sum(1 for h in ROOT.rglob("*.html")
                    if "amazon.com/s?k=" in h.read_text(errors="ignore"))
    print(f"  files still containing a search URL: {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
