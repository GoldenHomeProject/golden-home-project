#!/usr/bin/env python3
"""GHP daily trending-products roundup — fresh content every day.

WHY: GHP kept recycling a fixed evergreen product set (under-sink organizers, couch
covers) → $0 sales. The real demand is whatever is actually topping Amazon's charts
today (cheap drinkware + high-use gadgets). This scrapes Amazon Best Sellers LIVE
(public pages; the Pi's residential IP is not bot-blocked, unlike GH Actions runners),
keeps only the proven-demand winners, EXCLUDES anything featured recently so every day
is genuinely new, and REFRESHES one evergreen per-category page (see EVERGREEN).

Pipeline:  scrape best-sellers -> filter -> de-dupe vs featured history -> pick N
           -> refresh the category's evergreen page + blog index + picks JSON
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
import unicodedata
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
    ("Home Storage",     "home",      "https://www.amazon.com/gp/bestsellers/home-garden/3610841/"),
    ("Home Décor",       "home",      "https://www.amazon.com/gp/bestsellers/home-garden/1063278/"),
    ("Home",             "home",      "https://www.amazon.com/gp/bestsellers/home-garden/"),
    # Coffee & Tea REMOVED 2026-07-31: the node yields 0 picks under the $5-35 /
    # 4.5star / 5k-review filter — coffee gear is either consumable pods and beans
    # (commodity-blocked, ~$0.20 commission) or machines well over $35. A category
    # that cannot fill an honest page should not have one.
    ("Bath",             "home",      "https://www.amazon.com/gp/bestsellers/home-garden/1063236/"),
    ("Cleaning",         "home",      "https://www.amazon.com/gp/bestsellers/home-garden/10802561/"),
]
# EVERGREEN consolidation (2026-07-31). Until now this script minted a NEW dated URL
# every single day — 11 near-identical "Best-Sellers Everyone's Buying Right Now" pages
# that targeted no search query and split the domain's ranking signal. Search Console
# showed the result: 108 impressions / 8 clicks in 90 days at average position 36.9,
# across just 14 queries, 12 of them brand-name lookups. Templated daily URLs are also
# precisely the pattern Google's scaled-content-abuse policy describes, so the bloat was
# plausibly suppressing the whole domain.
#
# Now each category owns ONE permanent URL that targets a REAL head query (every phrase
# below was confirmed to appear verbatim in Google autocomplete on 2026-07-31) and gets
# REFRESHED daily with live best-seller data. One page compounds authority, freshness
# and internal links instead of thirty pages competing with each other — and the daily
# refresh still gives Pinterest/social something new to post.
EVERGREEN = {
    "Kitchen":      ("best-kitchen-gadgets",               "best kitchen gadgets"),
    "Home Storage": ("best-storage-bins",                  "best storage bins"),
    "Home Décor":   ("best-home-decor-finds",              "best home decor finds"),
    "Home":         ("best-home-organization-products",    "best home organization products"),
    "Bath":         ("best-bathroom-essentials",           "best bathroom essentials"),
    "Cleaning":     ("best-cleaning-supplies",             "best cleaning supplies"),
}

# Node IDs above were READ off Amazon's own Best Sellers nav on 2026-07-25, not guessed.
# The old "Kitchen Gadget" node (kitchen/2402456011) returned exactly 1 item and was
# replaced with the verified Home Décor chart.
# The previous "Cleaning" node (hpc/3760931) was a Health & Personal Care chart: it served
# creatine, eye drops and acne wash for a post headlined "Cleaning Best-Sellers".
# Storage (3610841), Bath (1063236) and Cleaning (10802561) are the verified home nodes.

# Proven-demand filter — the profile that actually converts (cheap, high-rating,
# low-return impulse buys with real review depth).
MIN_PRICE, MAX_PRICE = 5.0, 35.0
MIN_RATING = 4.5
MIN_REVIEWS = 5000
PICKS_PER_POST = 6
FRESH_WINDOW_DAYS = 21          # legacy: only consulted if EVERGREEN_IGNORE_HISTORY is False
EVERGREEN_IGNORE_HISTORY = True  # see pick_fresh() — evergreen pages must show today's truth

# Commodity/consumable exclusion. Amazon's Cleaning + Grocery charts are dominated by
# single-use staples (toilet paper, paper plates, trash bags). They top the charts because
# everyone rebuys them on Subscribe & Save -- NOT because anyone clicks a blog to find
# them. A $6.99 pack at ~3% is ~$0.21 and zero buyer intent from content, so they crowd
# out the actual earners. Added 2026-07-25 after the first live run published toilet paper.
COMMODITY_BLOCK = re.compile(
    r"\b("
    r"toilet paper|bath tissue|paper towel|paper plate|paper bowl|napkin|facial tissue|"
    r"trash bag|garbage bag|storage bag|sandwich bag|freezer bag|ziploc|"
    r"aluminum foil|plastic wrap|parchment paper|"
    r"laundry detergent|fabric softener|dryer sheet|dish soap|dishwasher pod|"
    r"disinfecting wipe|cleaning wipe|makeup remover|micellar|facial wipe|baby wipe|"
    r"flushable wipe|wet wipe|prep pad|alcohol pad|cotton round|disposable towel|"
    r"diaper|tampon|pad liner|toothpaste|deodorant|shampoo|conditioner|body wash|"
    r"battery|batteries|k-cup|coffee pod|bottled water|"
    r"refill|refills|value pack of|count pack"
    r")e?s?\b",          # e?s? so "paper towels"/"paper plates"/"wipes" match too
    re.I,
)

# Off-brand exclusion. The "Cleaning" node (hpc/3760931) actually serves Amazon's
# Health & Personal Care chart, so a run on 2026-07-25 proposed creatine powder,
# LUMIFY eye drops and The Ordinary toner under a "Cleaning Best-Sellers" headline.
# GHP is a HOME brand: supplements, medicine and skincare don't belong on it at any
# price, and health claims are a compliance problem we have no reason to take on.
OFF_BRAND_BLOCK = re.compile(
    r"\b("
    r"creatine|magnesium|melatonin|collagen|probiotic|vitamin|supplement|multivitamin|"
    r"protein powder|pre-?workout|electrolyte|ashwagandha|fish oil|biotin|"
    r"eye drop|nasal|allergy relief|ibuprofen|acetaminophen|antacid|laxative|"
    r"serum|retinol|hyaluronic|glycolic|salicylic|niacinamide|toner pad|"
    r"moisturizer|sunscreen|acne|wrinkle|lash|mascara|foundation|concealer"
    r")e?s?\b",
    re.I,
)

# Amazon titles front-load the product and back-load marketing ("...Batteries Included",
# "...like parchment paper"). Matching the whole string blocked a legitimate kitchen scale
# for mentioning its batteries, so only judge the product-name portion.
TITLE_HEAD_CHARS = 60

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
        head = (it.get("title") or "")[:TITLE_HEAD_CHARS]
        if COMMODITY_BLOCK.search(head):
            print(f"  [skip] {a} commodity/consumable — {head}")
            continue
        if OFF_BRAND_BLOCK.search(head):
            print(f"  [skip] {a} off-brand (health/beauty) — {head}")
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


def _slugify(label: str) -> str:
    """ASCII-safe URL slug. 'Home Décor' must not become /posts/...home-décor... —
    non-ASCII in a path gets percent-encoded and breaks shares and analytics."""
    folded = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", folded.lower())).strip("-")


_STOPWORDS = {
    "the", "and", "for", "with", "pack", "set", "count", "inch", "large", "small", "clear",
    "black", "white", "home", "heavy", "duty", "extra", "premium", "upgrade", "pcs", "piece",
}


def _type_key(title: str) -> set[str]:
    """Significant words of a title, used to detect 'same kind of thing'."""
    words = re.findall(r"[a-z]+", (title or "").lower())
    return {w for w in words if len(w) > 3 and w not in _STOPWORDS}


def _varied(candidates: list[dict], limit: int) -> list[dict]:
    """Take `limit` picks, skipping near-duplicates of what's already chosen.

    Amazon category charts cluster hard: the Bath chart's top 6 were five shower
    curtains/liners. A roundup of one product type six times is not a roundup and gives a
    reader nothing to buy. Two shared significant words == same kind of product; fall back
    to the strict order if variety can't fill the post.
    """
    picks, keys = [], []
    for c in candidates:
        k = _type_key(c.get("title", ""))
        if any(len(k & prev) >= 2 for prev in keys):
            continue
        picks.append(c)
        keys.append(k)
        if len(picks) >= limit:
            break
    if len(picks) < limit:                      # variety guard starved the post → relax it
        for c in candidates:
            if c not in picks:
                picks.append(c)
            if len(picks) >= limit:
                break
    return picks[:limit]


def pick_fresh(qualified: list[dict], history: dict, today: date,
               primary_label: str | None = None) -> list[dict]:
    def recent(asin):
        d = history.get(asin)
        if not d:
            return False
        try:
            return (today - date.fromisoformat(d)).days < FRESH_WINDOW_DAYS
        except ValueError:
            return False
    # The 21-day "don't re-feature" rule existed for the old model, where every day
    # minted a NEW url and repeating a product made the new page look recycled. An
    # evergreen page is the opposite: "best cleaning supplies" must list what is
    # genuinely selling best TODAY, and the true answer often is the same product as
    # last week. Enforcing novelty here starved whole categories — Cleaning and
    # Coffee & Tea returned 0 eligible picks because their charts had been consumed.
    # History is still recorded; it just no longer vetoes a pick.
    fresh = list(qualified) if EVERGREEN_IGNORE_HISTORY else [
        q for q in qualified if not recent(q["asin"])]
    # Category coherence: we scrape a neighbour node too, purely for pool depth, but the
    # headline names ONE category. Exhaust the primary node before borrowing, or the post
    # ends up like 2026-07-25 -- a "Cleaning" roundup listing tumblers and makeup wipes.
    if primary_label:
        fresh.sort(key=lambda q: 0 if q.get("cat_label") == primary_label else 1)
    picks = _varied(fresh, PICKS_PER_POST)
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
    slug, target_query = EVERGREEN.get(
        cat_label, (f"best-{_slugify(cat_label)}-finds", f"best {cat_label.lower()} finds"))
    url = f"https://goldenhomeproject.com/blog/posts/{slug}.html"
    headline = target_query.title().replace(" And ", " and ")
    title = (f"{headline}: {n} Picks Under ${int(MAX_PRICE)} "
             f"(Updated {today.strftime('%B %Y')})")
    desc = (f"The {target_query} on Amazon right now — {n} picks under ${int(MAX_PRICE)}, "
            f"each with thousands of reviews. Updated {today.strftime('%B %-d, %Y')}.")

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

    # Evergreen pages keep their ORIGINAL publish date and only move dateModified.
    # Re-stamping datePublished every refresh would claim the page is new each day,
    # which is both untrue and a pattern search engines discount.
    first_published = ymd
    existing = BLOG_POSTS / f"{slug}.html"
    if existing.exists():
        m = re.search(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})"', existing.read_text())
        if m:
            first_published = m.group(1)

    schema_article = json.dumps({"@context": "https://schema.org", "@type": "Article",
        "headline": title, "datePublished": first_published, "dateModified": ymd,
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
<meta property="og:site_name" content="Golden Home Project">
<meta property="og:image" content="https://goldenhomeproject.com/images/og-default.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
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
    ap.add_argument("--category", help="override the day-of-year rotation "
                    "(used to build every evergreen page in one sitting instead of "
                    "waiting a week for the rotation to come around)")
    ap.add_argument("--date", help="override date YYYY-MM-DD (test)")
    args = ap.parse_args()

    today = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    # rotate category by day-of-year so the theme cycles through the week
    cat_label, _, _ = CATEGORY_ROTATION[today.toordinal() % len(CATEGORY_ROTATION)]
    if getattr(args, "category", None):
        for c in CATEGORY_ROTATION:
            if c[0].lower() == args.category.lower():
                cat_label = c[0]

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
        if args.category:
            match = [i for i, c in enumerate(CATEGORY_ROTATION)
                     if c[0].lower() == args.category.lower()]
            if not match:
                print(f"[trending] unknown category {args.category!r}; "
                      f"choose from: {', '.join(c[0] for c in CATEGORY_ROTATION)}")
                return 1
            idx = match[0]
        nodes = [CATEGORY_ROTATION[idx], CATEGORY_ROTATION[(idx + 1) % len(CATEGORY_ROTATION)]]
        raw = scrape_bestsellers(nodes)
        print(f"[trending] scraped {len(raw)} raw items")
        qualified = qualify(raw)
        print(f"[trending] {len(qualified)} passed the ${int(MIN_PRICE)}-${int(MAX_PRICE)} / "
              f"{MIN_RATING}star / {MIN_REVIEWS}+reviews filter")
        history = load_history()
        picks = pick_fresh(qualified, history, today, primary_label=cat_label)
        # The label is PINNED to the primary category. It used to follow the majority
        # of picks, which was harmless when the label only shaped a headline — but the
        # label now selects the evergreen FILENAME, so a "Cleaning" run whose picks
        # skewed to the neighbour node overwrote best-kitchen-gadgets.html and left the
        # cleaning page stale forever. Borrowed picks are fine; a borrowed identity is not.
        primary = [p for p in picks if p.get("cat_label") == cat_label]
        if len(primary) < 3:
            print(f"[trending] only {len(primary)} of {len(picks)} picks are genuinely "
                  f"{cat_label} — refusing to publish a mislabelled page. "
                  f"Widen the filter or check the {cat_label} node.")
            return 0

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
