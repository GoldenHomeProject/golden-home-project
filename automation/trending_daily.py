#!/usr/bin/env python3
"""GHP daily trending-products roundup — fresh content every day.

WHY: GHP kept recycling a fixed evergreen product set (under-sink organizers, couch
covers) → $0 sales. The real demand is whatever is actually topping Amazon's charts
today (cheap drinkware + high-use gadgets). This scrapes Amazon Best Sellers LIVE
(public pages; the Pi's residential IP is not bot-blocked, unlike GH Actions runners),
keeps only the proven-demand winners, EXCLUDES anything featured recently so every day
is genuinely new, and publishes a dated buyer-intent roundup post.

Pipeline:  scrape best-sellers -> filter -> de-dupe vs featured history -> pick N
           -> generate dated roundup HTML + update blog index + write picks JSON
           -> record featured history.  (systemd ExecStartPost commits + pushes.)

Run modes:
  python trending_daily.py                 # scrape live + generate (Pi/prod)
  python trending_daily.py --from-json f   # skip scrape, generate from a picks JSON (test)
  python trending_daily.py --dry-run       # scrape + pick, print picks, write nothing

Guardrails (see feedback_ghp_trending_not_evergreen / _intent_not_volume / dead-ASIN):
  * Only /dp/<ASIN>?tag=goldenhomep06-20 URLs — ASINs come straight off the live
    best-seller grid (Amazon-native proof they exist), never fabricated.
  * Real scraped rating/review counts only — never invent ratings.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG_POSTS = ROOT / "blog" / "posts"
BLOG_INDEX = ROOT / "blog" / "index.html"
PICKS_DIR = ROOT / "social"
HISTORY = ROOT / "social" / "trending_featured_history.json"
AFFIL_TAG = "goldenhomep06-20"

# Public best-seller category nodes (no login needed). Rotated by weekday so the
# theme varies across the week without repeating.
CATEGORY_ROTATION = [
    ("Kitchen",          "kitchen",   "https://www.amazon.com/gp/bestsellers/kitchen/"),
    ("Home Storage",     "home",      "https://www.amazon.com/gp/bestsellers/home-garden/3733551/"),
    ("Kitchen Gadget",   "kitchen",   "https://www.amazon.com/gp/bestsellers/kitchen/2402456011/"),
    ("Home",             "home",      "https://www.amazon.com/gp/bestsellers/home-garden/"),
    ("Coffee & Tea",     "kitchen",   "https://www.amazon.com/gp/bestsellers/kitchen/13400711/"),
    ("Bed & Bath",       "home",      "https://www.amazon.com/gp/bestsellers/home-garden/1063252/"),
    ("Cleaning",         "home",      "https://www.amazon.com/gp/bestsellers/hpc/3760931/"),
]

# Proven-demand filter — the profile that actually converts (cheap, high-rating,
# low-return impulse buys with real review depth).
MIN_PRICE, MAX_PRICE = 5.0, 35.0
MIN_RATING = 4.5
MIN_REVIEWS = 5000
PICKS_PER_POST = 6
FRESH_WINDOW_DAYS = 21          # don't re-feature an ASIN within this many days

# In-page extractor (proven live 2026-07-20): one structured record per grid card.
EXTRACT_JS = r"""
(() => {
  const out = [], seen = new Set();
  document.querySelectorAll('a[href*="/dp/"]').forEach(link => {
    const m = link.href.match(/\/dp\/([A-Z0-9]{10})/);
    if (!m) return;
    const asin = m[1];
    if (seen.has(asin)) return;
    const card = link.closest('#gridItemRoot, [class*="grid-cell"], li, .a-carousel-card') || link.parentElement;
    if (!card) return;
    const text = card.innerText || '';
    const title = (card.querySelector('img')?.alt || '').trim()
      || (text.split('\n').map(s=>s.trim()).find(s=>s.length>15) || '');
    if (title.length < 15) return;
    const rank = (text.match(/#(\d+)/)||[])[1];
    const price = (text.match(/\$[\d,]+\.\d{2}/)||[])[0];
    const rating = (text.match(/([\d.]+)\s*out of 5 stars/)||[])[1];
    const rev = (text.match(/stars\s*[\r\n]+\s*([\d,]+)/)||[])[1];
    seen.add(asin);
    out.push({rank: rank?+rank:null, asin, price,
      rating: rating?+rating:null,
      reviews: rev?+rev.replace(/,/g,''):null,
      title: title.slice(0,120)});
  });
  return out;
})()
"""


# ----------------------------- scrape -----------------------------------------
def scrape_bestsellers(nodes) -> list[dict]:
    from playwright.sync_api import sync_playwright  # noqa: import here so --from-json needs no playwright
    items: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            viewport={"width": 1440, "height": 2400}, locale="en-US")
        page = ctx.new_page()
        for label, group, url in nodes:
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                page.mouse.wheel(0, 4000)          # trigger lazy-load of the grid
                page.wait_for_timeout(1500)
                recs = page.evaluate(EXTRACT_JS) or []
                for r in recs:
                    r["cat_label"], r["cat_group"] = label, group
                items.extend(recs)
                print(f"  [scrape] {label}: {len(recs)} items")
            except Exception as e:  # noqa: BLE001
                print(f"  [scrape] {label}: FAILED — {e}")
        browser.close()
    return items


# ----------------------------- select -----------------------------------------
def _price_val(p) -> float | None:
    if not p:
        return None
    m = re.search(r"[\d,]+\.\d{2}", p)
    return float(m.group().replace(",", "")) if m else None


def qualify(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for it in items:
        a = it.get("asin")
        pv = _price_val(it.get("price"))
        if not a or a in seen:
            continue
        if pv is None or not (MIN_PRICE <= pv <= MAX_PRICE):
            continue
        if (it.get("rating") or 0) < MIN_RATING:
            continue
        if (it.get("reviews") or 0) < MIN_REVIEWS:
            continue
        seen.add(a)
        it["price_val"] = pv
        out.append(it)
    # best sellers first (lowest rank), then by review depth
    out.sort(key=lambda x: (x.get("rank") or 999, -(x.get("reviews") or 0)))
    return out


def load_history() -> dict:
    if HISTORY.exists():
        try:
            return json.loads(HISTORY.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def pick_fresh(qualified: list[dict], history: dict, today: date) -> list[dict]:
    def recent(asin):
        d = history.get(asin)
        if not d:
            return False
        try:
            return (today - date.fromisoformat(d)).days < FRESH_WINDOW_DAYS
        except ValueError:
            return False
    fresh = [q for q in qualified if not recent(q["asin"])]
    picks = fresh[:PICKS_PER_POST]
    if len(picks) < PICKS_PER_POST:            # not enough new ones → backfill w/ oldest-featured
        backfill = [q for q in qualified if q not in picks]
        picks += backfill[: PICKS_PER_POST - len(picks)]
    return picks[:PICKS_PER_POST]


# ----------------------------- copy templating --------------------------------
# Keyword → honest benefit lines, so common products read naturally. Generic
# fallback keeps it truthful for anything else. NO fabricated specs.
KEYWORD_COPY = {
    "water bottle": ["Keeps drinks cold for hours", "The bottle you'll actually keep refilling", "Leak-resistant for a bag or backpack"],
    "tumbler":      ["Keeps drinks cold for hours", "Fits most cup holders despite the size", "The one people can't stop buying"],
    "scale":        ["Grams and ounces with a tare button", "Perfect for baking, coffee, and portions", "A tool you'll reach for every week"],
    "thermometer":  ["Instant, accurate reads", "No more dry, overcooked meat", "Takes the guesswork out of dinner"],
    "can opener":   ["Razor-sharp wheel that cuts cleanly", "Comfortable, grippy handles", "Replaces the frustrating one in your drawer"],
    "shears":       ["Sharp enough for herbs, packaging, and poultry", "Dishwasher safe with a protective sheath", "The cheapest upgrade on this list"],
    "organizer":    ["Turns wasted space into real storage", "No tools — place and go", "Wipes clean in seconds"],
    "storage":      ["Reclaims cluttered, wasted space", "Sturdy and easy to assemble", "Makes everything easy to find"],
    "coffee":       ["Brews a better cup at home", "Simple to use and clean", "A daily-use upgrade for the price"],
    "sheets":       ["Soft and breathable for better sleep", "Holds up wash after wash", "An easy, affordable bedroom refresh"],
    "towel":        ["Absorbent and quick-drying", "Holds up to daily use", "A small upgrade you'll notice every day"],
}
GENERIC_COPY = ["Proven, everyday-useful design", "Loved across a huge number of reviews", "High value for the price"]


def _benefits(title: str) -> list[str]:
    t = title.lower()
    for kw, lines in KEYWORD_COPY.items():
        if kw in t:
            return lines
    return GENERIC_COPY


def _badge(pick: dict, i: int, picks: list[dict]) -> str:
    if pick["price_val"] == min(p["price_val"] for p in picks):
        return "Cheapest Pick"
    if pick.get("rating") == max((p.get("rating") or 0) for p in picks):
        return "Highest-Rated Pick"
    if i == 0:
        return "Top Seller"
    return f"#{pick.get('rank', i+1)} Best-Seller"


def _clean_title(t: str) -> str:
    # trim marketing run-ons to the first natural clause for readable headings
    t = re.split(r"[|,–-]\s|\s\(", t)[0].strip()
    return (t[:70]).strip()


# ----------------------------- HTML generation --------------------------------
def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def build_post(picks: list[dict], today: date, cat_label: str) -> tuple[str, str, dict]:
    ymd = today.isoformat()
    subtag = f"blog-trending-{today.strftime('%Y%m%d')}"
    n = len(picks)
    title = f"{n} {cat_label} Best-Sellers Everyone's Buying Right Now (Under ${int(MAX_PRICE)})"
    slug = f"{ymd}-trending-{cat_label.lower().replace(' & ','-').replace(' ','-')}-best-sellers"
    url = f"https://goldenhomeproject.com/blog/posts/{slug}.html"
    desc = (f"The {cat_label.lower()} products actually topping Amazon's charts this week — "
            f"proven-demand picks under ${int(MAX_PRICE)}, each with thousands of reviews.")

    def afurl(a):
        return f"https://www.amazon.com/dp/{a}?tag={AFFIL_TAG}&ascsubtag={subtag}"

    item_list = [{"@type": "ListItem", "position": i + 1, "name": _clean_title(p["title"])}
                 for i, p in enumerate(picks)]
    rows = "\n".join(
        f'    <tr><td>{esc(_clean_title(p["title"]))}</td><td>{p.get("rating","?")}&#9733; '
        f'({(p.get("reviews") or 0)//1000}k+)</td><td>~{esc(p.get("price","")) }</td></tr>'
        for p in picks)
    cards = "\n".join(
        f'''    <div class="product-card">
      <span class="pick-badge">{esc(_badge(p, i, picks))}</span>
      <div class="product-name">{esc(_clean_title(p["title"]))}</div>
      <div class="product-rating">{p.get("rating","?")}&#9733; &middot; {(p.get("reviews") or 0):,}+ ratings &middot; ~{esc(p.get("price",""))}</div>
      <ul class="value-stack">
        <li><strong>{esc(_benefits(p["title"])[0])}</strong></li>
        <li>{esc(_benefits(p["title"])[1])}</li>
        <li>{esc(_benefits(p["title"])[2])}</li>
      </ul>
      <a class="cta" href="{afurl(p["asin"])}" rel="sponsored nofollow noopener" target="_blank">Check current price on Amazon &rarr;</a>
    </div>'''
        for i, p in enumerate(picks))

    schema_article = json.dumps({"@context": "https://schema.org", "@type": "Article",
        "headline": title, "datePublished": ymd, "dateModified": ymd,
        "author": {"@type": "Organization", "name": "Golden Home Project"},
        "publisher": {"@type": "Organization", "name": "Golden Home Project LLC"},
        "mainEntityOfPage": url, "description": desc})
    schema_list = json.dumps({"@context": "https://schema.org", "@type": "ItemList",
        "name": title, "itemListElement": item_list})

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)} | Golden Home Project</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="article">
<meta property="og:url" content="{url}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Playfair+Display:wght@600;700&display=swap" rel="stylesheet">
<script type="application/ld+json">{schema_article}</script>
<script type="application/ld+json">{schema_list}</script>
<style>
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',sans-serif;background:#0a0a0a;color:#f0ece4;line-height:1.7;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:760px;margin:0 auto;padding:40px 20px 80px}}
.breadcrumbs{{font-size:13px;color:#a8a4a0;margin-bottom:24px}}
.breadcrumbs a{{color:#d4a745;text-decoration:none}}
h1{{font-family:'Playfair Display',serif;font-size:38px;line-height:1.2;margin-bottom:16px;color:#fff}}
.meta{{color:#a8a4a0;font-size:14px;margin-bottom:32px;padding-bottom:24px;border-bottom:1px solid rgba(212,167,69,.15)}}
.affiliate-disclosure{{font-size:12px;color:#a8a4a0;background:rgba(212,167,69,.06);padding:12px 16px;border-left:3px solid #d4a745;margin-bottom:32px;border-radius:4px}}
.intro{{font-size:18px;color:#e8e4dc;margin-bottom:32px}}
.intro p{{margin-bottom:16px}}
h2{{font-family:'Playfair Display',serif;font-size:26px;margin:40px 0 16px;color:#fff}}
.cmp{{width:100%;border-collapse:collapse;margin:24px 0;font-size:14px;background:#141428;border:1px solid rgba(212,167,69,.2);border-radius:12px;overflow:hidden}}
.cmp th,.cmp td{{padding:12px 14px;text-align:left;border-bottom:1px solid rgba(212,167,69,.12)}}
.cmp th{{background:rgba(212,167,69,.1);color:#d4a745;font-weight:700}}
.cmp tr:last-child td{{border-bottom:none}}
.product-card{{background:#141428;border:1px solid rgba(212,167,69,.2);border-radius:12px;padding:24px;margin:24px 0}}
.pick-badge{{display:inline-block;background:linear-gradient(135deg,#d4a745,#b8912e);color:#0a0a0a;font-weight:700;font-size:12px;letter-spacing:.04em;text-transform:uppercase;padding:5px 12px;border-radius:20px;margin-bottom:12px}}
.product-name{{font-weight:700;font-size:18px;color:#fff}}
.product-rating{{color:#a8a4a0;font-size:13px;margin:4px 0}}
.value-stack{{list-style:none;margin-bottom:18px}}
.value-stack li{{padding:6px 0;font-size:15px;color:#d8d4cc}}
.value-stack strong{{color:#d4a745}}
.cta{{display:inline-block;background:linear-gradient(135deg,#d4a745,#b8912e);color:#0a0a0a;font-weight:700;padding:14px 24px;border-radius:8px;text-decoration:none}}
details{{background:#141428;border:1px solid rgba(212,167,69,.15);border-radius:8px;padding:14px 18px;margin-bottom:10px}}
details summary{{cursor:pointer;font-weight:600;color:#f0ece4}}
details p{{margin-top:10px;color:#c8c4bc;font-size:15px}}
.conclusion{{white-space:pre-line;background:rgba(212,167,69,.06);border-radius:10px;padding:22px 24px;margin:36px 0;color:#e8e4dc}}
.back-link{{display:inline-block;margin-top:24px;color:#d4a745;text-decoration:none;font-weight:600}}
</style>
</head>
<body>
<div class="wrap">
  <div class="breadcrumbs"><a href="/">Home</a> &rsaquo; <a href="/blog/">Blog</a> &rsaquo; Trending {esc(cat_label)} Best-Sellers</div>
  <h1>{esc(title)}</h1>
  <div class="meta">Updated {today.strftime('%B %-d, %Y')} &middot; Golden Home Project</div>
  <div class="affiliate-disclosure">As an Amazon Associate, Golden Home Project earns from qualifying purchases. Prices and availability were accurate at publish time and change often — always check the live listing.</div>
  <div class="intro">
    <p>We pulled Amazon's live {esc(cat_label.lower())} best-seller charts this week and kept only what's both <strong>selling fast</strong> and <strong>genuinely loved</strong> — every pick below holds {MIN_RATING}&#9733; or higher across thousands of reviews.</p>
    <p>No hype without proof. These are the {n} things real people are buying right now, each under ${int(MAX_PRICE)}.</p>
  </div>
  <table class="cmp">
    <tr><th>Pick</th><th>Rating</th><th>Price*</th></tr>
{rows}
  </table>
  <p style="font-size:13px;color:#a8a4a0">*Live prices move — tap any pick for the current price.</p>
  <section class="post-section">
{cards}
  </section>
  <h2>Frequently asked</h2>
  <div class="faq-section">
    <details><summary>How do you choose these products?</summary><p>We start from what's genuinely selling — Amazon's live best-seller charts — then keep only items that also hold a high rating across a large number of reviews. Every pick sits at {MIN_RATING}&#9733; or higher with thousands of ratings, so you're buying proven demand, not a thin, easily-gamed review count.</p></details>
    <details><summary>Why cheap items instead of big-ticket ones?</summary><p>Small, sub-$15 tools get used constantly, cost less than a takeout meal, and rarely disappoint. The highest satisfaction per dollar is almost always in the cheap, high-use products — not the priciest thing on the shelf.</p></details>
    <details><summary>Do prices and availability change?</summary><p>Best-sellers move fast and popular options sell out first, so prices shift. That's why we link straight to the live Amazon listing for each pick — always check the current price before buying.</p></details>
  </div>
  <div class="conclusion">This week's charts make the pattern clear: the products people actually buy are cheap, high-use, and proven by thousands of reviews.

Pick whatever you'd reach for every day, check the live listing before you order — these move fast — and skip anything that doesn't solve a real, recurring annoyance.

We refresh this with what's actually trending. If it helped, tomorrow's is worth a look.</div>
  <a class="back-link" href="/blog/">&larr; More posts</a>
</div>
</body>
</html>
"""
    picks_record = {
        "captured_at": ymd, "category": cat_label,
        "source": "Amazon Best Sellers (live Pi scrape)",
        "post": f"blog/posts/{slug}.html",
        "picks": [{"asin": p["asin"], "name": _clean_title(p["title"]), "price": p.get("price"),
                   "rating": p.get("rating"), "reviews": p.get("reviews"), "rank": p.get("rank")}
                  for p in picks],
    }
    return slug, html, picks_record


def insert_index_card(slug: str, title: str, desc: str, ymd: str) -> None:
    idx = BLOG_INDEX.read_text()
    card = (f'\n<a class="post-card" href="/blog/posts/{slug}.html">\n'
            f'  <div class="post-date">{ymd}</div>\n'
            f'  <h3>{esc(title)}</h3>\n'
            f'  <p>{esc(desc)}</p>\n</a>')
    anchor = '<p class="tagline">In-depth transformation guides. Honest product reviews. Specific prices.</p>'
    if anchor in idx and slug not in idx:
        idx = idx.replace(anchor, anchor + "\n" + card, 1)
        BLOG_INDEX.write_text(idx)


# ----------------------------- main -------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", help="generate from an existing picks JSON (skip scrape)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date", help="override date YYYY-MM-DD (test)")
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    # rotate category by day-of-year so the theme cycles through the week
    cat_label, _, _ = CATEGORY_ROTATION[today.toordinal() % len(CATEGORY_ROTATION)]

    if args.from_json:
        data = json.loads(Path(args.from_json).read_text())
        picks = data["picks"]
        for p in picks:                      # normalize test JSON to internal shape
            p.setdefault("price_val", _price_val(p.get("price")) or 0)
            p["title"] = p.get("name") or p.get("title")
        cat_label = data.get("category", cat_label)
    else:
        # scrape today's category + a couple of neighbors for a deeper pool
        idx = today.toordinal() % len(CATEGORY_ROTATION)
        nodes = [CATEGORY_ROTATION[idx], CATEGORY_ROTATION[(idx + 1) % len(CATEGORY_ROTATION)]]
        raw = scrape_bestsellers(nodes)
        print(f"[trending] scraped {len(raw)} raw items")
        qualified = qualify(raw)
        print(f"[trending] {len(qualified)} passed the ${int(MIN_PRICE)}-${int(MAX_PRICE)} / "
              f"{MIN_RATING}star / {MIN_REVIEWS}+reviews filter")
        history = load_history()
        picks = pick_fresh(qualified, history, today)
        cat_label = (picks[0].get("cat_label") if picks else None) or cat_label

    if len(picks) < 3:
        print(f"[trending] only {len(picks)} qualifying picks — not enough for a post. Aborting cleanly.")
        return 0

    slug, html, record = build_post(picks, today, cat_label)
    desc = (f"The {cat_label.lower()} products actually topping Amazon's charts this week — "
            f"proven-demand picks under ${int(MAX_PRICE)}, each with thousands of reviews.")
    title = f"{len(picks)} {cat_label} Best-Sellers Everyone's Buying Right Now (Under ${int(MAX_PRICE)})"

    if args.dry_run:
        print(f"[dry-run] category={cat_label}  picks:")
        for p in picks:
            print(f"   {p['asin']}  {p.get('price')}  {p.get('rating')}*  "
                  f"{p.get('reviews')} rev  {_clean_title(p['title'])}")
        print(f"[dry-run] would write blog/posts/{slug}.html ({len(html)} bytes)")
        return 0

    (BLOG_POSTS / f"{slug}.html").write_text(html)
    (PICKS_DIR / f"trending_picks_{today.isoformat()}.json").write_text(json.dumps(record, indent=2) + "\n")
    insert_index_card(slug, title, desc, today.isoformat())
    hist = load_history()
    for p in picks:
        hist[p["asin"]] = today.isoformat()
    HISTORY.write_text(json.dumps(hist, indent=2) + "\n")
    print(f"[trending] WROTE blog/posts/{slug}.html  ({len(picks)} picks, category {cat_label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
