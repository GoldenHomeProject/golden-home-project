"""GHP ASIN Discoverer — runs after Trend Scout.

For each product opportunity surfaced by Trend Scout (social/trend_feed.json),
if it is not already covered by the live registry or vetted pool:
  1. Search amazon.com via headless Playwright
  2. Pick the top organic (non-sponsored) result with >= MIN_STARS and >= MIN_REVIEWS
  3. Navigate to /dp/ASIN and verify it renders a real product page (not a
     captcha / "Sorry, this page is not available" / dead listing)
  4. Append the verified ASIN to dm_keyword_registry.json `vetted[]` pool

This is the missing link between Trend Scout (Agent 1) and Blog/Content
production: it grows the verified-ASIN catalog automatically so the downstream
agents always have a payable affiliate URL.

Guardrails:
- MAX_NEW_PER_RUN caps how many ASINs we add per invocation
- MAX_VETTED_POOL caps total pool size so we don't accumulate forever
- All verification is conservative: any failure -> skip, never silently
  fall back to a search URL (which would not pay this account)
- Per feedback_ghp_no_search_urls.md: only /dp/ASIN?tag= URLs are emitted
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from agent_log import append_log_entry  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "social" / "dm_keyword_registry.json"
TREND_FEED = ROOT / "social" / "trend_feed.json"
MOVERS_CACHE = ROOT / "automation" / "trends" / "movers_shakers_latest.json"
REDDIT_CACHE = ROOT / "automation" / "trends" / "reddit_latest.json"
AMAZON_TAG = "goldenhomep06-20"

# Subreddits the Pi-side Reddit fetcher samples. Trend Scout used to fetch
# these directly from GH Actions, but Reddit started 403'ing GH runner IPs
# (2026-05-27). The Pi has a residential IP that still works. We write the
# cache here and Trend Scout reads it on its next morning run.
REDDIT_SUBS = [
    "BuyItForLife",
    "HomeImprovement",
    "DiWHY",
    "organization",
    "HomeDecorating",
]

# Amazon Best Sellers nodes we sample each Pi run. Trend Scout reads the
# cached output the next morning. We keep this short to be a good citizen on
# Amazon traffic. The /movers-and-shakers/ pages have a different layout that
# our card selector doesn't match — left for a future selector pass; the
# /bestsellers/ pages give plenty of signal in the meantime.
MOVERS_NODES = [
    ("home_storage",  "https://www.amazon.com/gp/bestsellers/home-garden/3733551/"),
    ("kitchen",       "https://www.amazon.com/gp/bestsellers/kitchen/"),
]

MAX_NEW_PER_RUN = 5
MAX_VETTED_POOL = 30
MIN_REVIEWS = 100
MIN_STARS = 4.0

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# Glue words that accumulate noise but don't disambiguate products. Numeric
# tokens (sizes, pack counts) are also dropped via str.isdigit() below.
_COVERAGE_STOPWORDS = {
    "a", "an", "and", "or", "the", "of", "in", "on", "for", "with",
    "to", "by", "no", "non", "from", "at", "as", "is",
    "pack", "set", "size", "piece", "pieces", "pc", "pcs",
}


def _meaningful_tokens(text: str) -> set[str]:
    """Lowercase word tokens, minus stopwords and pure-digit tokens."""
    return {
        t for t in re.findall(r"\w+", (text or "").lower())
        if t and not t.isdigit() and t not in _COVERAGE_STOPWORDS
    }


def existing_coverage(reg: dict) -> tuple[list[set[str]], set[str], set[str]]:
    """Return (per-product token sets, lowercased categories, asins) already
    in the registry — used to skip opportunities we've already covered.

    Per-product (not unioned) so opportunity_is_covered can require that an
    opportunity match a SINGLE existing product substantially, not just hit
    a couple glue words spread across several unrelated products. The prior
    union approach false-positived 2 of 5 opps on 2026-05-27 (outdoor patio
    set caught on {'4','set'}; throw pillow covers caught on words drawn
    from sofa cover + hangers + pillow — three unrelated entries)."""
    per_product: list[set[str]] = []
    cats: set[str] = set()
    asins: set[str] = set()
    pool = list(reg.get("entries", [])) + list(reg.get("vetted", []))
    for e in pool:
        toks = _meaningful_tokens(e.get("product_name") or "")
        if e.get("keyword"):
            kw = e["keyword"].lower()
            if kw not in _COVERAGE_STOPWORDS and not kw.isdigit():
                toks.add(kw)
        if toks:
            per_product.append(toks)
        cats |= set(c.lower() for c in (e.get("categories") or []))
        if e.get("asin"):
            asins.add(e["asin"])
    return per_product, cats, asins


def opportunity_is_covered(
    opp: dict, per_product: list[set[str]], cats: set[str]
) -> bool:
    """Covered iff the opportunity overlaps substantially with ONE existing
    product (Jaccard-ish >= 0.5 on meaningful tokens AND >=2 token overlap)
    OR the opportunity's category exactly matches an existing category."""
    opp_toks = _meaningful_tokens(
        (opp.get("specific_product") or "") + " " + (opp.get("product_category") or "")
    )
    for prod_toks in per_product:
        overlap = opp_toks & prod_toks
        if len(overlap) < 2:
            continue
        denom = min(len(opp_toks), len(prod_toks))
        if denom and len(overlap) / denom >= 0.5:
            return True
    opp_cat = (opp.get("product_category") or "").lower().strip()
    if opp_cat and opp_cat in cats:
        return True
    return False


def parse_review_count(text: str) -> int:
    """'(6,190)' -> 6190; '(1.7K)' -> 1700; '' -> 0."""
    if not text:
        return 0
    t = text.strip().strip("()").upper().replace(",", "")
    if t.endswith("K"):
        try:
            return int(float(t[:-1]) * 1000)
        except ValueError:
            return 0
    digits = re.sub(r"[^\d]", "", t)
    return int(digits) if digits else 0


def parse_stars(text: str) -> float:
    """'4.7 out of 5 stars' -> 4.7."""
    if not text:
        return 0.0
    m = re.match(r"\s*([\d.]+)", text)
    return float(m.group(1)) if m else 0.0


def fetch_reddit_for_cache(subs: list[str], per_sub: int = 10) -> dict:
    """Pull /r/<sub>/top.json?t=day from each sub via stdlib urllib.

    NOTE (2026-05-31): Reddit now blocks this *and* GH Actions IPs at the
    network level — the .json API 403s regardless of User-Agent, and even the
    old.reddit HTML returns an empty #siteTable (200 but no posts) to this Pi's
    IP. There is no free, agent-only workaround (the official API needs an
    OAuth app the owner must register). This function is left in place because
    (a) IP blocks can lift, and (b) callers already degrade gracefully — on
    zero posts we keep the prior cache and Trend Scout falls back to Amazon
    Movers & Shakers, which is a stronger buyer-intent signal anyway.

    Returns the same shape Trend Scout previously built in-process:
        {fetched_at, subs: {sub: [{title, score, num_comments, url}, ...]}}
    """
    from urllib import request as _req
    out: dict[str, list[dict]] = {}
    for sub in subs:
        url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={per_sub}"
        req = _req.Request(url, headers={"User-Agent": "GHP-TrendScout/1.0 (Pi)"})
        try:
            with _req.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
        except Exception as e:
            print(f"  [reddit] /r/{sub} failed: {e}")
            continue
        posts = []
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            posts.append({
                "title": (p.get("title") or "")[:200],
                "score": p.get("score", 0),
                "num_comments": p.get("num_comments", 0),
                "url": f"https://reddit.com{p.get('permalink', '')}",
            })
        if posts:
            out[sub] = posts
            print(f"  [reddit] /r/{sub}: {len(posts)} posts")
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "subs": out,
    }


def search_amazon(page, query: str) -> Optional[dict]:
    """Search Amazon, return top organic non-sponsored result meeting thresholds.
    Returns dict {asin, title, stars, reviews, price} or None."""
    url = "https://www.amazon.com/s?k=" + query.replace(" ", "+")
    # Amazon's SERP occasionally first-paints slowly or flashes a brief
    # interstitial; a single 15s wait_for_selector raced and failed ~2/3 of
    # runs even though the results were about to load. Retry once with a
    # reload and a longer wait before giving up.
    results_ready = False
    for attempt in (1, 2):
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_selector('[data-component-type="s-search-result"]', timeout=25000)
            results_ready = True
            break
        except Exception as e:
            print(f"    search attempt {attempt} failed: {e}")
            time.sleep(4)
    if not results_ready:
        return None

    cards = page.query_selector_all('[data-component-type="s-search-result"][data-asin]')
    for card in cards:
        asin = card.get_attribute("data-asin")
        if not asin or len(asin) != 10:
            continue
        # Skip sponsored placements — those are paid, not organic relevance
        if card.query_selector('span.puis-sponsored-label-text'):
            continue

        title_el = card.query_selector('h2 span')
        title = title_el.inner_text().strip() if title_el else ""
        if not title:
            continue

        stars_el = card.query_selector('.a-icon-alt')
        stars = parse_stars(stars_el.inner_text() if stars_el else "")

        # Review count: 2026-05-27 Amazon SERP exposes the EXACT count in the
        # aria-label of the ratings link ("6,192 ratings"). The visible
        # inner_text is rounded ("6.1K"), and the older `a span.a-size-base.
        # s-underline-text` selector matches nothing on the current DOM, which
        # is what caused the first Pi run to reject every result. Prefer the
        # aria-label; fall back to the rounded inner_text only if missing.
        reviews = 0
        ratings_link = card.query_selector('a[aria-label*="ratings"]')
        if ratings_link:
            aria = ratings_link.get_attribute("aria-label") or ""
            reviews = parse_review_count(aria)
            if not reviews:
                reviews = parse_review_count(ratings_link.inner_text())

        price_el = card.query_selector('.a-price .a-offscreen')
        price = price_el.inner_text().strip() if price_el else ""

        if stars >= MIN_STARS and reviews >= MIN_REVIEWS:
            return {
                "asin": asin,
                "title": title[:140],
                "stars": stars,
                "reviews": reviews,
                "price": price,
            }
    return None


def verify_dp(page, asin: str) -> Optional[dict]:
    """Navigate /dp/ASIN. Confirm a real product page renders. Conservative:
    any unexpected state -> None (skip). Returns verified metadata dict."""
    url = f"https://www.amazon.com/dp/{asin}"
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_selector("#productTitle", timeout=10000)
    except Exception as e:
        print(f"    /dp/{asin} did not render productTitle: {e}")
        return None

    body_text = ""
    try:
        body_text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body_text = ""

    for sentinel in (
        "Sorry, this page is not available",
        "Sorry! We couldn't find that page",
        "Robot Check",
        "Type the characters you see in this image",
    ):
        if sentinel in body_text:
            print(f"    /dp/{asin} hit sentinel: {sentinel!r}")
            return None

    try:
        title = page.eval_on_selector(
            "#productTitle", "el => el.textContent.trim()"
        )
    except Exception:
        return None

    def _safe(sel, expr):
        try:
            return page.eval_on_selector(sel, expr)
        except Exception:
            return ""

    stars_attr = _safe("#acrPopover", "el => el.getAttribute('title') || ''")
    reviews = _safe(
        "#acrCustomerReviewText", "el => el.textContent.trim()"
    )
    price = _safe(".a-price .a-offscreen", "el => el.textContent.trim()")
    availability = _safe("#availability", "el => el.textContent.trim()")

    return {
        "title": title[:140],
        "stars": parse_stars(stars_attr),
        "reviews": parse_review_count(reviews),
        "price": price,
        "in_stock": "in stock" in availability.lower()
        or "ships from" in availability.lower()
        or "available" in availability.lower()
        or not availability,  # missing availability block usually means in stock
    }


def fetch_movers_shakers(page, nodes: list[tuple[str, str]]) -> dict:
    """Harvest Amazon Movers & Shakers / Best Sellers pages for trend signal.
    Runs on the Pi (where Amazon doesn't bot-block us). Writes JSON consumed
    by Trend Scout on its next run.

    Conservative: any failure on a node logs + skips, never crashes the run.
    Returns dict ready to be JSON-dumped: {fetched_at, items: [...]}
    """
    out_items: list[dict] = []
    for label, url in nodes:
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            # Best Sellers + Movers pages both expose product cards with
            # data-asin under .zg-grid-general-faceout or .a-carousel-card.
            # We try a broader selector that matches both layouts.
            page.wait_for_selector("[id^='gridItemRoot'], .zg-grid-general-faceout, .a-carousel-card", timeout=15000)
        except Exception as e:
            print(f"  [movers] {label}: page load failed — {e}")
            continue

        try:
            cards = page.query_selector_all("[id^='gridItemRoot'], .zg-grid-general-faceout")
            for card in cards[:30]:
                asin = ""
                # Movers pages put data-asin on the inner card div
                inner = card.query_selector("[data-asin]")
                if inner:
                    asin = inner.get_attribute("data-asin") or ""
                if not asin or len(asin) != 10:
                    # fallback: parse from product link href
                    a = card.query_selector("a[href*='/dp/']")
                    href = a.get_attribute("href") if a else ""
                    if href:
                        import re as _re
                        m = _re.search(r"/dp/([A-Z0-9]{10})", href)
                        if m:
                            asin = m.group(1)
                if not asin:
                    continue
                title_el = card.query_selector("[class*='_p13n-zg-list-grid_'], div._cDEzb_p13n-sc-css-line-clamp_, .a-link-normal span div, h3")
                title = title_el.inner_text().strip() if title_el else ""
                if not title:
                    # fallback: aria-label on the product link often holds the title
                    a = card.query_selector("a[aria-label]")
                    title = (a.get_attribute("aria-label") or "").strip() if a else ""
                rank_el = card.query_selector(".zg-bdg-text, .zg-badge-text")
                rank = (rank_el.inner_text().strip() if rank_el else "").lstrip("#")
                out_items.append({
                    "node": label,
                    "rank": rank,
                    "asin": asin,
                    "title": title[:160],
                })
        except Exception as e:
            print(f"  [movers] {label}: parse failed — {e}")
            continue

        time.sleep(2)  # courtesy pause between nodes

    # Dedupe by (node, asin) — selector matches both the outer card and an
    # inner data-asin element, producing two rows per product.
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for it in out_items:
        key = (it["node"], it["asin"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "items": deduped,
    }


def build_vetted_entry(opp: dict, search_hit: dict, dp_verified: dict) -> dict:
    """Compose the JSON entry we will append to vetted[]."""
    categories: list[str] = []
    raw_cat = (opp.get("product_category") or "").strip().lower()
    if raw_cat:
        categories.append(raw_cat)
    # Pull intent keywords as secondary categories for token matching downstream
    for kw in (opp.get("buyer_intent_keywords") or [])[:3]:
        token = kw.strip().lower().split()[0] if kw else ""
        if token and token not in categories:
            categories.append(token)

    return {
        "asin": search_hit["asin"],
        "product_name": dp_verified["title"],
        "categories": categories,
        "affiliate_url": (
            f"https://www.amazon.com/dp/{search_hit['asin']}?tag={AMAZON_TAG}"
        ),
        "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "verified_stars": str(dp_verified["stars"] or search_hit["stars"]),
        "verified_reviews": dp_verified["reviews"] or search_hit["reviews"],
        "verified_price": dp_verified["price"] or search_hit["price"],
        "discovered_from_trend": (
            opp.get("specific_product") or opp.get("product_category") or ""
        ),
        "discovery_source": "asin_discoverer_auto",
    }


def main() -> int:
    if not TREND_FEED.exists():
        print("[asin-discoverer] No trend_feed.json — nothing to discover.")
        return 0
    feed = json.loads(TREND_FEED.read_text())
    opportunities = feed.get("opportunities", [])
    if not opportunities:
        print("[asin-discoverer] Trend feed has no opportunities.")
        return 0

    if not REGISTRY_PATH.exists():
        print("[asin-discoverer] Registry missing — aborting.")
        return 1
    reg = json.loads(REGISTRY_PATH.read_text())
    reg.setdefault("vetted", [])
    reg.setdefault(
        "_vetted_doc",
        "Verified-live Amazon ASINs cleared for blog/SEO/IG use but NOT yet "
        "wired to a Meta DM automation. Promote to entries[] (with a unique "
        "keyword) only AFTER creating the matching Meta Business Suite "
        "automation. Always /dp/<ASIN>?tag=goldenhomep06-20 URLs — never search URLs.",
    )

    if len(reg["vetted"]) >= MAX_VETTED_POOL:
        print(
            f"[asin-discoverer] Vetted pool at cap ({len(reg['vetted'])}/{MAX_VETTED_POOL}) "
            "— skipping run."
        )
        return 0

    tokens, cats, asins = existing_coverage(reg)
    candidates = [o for o in opportunities if not opportunity_is_covered(o, tokens, cats)]
    if not candidates:
        print(
            f"[asin-discoverer] All {len(opportunities)} trend opportunities "
            "already covered — running Movers & Shakers harvest only."
        )
    else:
        candidates = candidates[:MAX_NEW_PER_RUN]
        print(
            f"[asin-discoverer] {len(candidates)} candidate opportunit{'y' if len(candidates) == 1 else 'ies'} "
            f"to discover (capped at {MAX_NEW_PER_RUN})"
        )

    # Import lazily so importing this module elsewhere doesn't require playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[asin-discoverer] playwright not installed. Run: "
            "pip install playwright && playwright install chromium"
        )
        return 1

    discovered: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            user_agent=UA,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()

        for i, opp in enumerate(candidates, 1):
            keywords = opp.get("buyer_intent_keywords") or []
            query = (
                keywords[0]
                if keywords
                else (opp.get("specific_product") or opp.get("product_category") or "")
            )
            if not query:
                print(f"  [{i}/{len(candidates)}] no query — skipping")
                continue
            print(f"  [{i}/{len(candidates)}] discovering: {query!r}")

            try:
                hit = search_amazon(page, query)
            except Exception as e:
                print(f"    search exception: {e}")
                continue

            if not hit:
                print("    no qualifying organic result")
                continue
            if hit["asin"] in asins:
                print(f"    top result {hit['asin']} already in registry — skip")
                continue

            time.sleep(2)  # avoid hammering Amazon between search and /dp/

            try:
                verified = verify_dp(page, hit["asin"])
            except Exception as e:
                print(f"    /dp/ exception: {e}")
                continue

            if not verified:
                continue

            entry = build_vetted_entry(opp, hit, verified)
            discovered.append(entry)
            asins.add(hit["asin"])
            print(
                f"    + {hit['asin']} {verified['title'][:60]!r} "
                f"({verified['stars']}*, {verified['reviews']} reviews)"
            )

            time.sleep(3)

        # Free side-product: refresh the Movers & Shakers cache that Trend
        # Scout reads on its next morning run. We do this AFTER discovery so
        # discovery itself never gets blocked by a flaky Movers page.
        print("[asin-discoverer] Harvesting Amazon Movers & Shakers for Trend Scout...")
        try:
            ms = fetch_movers_shakers(page, MOVERS_NODES)
        except Exception as e:
            print(f"  [movers] harvest exception: {e}")
            ms = None

        browser.close()

    if ms and ms.get("items"):
        MOVERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        MOVERS_CACHE.write_text(json.dumps(ms, indent=2) + "\n")
        print(f"[asin-discoverer] Wrote {len(ms['items'])} movers items -> {MOVERS_CACHE.relative_to(ROOT)}")

    # Refresh Reddit cache for Trend Scout. Best-effort only: Reddit blocks
    # this IP at the network level (see fetch_reddit_for_cache docstring), so
    # this usually returns 0 posts and we keep the prior cache. Movers &
    # Shakers above is the load-bearing trend signal.
    print("[asin-discoverer] Refreshing Reddit cache for Trend Scout (best-effort)...")
    reddit_cache = fetch_reddit_for_cache(REDDIT_SUBS)
    reddit_post_count = sum(len(v) for v in reddit_cache.get("subs", {}).values())
    if reddit_post_count:
        REDDIT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        REDDIT_CACHE.write_text(json.dumps(reddit_cache, indent=2) + "\n")
        print(f"[asin-discoverer] Wrote {reddit_post_count} reddit posts -> {REDDIT_CACHE.relative_to(ROOT)}")
    else:
        print("[asin-discoverer] Reddit returned no posts — leaving prior cache (if any) untouched")

    movers_count = len(ms["items"]) if (ms and ms.get("items")) else 0

    if not discovered:
        print("[asin-discoverer] No new ASINs verified this run.")
        # Still useful to log if we refreshed any caches
        if movers_count or reddit_post_count:
            cache_parts = []
            if movers_count:
                cache_parts.append(str(MOVERS_CACHE.relative_to(ROOT)))
            if reddit_post_count:
                cache_parts.append(str(REDDIT_CACHE.relative_to(ROOT)))
            ran_parts = []
            if movers_count:
                ran_parts.append(f"{movers_count} Movers items")
            if reddit_post_count:
                ran_parts.append(f"{reddit_post_count} Reddit posts")
            append_log_entry(
                agent="ASIN Discoverer",
                ran=f"No new ASINs; refreshed " + " + ".join(ran_parts),
                changed=", ".join(cache_parts),
                external="amazon.com bestsellers (playwright) + reddit.com top.json (stdlib)",
                hint="Trend Scout will read refreshed caches on next run.",
            )
        return 0

    reg["vetted"].extend(discovered)
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2) + "\n")
    print(
        f"[asin-discoverer] Added {len(discovered)} ASIN(s) to vetted pool "
        f"(pool now {len(reg['vetted'])}/{MAX_VETTED_POOL})."
    )

    changed_parts = ["social/dm_keyword_registry.json"]
    if movers_count:
        changed_parts.append(str(MOVERS_CACHE.relative_to(ROOT)))
    if reddit_post_count:
        changed_parts.append(str(REDDIT_CACHE.relative_to(ROOT)))
    ran_suffix = ""
    if movers_count:
        ran_suffix += f", refreshed {movers_count} Movers items"
    if reddit_post_count:
        ran_suffix += f", refreshed {reddit_post_count} Reddit posts"

    append_log_entry(
        agent="ASIN Discoverer",
        ran=(
            f"Scanned {len(opportunities)} trend opportunities, "
            f"verified {len(discovered)} new ASIN(s)" + ran_suffix
        ),
        changed=", ".join(changed_parts),
        external="amazon.com search + /dp/ + bestsellers (playwright) + reddit.com top.json (stdlib)",
        hint=(
            "Blog Writer can now ship monetized posts about: "
            + ", ".join(d["product_name"][:50] for d in discovered)
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
