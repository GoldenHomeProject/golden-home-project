"""Point "still vetting" placeholders at a relevant hub instead of the blog index.

10 CTAs across 5 posts carry a cta-disabled placeholder. The wording is honest and
stays exactly as it is — we genuinely have no product we trust for that specific named
brand, and link_unlinked_products.py correctly refuses to substitute a different one
(its matches() requires the brand token to agree; swapping brands would make the text
and the link disagree).

But the placeholder currently sends people to /blog/, a generic index. The evergreen
hubs carry six verified /dp/ links each and refresh daily, so routing there gives the
reader something real to buy without claiming it is the product named in the heading.
"""
import re
from pathlib import Path

ROOT = Path("/home/ianmcwherter/golden-home-project")

ROUTES = [
    (("drawer", "organizer", "divider", "storage", "bin", "closet", "sock",
      "underwear", "basket"), "best-storage-bins", "storage picks"),
    (("sheet", "bedding", "mattress", "duvet", "comforter", "pillow", "bedroom"),
     "best-bedding-essentials", "bedding picks"),
    (("curtain", "blackout", "window", "blind"), "best-blackout-curtains",
     "blackout curtain picks"),
    (("towel", "bath", "shower", "linen"), "best-bath-towels-and-linens",
     "bath linen picks"),
    (("kitchen", "dish", "rack", "utensil", "counter"), "best-kitchen-gadgets",
     "kitchen picks"),
    (("clean", "sponge", "mop", "vacuum"), "best-cleaning-supplies",
     "cleaning picks"),
    (("wall", "backsplash", "plaster", "decor", "accent", "frame"),
     "best-home-decor-finds", "decor picks"),
]
DEFAULT = ("best-home-organization-products", "home organization picks")

OLD = ('<a href="/blog/">Browse other Golden Home Project picks</a>')


def route_for(text: str):
    t = text.lower()
    for words, slug, label in ROUTES:
        if any(w in t for w in words):
            return slug, label
    return DEFAULT


def main() -> int:
    changed = 0
    for post in sorted((ROOT / "blog" / "posts").glob("*.html")):
        html = post.read_text()
        if OLD not in html:
            continue
        slug, label = route_for(post.stem)
        new = (f'<a href="/blog/posts/{slug}.html">See our verified {label}</a>')
        html2 = html.replace(OLD, new)
        if html2 != html:
            post.write_text(html2)
            n = html.count(OLD)
            changed += n
            print(f"  {post.name[:52]:54} -> {slug} ({n})")
    print(f"[cta] routed {changed} placeholder link(s) to a verified hub")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
