"""Put verified product links at the top of the Instagram bio funnel.

The funnel was: Instagram -> links.html -> /products/post-NNN.html -> an Amazon SEARCH
URL. 453 of the site's 847 Amazon links (53%) are search URLs, and all 59 pages that
carry them hang off this page. A search link hands a ready-to-buy visitor a results
page and asks them to go find it themselves, which is where the intent dies. It also
breaks our own no-search-URLs rule.

The six evergreen hubs are the opposite: 6 verified /dp/ links each, zero search URLs,
refreshed daily from the live best-seller charts. They were not linked from here at all.

This inserts them as the first section, so the highest-intent traffic we get lands on
real products. The legacy posts stay below, untouched - nothing is deleted.
"""
from pathlib import Path

ROOT = Path("/home/ianmcwherter/golden-home-project")
page = ROOT / "links.html"

HUBS = [
    ("best-kitchen-gadgets", "&#x1F373;", "Best Kitchen Gadgets",
     "6 verified picks &mdash; updated daily"),
    ("best-storage-bins", "&#x1F4E6;", "Best Storage Bins",
     "6 verified picks &mdash; updated daily"),
    ("best-home-organization-products", "&#x1F3E1;", "Home Organization Picks",
     "6 verified picks &mdash; updated daily"),
    ("best-bathroom-essentials", "&#x1F6C1;", "Bathroom Essentials",
     "6 verified picks &mdash; updated daily"),
    ("best-cleaning-supplies", "&#x1F9F9;", "Best Cleaning Supplies",
     "6 verified picks &mdash; updated daily"),
    ("best-home-decor-finds", "&#x1FA9E;", "Home Decor Finds",
     "6 verified picks &mdash; updated daily"),
    # Added 2026-08-30: the bathroom/bedroom textile hubs, built because that is the
    # theme our only real sales came from.
    ("best-bedding-essentials", "&#x1F6CF;", "Best Bedding Essentials",
     "6 verified picks &mdash; updated daily"),
    ("best-sheet-sets", "&#x1F9F5;", "Best Sheet Sets",
     "6 verified picks &mdash; updated daily"),
    ("best-blackout-curtains", "&#x1FA9F;", "Best Blackout Curtains",
     "6 verified picks &mdash; updated daily"),
    ("best-bath-towels-and-linens", "&#x1F9FB;", "Bath Towels &amp; Linens",
     "6 verified picks &mdash; updated daily"),
]

MARKER = "<!-- verified-hubs-v2 -->"


def main() -> int:
    html = page.read_text()
    if MARKER in html:
        print("  links.html: verified hubs already present")
        return 0

    anchor = '    <div class="section-label">Latest Posts</div>'
    if anchor not in html:
        print("  links.html: anchor not found — NOT modified")
        return 1

    cards = [MARKER, '    <div class="section-label">Shop Verified Picks</div>', ""]
    for slug, icon, title, sub in HUBS:
        cards.append(f'    <a href="/blog/posts/{slug}.html" class="link-card">')
        cards.append(f'      <div class="link-icon">{icon}</div>')
        cards.append('      <div class="link-text">')
        cards.append(f'        <div class="link-title">{title}</div>')
        cards.append(f'        <div class="link-subtitle">{sub}</div>')
        cards.append('      </div>')
        cards.append('      <div class="link-arrow">&#8250;</div>')
        cards.append('    </a>')
        cards.append("")

    html = html.replace(anchor, "\n".join(cards) + "\n" + anchor, 1)
    page.write_text(html)
    print(f"  links.html: inserted {len(HUBS)} verified-hub cards above Latest Posts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
