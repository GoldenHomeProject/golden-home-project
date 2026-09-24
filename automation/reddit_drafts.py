#!/usr/bin/env python3
"""reddit_drafts.py — write one ready-to-post Reddit draft a day. It does NOT post.

Why drafts and not an auto-poster (decided 2026-09-24)
------------------------------------------------------
* Reddit closed self-service API registration: every new OAuth app now needs manual
  approval, and COMMERCIAL use needs a paid agreement. An affiliate business posting
  through the API is commercial use, and GHP runs on a $0 budget.
* Posting through a scripted browser instead would be routing around that approval
  gate — the quickest way to get the account and the domain banned.
* Reddit's filters and most subreddits treat raw Amazon affiliate links as spam, and
  undisclosed affiliate links get accounts permanently banned.

So the Pi does the part that takes effort — choosing a current, genuinely useful set of
products and writing it up — and a human posts it. If Reddit ever approves API access,
this same draft becomes the payload and only a posting step needs adding.

Rules every draft obeys:
  * Value lives IN the post: the picks, their real rating and review counts, prices.
    Someone who never clicks still got something.
  * NO raw affiliate links in the body. One link to our hub page at the end, with an
    explicit disclosure line.
  * No claimed first-hand experience (fabrication gate), nothing off-niche or out of
    season (the same shared lists every other channel uses).
  * A hub is not reused within REUSE_DAYS, so it does not read as a campaign.

Run:  python3 automation/reddit_drafts.py
Output: social/reddit_drafts/YYYY-MM-DD.md and a line in social/reddit_drafts.json
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
from category_identity import in_category, off_niche_hit, dead_season_hit  # noqa: E402
from content_quality_gate import fabrication_match  # noqa: E402
from trending_daily import EVERGREEN  # noqa: E402

SITE = "https://goldenhomeproject.com"
OUT_DIR = ROOT / "social" / "reddit_drafts"
LEDGER = ROOT / "social" / "reddit_drafts.json"
REUSE_DAYS = 10
PICKS = 5

# Candidate communities per category. These are SUGGESTIONS, not verified permission:
# every subreddit sets its own self-promotion rules, and they change. The draft tells
# the poster to read the sidebar rules first. Kept deliberately short.
SUBREDDITS = {
    "Home Storage":      ["r/organization", "r/declutter"],
    "Home":              ["r/organization", "r/declutter"],
    "Kitchen":           ["r/organization", "r/Cooking"],
    "Bath":              ["r/organization", "r/CleaningTips"],
    "Bath Linens":       ["r/organization", "r/CleaningTips"],
    "Cleaning":          ["r/CleaningTips"],
    "Bedding":           ["r/malelivingspace", "r/femalelivingspace"],
    "Window Treatments": ["r/malelivingspace", "r/femalelivingspace"],
    "Home Décor":        ["r/malelivingspace", "r/femalelivingspace"],
    "Seasonal Décor":    ["r/Halloween", "r/HomeDecorating"],
}


def _ledger() -> list:
    try:
        return json.loads(LEDGER.read_text())
    except (OSError, ValueError):
        return []


def _recent_hubs(ledger: list, today: date) -> set:
    cutoff = str(today - timedelta(days=REUSE_DAYS))
    return {e.get("hub") for e in ledger if str(e.get("date", "")) >= cutoff}


def _clean(name: str) -> str:
    """Short, whole-word product name.

    Scraped titles are often already truncated upstream mid-word ("...with Zippers &
    Carryi"), so a long name is cut back to the last whole word before 60 chars rather
    than trusted to end cleanly.
    """
    n = name.split(",")[0].split(" (")[0].strip()
    if len(n) <= 60:
        return n
    words = n[:60].rsplit(" ", 1)[0].rstrip(" -&|/").split()
    # never end on a connector: "...Heavy Duty with" reads as broken
    while words and words[-1].lower() in {"with", "and", "for", "of", "&", "-", "in",
                                          "to", "the", "a", "or", "|"}:
        words.pop()
    return " ".join(words)


def _pick_set(today: date, skip_hubs: set):
    """Newest picks file whose hub exists, is not recently used, and has enough
    products that pass every shared gate."""
    for f in sorted((ROOT / "social").glob("trending_picks_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        cat = data.get("category") or ""
        if cat not in EVERGREEN:
            continue
        slug, query = EVERGREEN[cat]
        if slug in skip_hubs or not (ROOT / "blog/posts" / f"{slug}.html").exists():
            continue
        good = []
        for p in data.get("picks") or []:
            name = str(p.get("name") or p.get("title") or "")
            if not name or not in_category(name, cat):
                continue
            if off_niche_hit(name) or dead_season_hit(name):
                continue
            good.append(p)
        if len(good) >= 3:
            # The post says "ranked by how many people have reviewed them" — so rank
            # them that way. The first draft kept chart order and the claim was false.
            good.sort(key=lambda p: int(p.get("reviews") or 0), reverse=True)
            return cat, slug, query, good[:PICKS]
    return None


def build(cat: str, slug: str, query: str, picks: list) -> dict:
    prices = [float(str(p.get("price", "")).replace("$", "") or 0) for p in picks
              if str(p.get("price", "")).startswith("$")]
    ceiling = f"${int(max(prices)) + 1}" if prices else ""
    title = (f"{query.capitalize()}: the {len(picks)} Amazon best-sellers with the "
             f"most reviews right now{' (all under ' + ceiling + ')' if ceiling else ''}")

    lines = [
        f"I track Amazon's live best-seller charts for {cat.lower()}. These are the "
        f"picks currently near the top that also hold 4.5 stars or better, ranked by "
        f"how many people have actually reviewed them:",
        "",
    ]
    for i, p in enumerate(picks, 1):
        bits = [f"**{_clean(str(p.get('name') or p.get('title')))}**"]
        facts = []
        if p.get("rating"):
            facts.append(f"{p['rating']}★")
        if p.get("reviews"):
            try:
                facts.append(f"{int(p['reviews']):,} reviews")
            except (TypeError, ValueError):
                pass
        if p.get("price"):
            facts.append(f"~{p['price']}")
        lines.append(f"{i}. {bits[0]} — {', '.join(facts)}")
    lines += [
        "",
        "I haven't personally tested these; the rating and review count are the "
        "evidence here, and prices move daily, so check before buying.",
        "",
        f"Full list with links, updated daily: {SITE}/blog/posts/{slug}.html",
        "",
        "*Disclosure: that page uses Amazon affiliate links, so I may earn a small "
        "commission at no extra cost to you.*",
    ]
    body = "\n".join(lines)

    fake = fabrication_match(f"{title}\n{body}")
    if fake:
        raise ValueError(f"draft failed the fabrication gate: {fake!r}")
    if "tag=" in body or "amzn.to" in body:
        raise ValueError("draft contains a raw affiliate link — not allowed on Reddit")
    return {"title": title, "body": body, "subreddits": SUBREDDITS.get(cat, [])}


def main() -> int:
    today = date.today()
    ledger = _ledger()
    if any(e.get("date") == str(today) for e in ledger):
        print(f"[reddit] draft for {today} already exists — nothing to do")
        return 0
    found = _pick_set(today, _recent_hubs(ledger, today))
    if not found:
        print("[reddit] no hub with >=3 clean picks that wasn't used recently — skipping")
        return 0
    cat, slug, query, picks = found
    d = build(cat, slug, query, picks)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    md = OUT_DIR / f"{today}.md"
    md.write_text(
        f"# Reddit draft — {today}\n\n"
        f"**Suggested subreddits:** {', '.join(d['subreddits']) or '(pick one)'}\n"
        f"Read the subreddit's rules first — many cap or forbid self-promotion. "
        f"Post as a text post; do not add links beyond the one below.\n\n"
        f"---\n\n**Title**\n\n{d['title']}\n\n**Body**\n\n{d['body']}\n")
    ledger.append({"date": str(today), "hub": slug, "category": cat,
                   "title": d["title"], "subreddits": d["subreddits"],
                   "file": str(md.relative_to(ROOT)), "posted": False})
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n")
    print(f"[reddit] wrote {md.relative_to(ROOT)} ({cat} -> {slug})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
