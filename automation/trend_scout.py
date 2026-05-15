"""GHP Trend Scout — Agent 1 of the flywheel.

Runs daily. Pulls signals from public sources (Reddit JSON, Amazon Movers &
Shakers page, Google Trends via unofficial endpoint if available) + asks
Claude to rank the top 5 product opportunities for transformation content.

Output: social/trend_feed.json (overwrites daily) + automation/trends/<date>.json (history)

Why not fancy scrapers? Simplicity + resilience. Reddit JSON and unauthenticated
Amazon HTML are the only two public sources that don't rot. Claude fills gaps.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import request

sys.path.insert(0, str(Path(__file__).parent))
from _claude_api import call_claude_json
from agent_log import append_log_entry

ROOT = Path(__file__).resolve().parent.parent
TREND_DIR = ROOT / "automation" / "trends"
TREND_DIR.mkdir(parents=True, exist_ok=True)
SOCIAL_DIR = ROOT / "social"
SOCIAL_DIR.mkdir(exist_ok=True)

REDDIT_SUBS = [
    "BuyItForLife",
    "HomeImprovement",
    "DiWHY",
    "organization",
    "HomeDecorating",
]


def fetch_reddit_top(sub: str, limit: int = 10) -> list[dict]:
    """Pull top posts of the day from a sub. Public JSON, no auth."""
    url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit={limit}"
    req = request.Request(url, headers={"User-Agent": "GHP-TrendScout/1.0"})
    try:
        with request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        posts = []
        for child in data.get("data", {}).get("children", []):
            p = child.get("data", {})
            posts.append({
                "title": p.get("title", "")[:200],
                "score": p.get("score", 0),
                "num_comments": p.get("num_comments", 0),
                "url": f"https://reddit.com{p.get('permalink', '')}",
            })
        return posts
    except Exception as e:
        print(f"  Reddit /r/{sub} failed: {e}")
        return []


def rank_opportunities(signals: dict) -> list[dict]:
    """Ask Claude to convert raw signals into ranked product opportunities."""
    prompt = f"""You are the Trend Scout for Golden Home Project LLC, an Amazon affiliate
marketing company focused on home transformation content (kitchen, bedroom,
bathroom, organization). Our Amazon Associate tag is `goldenhomep06-20`.

Today's date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}.

Raw signals from Reddit (top posts of the day across home/organization subs):
{json.dumps(signals, indent=2)[:6000]}

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

    # 1. Gather raw signals
    signals = {}
    for sub in REDDIT_SUBS:
        posts = fetch_reddit_top(sub)
        if posts:
            signals[sub] = posts
            print(f"  /r/{sub}: {len(posts)} posts")

    if not signals:
        print("  WARNING: No Reddit signals. Claude will reason from its own trend knowledge.")

    # 2. Claude ranks opportunities
    print("[trend-scout] Ranking opportunities with Claude...")
    try:
        opportunities = rank_opportunities(signals)
    except Exception as e:
        print(f"  ERROR: Claude ranking failed: {e}")
        # Fallback: write a minimal feed so downstream agents don't crash
        opportunities = []

    # 3. Persist — daily history + latest pointer
    feed = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "date": date_str,
        "opportunities": opportunities,
        "raw_signal_count": sum(len(v) for v in signals.values()),
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
    append_log_entry(
        agent="Trend Scout",
        ran=f"Scanned {len(signals)} subreddits ({sum(len(v) for v in signals.values())} posts), ranked {len(opportunities)} opportunities",
        changed=f"{history_path.relative_to(ROOT)}, {latest_path.relative_to(ROOT)}",
        external="none",
        hint=f"Content Engine: today's top-3 opportunities are: {top_hooks}",
    )


if __name__ == "__main__":
    main()
