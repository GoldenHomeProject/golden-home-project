"""GHP Trend Scout — Agent 1 of the flywheel.

Runs daily. Pulls signals from public sources and asks Claude to rank the top 5
product opportunities for transformation content.

Sources (2026-05-27 expansion):
  - Reddit JSON (5 home subs)               — Pi-side stdlib fetch, cached
                                                JSON consumed here. Reddit
                                                started 403'ing GH Actions
                                                runner IPs 2026-05-27.
  - Google Trends daily RSS (US)            — GH Actions, public XML, no auth
  - Pinterest publisher board RSS feeds     — GH Actions, public XML, no auth
  - Amazon Movers & Shakers (Home & Kitchen) — Pi-side via Playwright, cached
                                                JSON consumed here. Pi has the
                                                residential IP that doesn't get
                                                Robot-Check'd; GH Actions does.

Output:
  social/trend_feed.json          (overwrites daily — consumed by Content Engine)
  automation/trends/<date>.json   (daily history snapshot)

Why not fancier scrapers? Reliability. Public RSS / JSON survive longer than
private endpoints. Claude fills semantic gaps.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import request
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
from _claude_api import call_claude_json
from agent_log import append_log_entry

ROOT = Path(__file__).resolve().parent.parent
TREND_DIR = ROOT / "automation" / "trends"
TREND_DIR.mkdir(parents=True, exist_ok=True)
SOCIAL_DIR = ROOT / "social"
SOCIAL_DIR.mkdir(exist_ok=True)

# Pinterest publisher boards with public RSS feeds. These are mainstream
# home/lifestyle media — what they're pinning is a strong indicator of what
# aesthetics are about to surface on consumer Pinterest. If any of these 404
# (Pinterest has been gradually deprecating RSS), the fetcher logs + skips.
PINTEREST_BOARDS = [
    "hgtv",
    "bhg",          # Better Homes & Gardens
    "apttherapy",   # Apartment Therapy
    "realsimple",
    "marthastewart",
]

UA_BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def load_reddit_cache() -> dict:
    """Load the Pi-written Reddit snapshot, if present + fresh.

    The Pi ASIN discoverer refreshes automation/trends/reddit_latest.json
    each run (~06:00 UTC). Trend Scout used to fetch Reddit directly from
    GH Actions but Reddit started 403'ing runner IPs (2026-05-27); the Pi's
    residential IP still works. Stale > 36h -> we return {} so Claude isn't
    fed yesterday's "top of day" thread.

    Returns {sub_name: [post, ...], ...} (the inner dict, NOT the wrapper
    with fetched_at — to keep the downstream signal shape identical to the
    old in-process fetcher).
    """
    path = TREND_DIR / "reddit_latest.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        print(f"  Reddit cache parse failed: {e}")
        return {}
    fetched_at = data.get("fetched_at", "")
    try:
        ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        if age_h > 36:
            print(f"  Reddit cache stale ({age_h:.1f}h old) — skipping")
            return {}
    except Exception:
        pass
    return data.get("subs", {})


def fetch_google_trends_daily() -> list[dict]:
    """Daily US trending searches RSS — public, no API key. Returns up to 30
    {title, approx_traffic} dicts. Most are news/sports; Claude filters down
    to home-relevant terms during ranking.

    Endpoint: trends.google.com/trending/rss?geo=US
    (The older /trends/trendingsearches/daily/rss endpoint returns 404 as of
    2026-05-27; Google migrated trending RSS to /trending/rss.)
    """
    url = "https://trends.google.com/trending/rss?geo=US"
    req = request.Request(url, headers={"User-Agent": UA_BROWSER})
    try:
        with request.urlopen(req, timeout=15) as r:
            xml_bytes = r.read()
    except Exception as e:
        print(f"  Google Trends RSS failed: {e}")
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"  Google Trends RSS parse failed: {e}")
        return []

    # The feed namespaces approx_traffic under a custom namespace. Strip
    # namespaces while iterating so .findtext() works on local tag names.
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        traffic = ""
        for child in item:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "approx_traffic":
                traffic = (child.text or "").strip()
                break
        if title:
            items.append({"title": title, "approx_traffic": traffic})
    return items[:30]


def fetch_pinterest_board(board: str, limit: int = 15) -> list[dict]:
    """Public RSS feed for a Pinterest user/board. Returns recent pin titles.
    Some boards 404 (RSS gradually deprecated) — we skip silently.

    Endpoint: pinterest.com/<user>/feed.rss
    """
    url = f"https://www.pinterest.com/{board}/feed.rss"
    req = request.Request(url, headers={"User-Agent": UA_BROWSER})
    try:
        with request.urlopen(req, timeout=15) as r:
            xml_bytes = r.read()
    except Exception as e:
        print(f"  Pinterest /{board} feed failed: {e}")
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"  Pinterest /{board} parse failed: {e}")
        return []
    pins = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if title and title.lower() != "no title":
            pins.append({"title": title[:160]})
        if len(pins) >= limit:
            break
    return pins


def load_movers_shakers_cache() -> dict:
    """Load the Pi-written Movers & Shakers snapshot, if present + fresh.

    The Pi ASIN discoverer refreshes automation/trends/movers_shakers_latest.json
    after each successful run (~06:00 UTC daily). If the file is missing or
    older than 36 hours we return {} so Claude isn't fed stale Best Sellers.
    """
    path = TREND_DIR / "movers_shakers_latest.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        print(f"  Movers & Shakers cache parse failed: {e}")
        return {}
    fetched_at = data.get("fetched_at", "")
    try:
        ts = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        if age_h > 36:
            print(f"  Movers & Shakers cache stale ({age_h:.1f}h old) — skipping")
            return {}
    except Exception:
        pass
    return data


def rank_opportunities(signals: dict) -> list[dict]:
    """Ask Claude to convert raw signals into ranked product opportunities."""
    # Trim to keep prompt under the model's context budget. Reddit + Google
    # Trends + Pinterest + Movers & Shakers together can be large; 12K of
    # signal JSON gives Claude plenty without bloating the prompt.
    prompt = f"""You are the Trend Scout for Golden Home Project LLC, an Amazon affiliate
marketing company focused on home transformation content (kitchen, bedroom,
bathroom, organization). Our Amazon Associate tag is `goldenhomep06-20`.

Today's date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}.

Raw signals (multi-source — Reddit posts, Google Trends daily searches,
Pinterest publisher pins, Amazon Movers & Shakers Home & Kitchen):
{json.dumps(signals, indent=2)[:12000]}

Source weighting guidance:
- Amazon Movers & Shakers = highest signal (direct purchase momentum)
- Pinterest publisher pins = aesthetic trends about to surface in mainstream
- Google Trends = broadest noise; filter to home-relevant terms only
- Reddit = qualitative depth (problems people are describing right now)

Your job: identify the TOP 5 product opportunities right now for
transformation-format Reels (before/after, specific $ amount, single CTA).

Score each on:
- Trend heat (1-10): is this actually surging or just evergreen?
- Transformation potential (1-10): does before/after make sense?
- Affiliate availability (1-10): is this easy to find on Amazon?
- Buyer intent (1-10): are people actively shopping for this?

Higher-commission brands to prioritize (mention them if relevant):
- Mamma Mia Covers (24-30% commission) — couch/sofa covers, pet hair angle
- Eli & Elm (20%) — pillows, side sleeper neck pain
- Best Choice Products (15%) — furniture
- Syruvia (20%) — kitchen tools

Return STRICT JSON (no prose, no fences) matching this schema:
[
  {{
    "rank": 1,
    "product_category": "string (e.g. 'couch covers')",
    "specific_product": "string (e.g. 'Mamma Mia waterproof stretch cover')",
    "brand": "string or 'Amazon generic'",
    "target_price": "string (e.g. '$47')",
    "transformation_hook": "string (<= 100 chars, specific dollar amount)",
    "before_state": "string describing the messy/problem before",
    "after_state": "string describing the transformed after",
    "buyer_intent_keywords": ["3-5 search phrases buyers use"],
    "scores": {{"trend": 8, "transformation": 9, "affiliate": 10, "intent": 9}},
    "composite_score": 36,
    "why_now": "string — one sentence on why this is hot today"
  }},
  ... (5 total, ranked by composite_score DESC)
]"""

    # max_turns=1 forces one-shot JSON (no agentic tool-use loop). timeout=180
    # so 3 retries (~9min) fit inside the workflow's 10-min job cap; without
    # this, default 300s × 3 = 15min would always exceed the cap. Cancelled
    # 2026-05-15 run at 22m15s motivated this cap.
    return call_claude_json(prompt, max_tokens=4096, max_turns=1, timeout=180)


def main():
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[trend-scout] Starting {date_str}")

    # 1. Gather raw signals — multi-source as of 2026-05-27
    signals: dict = {}

    # Reddit — read Pi-cached snapshot (Reddit 403s GH Actions runner IPs)
    reddit_signals = load_reddit_cache()
    if reddit_signals:
        signals["reddit"] = reddit_signals
        total = sum(len(v) for v in reddit_signals.values())
        print(f"  reddit: {len(reddit_signals)} subs, {total} posts (Pi cache)")

    # Google Trends daily RSS (US-wide, noisy)
    gt = fetch_google_trends_daily()
    if gt:
        signals["google_trends_daily_us"] = gt
        print(f"  google_trends_daily: {len(gt)} terms")

    # Pinterest publisher boards (best-effort; some 404)
    pin_signals = {}
    for board in PINTEREST_BOARDS:
        pins = fetch_pinterest_board(board)
        if pins:
            pin_signals[board] = pins
            print(f"  pinterest/{board}: {len(pins)} pins")
    if pin_signals:
        signals["pinterest"] = pin_signals

    # Amazon Movers & Shakers — cached by Pi discoverer (yesterday's run)
    ms = load_movers_shakers_cache()
    if ms:
        signals["amazon_movers_shakers"] = ms
        print(f"  amazon_movers_shakers: {len(ms.get('items', []))} items "
              f"(fetched_at={ms.get('fetched_at', '?')})")

    if not signals:
        print("  WARNING: No signals at all. Claude will reason from its own trend knowledge.")

    # 2. Claude ranks opportunities
    print("[trend-scout] Ranking opportunities with Claude...")
    try:
        opportunities = rank_opportunities(signals)
    except Exception as e:
        print(f"  ERROR: Claude ranking failed: {e}")
        # Fallback: write a minimal feed so downstream agents don't crash
        opportunities = []

    # 3. Persist — daily history + latest pointer
    # Count actual content items, not top-level container lengths — sources
    # have nested structures (reddit/pinterest are dict-of-lists, movers is
    # dict-with-items-list, google_trends is a flat list).
    def _count_items(v) -> int:
        if isinstance(v, list):
            return len(v)
        if isinstance(v, dict):
            if "items" in v and isinstance(v["items"], list):
                return len(v["items"])
            return sum(_count_items(x) for x in v.values())
        return 0
    raw_signal_count = sum(_count_items(v) for v in signals.values())

    feed = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "date": date_str,
        "opportunities": opportunities,
        "raw_signal_count": raw_signal_count,
        "sources_used": sorted(signals.keys()),
    }
    history_path = TREND_DIR / f"{date_str}.json"
    latest_path = SOCIAL_DIR / "trend_feed.json"
    history_path.write_text(json.dumps(feed, indent=2))
    latest_path.write_text(json.dumps(feed, indent=2))

    print(f"[trend-scout] Wrote {len(opportunities)} opportunities → {latest_path}")
    if opportunities:
        for o in opportunities[:3]:
            print(f"  #{o.get('rank')}: {o.get('transformation_hook')}")

    # Per AGENT COORDINATION PROTOCOL — append to the shared log
    top_hooks = ", ".join(
        (o.get("transformation_hook") or o.get("product_category", "?"))[:40]
        for o in opportunities[:3]
    ) or "no opportunities ranked"
    src_summary = ", ".join(signals.keys()) or "none"
    append_log_entry(
        agent="Trend Scout",
        ran=(
            f"Scanned {len(signals)} sources ({src_summary}) -> {raw_signal_count} items, "
            f"ranked {len(opportunities)} opportunities"
        ),
        changed=f"{history_path.relative_to(ROOT)}, {latest_path.relative_to(ROOT)}",
        external="reddit_pi_cache + google_trends + pinterest_rss + amazon_movers_pi_cache",
        hint=f"Content Engine: today's top-3 opportunities are: {top_hooks}",
    )


if __name__ == "__main__":
    main()
