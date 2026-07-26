#!/usr/bin/env python3
"""keyword_research.py — build a ranked queue of REAL search queries to target.

Why this exists (2026-07-26): Google Search Console shows the site earned 108
impressions and 8 clicks in 90 days at average position 36.9, across 14 unique
queries — and almost all of those were people typing the brand name ("golden home",
"goldenhome"). Only TWO impressions in three months came from a commercial query.
Six months of daily posting captured essentially zero search demand, because
`blog_writer.pick_topic()` chooses topics from a Reddit/best-seller trend feed:
what is *popular*, never what is *searched*. A faceless affiliate site lives or dies
on search intent, so the pipeline needs a demand signal. This is it.

Data sources, both free and keyless (no paid SEO tool, per the free-tools mandate):
  * Google Suggest  — autocomplete only returns strings people actually search.
  * Amazon completion — the same, filtered to shopping intent.
Neither returns volume numbers, so we rank by the signals we DO get: suggestion
order (earlier = more common), commercial-intent modifiers, and long-tail
specificity (a 5-word query is winnable for a site with no authority; "storage
bins" is not).

Run on the Pi — Amazon bot-walls datacenter IPs.

    python3 automation/keyword_research.py [--max-seeds N] [--dry-run]

Writes social/keyword_queue.json, consumed by blog_writer.pick_topic().
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"
QUEUE = ROOT / "social" / "keyword_queue.json"
POSTS = ROOT / "blog" / "posts"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Intent modifiers. A searcher typing "best X for Y" is comparing before buying;
# someone typing "X" alone may just want a picture. We only want the former.
COMMERCIAL_PREFIXES = ["best", "cheap", "top rated"]
COMMERCIAL_SUFFIXES = ["for", "vs", "under", "review", "worth it", "that"]

# Queries we must NOT chase. wirecutter/reddit/ikea mean the searcher already
# picked a destination that isn't us; brand terms are already "ranking" and earn
# nothing (see the GSC query list). Junk = autocomplete noise.
BLOCK = re.compile(
    r"\b(wirecutter|reddit|ikea|amazon|walmart|target|costco|home depot|lowes|"
    r"golden home|goldenhome|golden project|youtube|tiktok|near me|used|diy plans|"
    # Wrong sense of an ambiguous seed. A bare "storage" seed returns gaming-PC
    # drives; "organization" returns ADHD apps and charities to donate to. All
    # real output from the first live run.
    r"water filter|water filtration|purifier|reverse osmosis|osmosis|garbage disposal|"
    r"gaming|pc|ssd|hard drive|cloud|app|software|nonprofit|non-profit|charity|"
    r"donate|donation|adhd|chart of accounts|structure|"
    # We are a US Amazon associate; foreign-geo queries cannot convert.
    r"uk|australia|india|canada|nz|ireland|singapore|philippines|south africa)\b",
    re.I,
)

# A query must name a physical home-organization thing we could actually sell.
# Without this gate, autocomplete wanders off the niche within two hops.
HOME_NOUNS = re.compile(
    r"\b(organizer|organizers|organis|storage bin|storage box|storage container|"
    r"bins?|baskets?|shelf|shelves|shelving|rack|racks|caddy|caddies|cabinet|"
    r"drawers?|closet|pantry|hangers?|hooks?|turntable|lazy susan|spice|"
    r"under sink|undersink|over the door|wall mount|stackable|riser|divider|"
    r"cart|bench|cubby|cube|tote|jars?|canisters?|labels?|liner)\b",
    re.I,
)

# Curated niche seeds. Registry product titles alone skew to whatever we happen to
# have vetted; these keep expansion anchored to the brand's actual category.
NICHE_SEEDS = [
    "under sink organizer",
    "closet organizer",
    "pantry storage containers",
    "kitchen cabinet organizer",
    "drawer organizer",
    "shower caddy",
    "lazy susan turntable",
    "over the door organizer",
    "shoe rack for closet",
    "under bed storage",
]
JUNK = re.compile(r"[^a-z0-9$ '\-]|(\b[bcdfghjklmnpqrstvwxz]{5,}\b)", re.I)

COMMERCIAL_TOKENS = {
    "best", "top", "review", "reviews", "vs", "versus", "under", "cheap",
    "affordable", "worth", "compare", "alternative", "for",
}


def fetch_json(url: str, timeout: int = 15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def google_suggest(q: str) -> list[str]:
    url = ("https://suggestqueries.google.com/complete/search?client=firefox&q="
           + urllib.parse.quote(q))
    try:
        data = fetch_json(url)
        return list(data[1]) if len(data) > 1 else []
    except Exception as e:  # noqa: BLE001 — one dead seed must not kill the run
        print(f"  [suggest] {q!r} failed: {type(e).__name__}")
        return []


def amazon_suggest(q: str) -> list[str]:
    url = ("https://completion.amazon.com/api/2017/suggestions?mid=ATVPDKIKX0DER"
           "&alias=aps&limit=10&prefix=" + urllib.parse.quote(q))
    try:
        data = fetch_json(url)
        return [s.get("value", "") for s in data.get("suggestions", [])]
    except Exception as e:  # noqa: BLE001
        print(f"  [amazon] {q!r} failed: {type(e).__name__}")
        return []


def seeds_from_registry(limit: int) -> list[str]:
    """Seed from products we can actually monetize, so every keyword we chase has
    a live ASIN behind it. Chasing traffic we cannot convert is how the blog ended
    up with posts containing zero affiliate links."""
    out: list[str] = []
    if not REGISTRY.exists():
        return out
    reg = json.loads(REGISTRY.read_text())
    for entry in list(reg.get("entries", [])) + list(reg.get("vetted", [])):
        if entry.get("status") != "live":
            continue
        name = (entry.get("product_name") or "").lower()
        # First 3-4 words of a listing title are the product noun phrase; the rest
        # is spec soup ("2 Tier Pull Out, Slide Out, Heavy Duty...").
        words = re.findall(r"[a-z]+", name)[:4]
        phrase = " ".join(w for w in words if len(w) > 2)
        # Multi-word product phrases only. Bare category tokens ("storage",
        # "organization") are ambiguous and sent the first run into gaming PCs
        # and hair-donation charities.
        if len(phrase.split()) >= 2 and HOME_NOUNS.search(phrase) and phrase not in out:
            out.append(phrase)
    return (NICHE_SEEDS + out)[:limit]


def published_slugs() -> set[str]:
    return {p.stem for p in POSTS.glob("*.html")} if POSTS.exists() else set()


def expand(seed: str) -> list[tuple[str, str, int]]:
    """(query, source, rank) for one seed, across intent-shaped probes."""
    probes = [seed, f"best {seed}", f"{seed} for", f"{seed} vs", f"{seed} under"]
    found: list[tuple[str, str, int]] = []
    for probe in probes:
        for rank, q in enumerate(google_suggest(probe)):
            found.append((q, "google", rank))
        time.sleep(0.4)          # be a polite client; these are free endpoints
    for rank, q in enumerate(amazon_suggest(seed)):
        found.append((q, "amazon", rank))
    time.sleep(0.4)
    return found


def score(query: str, source: str, rank: int) -> float:
    words = query.split()
    n = len(words)
    s = 0.0
    # Suggestion order is our only popularity proxy: position 0 is the most-typed.
    s += max(0.0, 10.0 - rank)
    # Commercial intent is the whole point — no intent, no commission.
    tokens = {w.lower() for w in words}
    s += 8.0 * len(tokens & COMMERCIAL_TOKENS)
    if query.lower().startswith(("best ", "top ")):
        s += 6.0
    # Long-tail is winnable; head terms are not, for a site at position 36.9.
    if n >= 5:
        s += 10.0
    elif n == 4:
        s += 7.0
    elif n == 3:
        s += 3.0
    else:
        s -= 6.0                 # 1-2 word head terms: unwinnable, skip in practice
    # Amazon autocomplete is pure shopping intent, Google's is mixed.
    if source == "amazon":
        s += 2.0
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-seeds", type=int, default=12)
    ap.add_argument("--top", type=int, default=40, help="keywords to keep")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    seeds = seeds_from_registry(args.max_seeds)
    if not seeds:
        print("ERROR: no live products in the registry to seed from", flush=True)
        return 1
    print(f"[keywords] {len(seeds)} seeds: {', '.join(seeds[:6])}...")

    slugs = published_slugs()
    best: dict[str, dict] = {}
    for seed in seeds:
        print(f"  [seed] {seed}")
        for query, source, rank in expand(seed):
            q = query.strip().lower()
            if not q or len(q) < 8:
                continue
            if BLOCK.search(q) or JUNK.search(q):
                continue
            if not HOME_NOUNS.search(q):
                continue                      # stay inside the niche
            slug = re.sub(r"[^a-z0-9]+", "-", q).strip("-")
            if any(slug in s or s.endswith(slug) for s in slugs):
                continue                      # already have a post on this
            sc = score(q, source, rank)
            if sc <= 0:
                continue
            if q not in best or sc > best[q]["score"]:
                best[q] = {"query": q, "score": round(sc, 1), "source": source,
                           "rank": rank, "seed": seed, "slug": slug}

    ranked = sorted(best.values(), key=lambda k: -k["score"])[: args.top]
    print(f"\n[keywords] {len(best)} unique candidates -> keeping top {len(ranked)}")
    for k in ranked[:15]:
        print(f"   {k['score']:6.1f}  [{k['source']}]  {k['query']}")

    if args.dry_run:
        print("[keywords] --dry-run, queue not written")
        return 0

    QUEUE.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Real search queries from Google/Amazon autocomplete. Consumed by "
                "blog_writer.pick_topic(). Regenerate weekly.",
        "keywords": ranked,
    }, indent=2) + "\n")
    print(f"[keywords] wrote {QUEUE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
