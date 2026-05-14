"""GHP Content Engine — Agent 2 of the flywheel.

Generates 3 Reel scripts per day from a hand-crafted copy library
(social/copy_library.json). Replaces the prior LLM-driven generator —
the Claude Code CLI was unreliable for batch JSON gen and burned
subscription minutes silently. The template approach is deterministic,
free, and ships predictable Madison-Ave-quality copy.

Outputs per script:
- automation/scripts/reel-<date>-NNN.json — full production spec
- Appended to social/post_queue.json — ready for instagram-poster.yml

Selection rules:
- Only DM keywords with status='live' in dm_keyword_registry.json are eligible
  (otherwise the comment-to-DM funnel silently fails and we earn $0)
- Variants are picked to (a) maximize hook-category diversity over the last
  7 days of shipped scripts and (b) avoid back-to-back use of the same variant

The reel-producer agent consumes these script JSONs to render actual MP4s.
"""
import hashlib
import json
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Dead opener patterns — STRATEGY_2026-04-30.md confirmed 15+ consecutive posts
# at 0 likes/comments using these. Hard-block at script-generation time so
# no future regression can ship them. Match is case-insensitive on .lower().
DEAD_HOOK_PATTERNS = [
    re.compile(r"^\s*\$\d"),                    # "$47 fixed my couch..."
    re.compile(r"^\s*i\s+spent\s+\$?\d"),       # "I spent $89 on a pillow..."
    re.compile(r"^\s*i\s+spent\s+(only\s+)?\$"),# "I spent only $X..."
]


def _is_dead_hook(hook: str) -> bool:
    h = hook.lower()
    return any(p.match(h) for p in DEAD_HOOK_PATTERNS)

sys.path.insert(0, str(Path(__file__).parent))
from agent_log import append_log_entry

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "automation" / "scripts"
SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
SOCIAL_DIR = ROOT / "social"
TREND_FEED = SOCIAL_DIR / "trend_feed.json"
QUEUE_PATH = SOCIAL_DIR / "post_queue.json"
DM_REGISTRY_PATH = SOCIAL_DIR / "dm_keyword_registry.json"
COPY_LIBRARY_PATH = SOCIAL_DIR / "copy_library.json"

AMAZON_TAG = "goldenhomep06-20"
DAILY_SCRIPT_COUNT = 3


def load_live_dm_entries() -> list[dict]:
    """Return registry entries with status='live' — the ONLY products the
    content engine is allowed to ship, because only these have a working
    comment-to-DM Meta automation behind them."""
    if not DM_REGISTRY_PATH.exists():
        return []
    reg = json.loads(DM_REGISTRY_PATH.read_text())
    return [e for e in reg.get("entries", []) if e.get("status") == "live"]


def affiliate_url_for(asin: str) -> str:
    return f"https://www.amazon.com/dp/{asin}?tag={AMAZON_TAG}"


# Voice and structure rules formerly enforced via LLM system prompt now live in
# docs/BRAND_VOICE.md and are baked into copy_library.json hand-crafted variants.

# Hook category rotation — Content Engine picks categories that have been
# used the LEAST over the last 7 days of scripts, to force voice variety.
HOOK_CATEGORIES = [
    "confession",
    "confrontation",
    "sensory",
    "before_after",
    "question",
    "story_fragment",
    "micro_insight",
    "wrong_until_right",
]


def recent_hook_categories(days: int = 7) -> dict[str, int]:
    """Count hook categories used in the last N days of script files."""
    from collections import Counter
    counts = Counter({c: 0 for c in HOOK_CATEGORIES})
    if not SCRIPT_DIR.exists():
        return dict(counts)
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    for f in SCRIPT_DIR.glob("reel-*.json"):
        if f.stat().st_mtime < cutoff:
            continue
        try:
            data = json.loads(f.read_text())
            cat = data.get("hook_category")
            if cat in counts:
                counts[cat] += 1
        except Exception:
            continue
    return dict(counts)


def pick_under_used_categories(n: int) -> list[str]:
    """Return N hook categories, biased toward the least-used in the last 7 days."""
    counts = recent_hook_categories()
    ranked = sorted(HOOK_CATEGORIES, key=lambda c: counts.get(c, 0))
    return ranked[:n]


def load_trends() -> list[dict]:
    if not TREND_FEED.exists():
        print("[content-engine] No trend_feed.json — cannot generate without trends.")
        return []
    feed = json.loads(TREND_FEED.read_text())
    return feed.get("opportunities", [])


def load_copy_library() -> dict:
    if not COPY_LIBRARY_PATH.exists():
        raise RuntimeError(
            f"copy_library.json not found at {COPY_LIBRARY_PATH}. "
            "The content engine needs hand-crafted variants per live DM keyword."
        )
    return json.loads(COPY_LIBRARY_PATH.read_text())


def recently_used_variant_ids(days: int = 7) -> set:
    """Hash each shipped variant by (dm_keyword + hook + first scene voiceover)
    so we can avoid shipping the same variant twice in a 7-day window."""
    used = set()
    if not SCRIPT_DIR.exists():
        return used
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    for f in SCRIPT_DIR.glob("reel-*.json"):
        if f.stat().st_mtime < cutoff:
            continue
        try:
            data = json.loads(f.read_text())
            kw = (data.get("affiliate_strategy") or {}).get("dm_keyword", "")
            hook = data.get("hook", "")
            used.add(_variant_id(kw, hook))
        except Exception:
            continue
    return used


def _variant_id(keyword: str, hook: str) -> str:
    return hashlib.md5(f"{keyword}|{hook}".encode()).hexdigest()[:12]


def _disclosure_for(registry_entry: dict) -> str:
    """Return the FTC affiliate disclosure line matching this keyword's
    actual destination. Keywords rerouted to Impact direct merchants must
    NOT claim to be Amazon affiliate links — that's both inaccurate and
    weakens FTC compliance.

    BUG-FIX 2026-05-14: the registry uses subnet-qualified network names
    ("impact_direct", "impact_maas_to_amazon"); the prior exact-match
    against "impact" silently fell through to the Amazon default, so
    every Impact-rerouted reel for 3+ weeks claimed "Amazon affiliate"
    when the link actually pays via Impact. Now matches by prefix.
    """
    network = (registry_entry or {}).get("affiliate_network", "amazon").lower()
    if network.startswith("impact") or network.startswith("cj") or network.startswith("shareasale") or network.startswith("awin"):
        return "Affiliate link — I earn a small commission at no extra cost to you."
    # default: Amazon Associates
    return "Amazon affiliate — I earn a small commission at no extra cost to you."


def _build_caption(variant: dict, keyword: str, hashtags: list[str], registry_entry: Optional[dict] = None) -> str:
    """Assemble the IG caption from variant components. Follows the AIDA
    structure mandated by docs/BRAND_VOICE.md: HOOK -> BEAT 1 -> TURN ->
    RESULT -> DM CTA -> hashtags."""
    parts = [
        variant["hook"],
        "",
        variant["beat1"],
        "",
        variant["turn"],
        "",
        variant["result"],
        "",
        f"Comment {keyword} and I'll DM you the link.",
        _disclosure_for(registry_entry or {}),
        "",
        " ".join(hashtags),
    ]
    return "\n".join(parts).strip()


def _pick_hashtags(library: dict, registry_entry: dict, max_tags: int = 4) -> list[str]:
    pools = library.get("hashtag_pools", {})
    seen = []
    for cat in registry_entry.get("categories", []):
        for tag in pools.get(cat, []):
            if tag not in seen:
                seen.append(tag)
            if len(seen) >= max_tags:
                return seen
    # Top up with default pool
    for tag in pools.get("_default", []):
        if tag not in seen:
            seen.append(tag)
        if len(seen) >= max_tags:
            break
    return seen[:max_tags] if seen else ["#amazonhomefinds"]


def generate_scripts(opportunities: list[dict], n: int = DAILY_SCRIPT_COUNT) -> list[dict]:
    """Pick N variants from copy_library.json, balanced across hook categories
    and avoiding 7-day repetition. opportunities is accepted for backward compat
    with the workflow but is now informational only — variants live in the
    library, not the trend feed."""
    library = load_copy_library()
    variants_by_kw = library.get("variants", {})

    live_dm = load_live_dm_entries()
    if not live_dm:
        print("[content-engine] dm_keyword_registry has no live entries — refusing to ship.")
        return []

    by_kw = {e["keyword"]: e for e in live_dm}
    used = recently_used_variant_ids(days=7)

    # Build the candidate pool: (keyword, variant) tuples for every live keyword
    # that has at least one library variant.
    pool = []
    blocked_dead = 0
    for kw, entries in variants_by_kw.items():
        if kw not in by_kw:
            continue
        for variant in entries:
            if _is_dead_hook(variant.get("hook", "")):
                blocked_dead += 1
                continue
            vid = _variant_id(kw, variant["hook"])
            if vid in used:
                continue
            pool.append((kw, variant))
    if blocked_dead:
        print(f"[content-engine] Hard-blocked {blocked_dead} variant(s) matching dead hook patterns ($X / 'I spent $X').")

    if not pool:
        print("[content-engine] No fresh variants available — falling back to oldest used variants.")
        for kw, entries in variants_by_kw.items():
            if kw not in by_kw:
                continue
            for variant in entries:
                if _is_dead_hook(variant.get("hook", "")):
                    continue  # never resurface dead patterns even in fallback
                pool.append((kw, variant))

    if not pool:
        print("[content-engine] copy_library.json has no variants for any live DM keyword. Cannot ship.")
        return []

    # Diversify: prefer variants whose hook category is least-used in the last 7 days,
    # and rotate across distinct DM keywords so we don't ship 3 PILLOW reels in one day.
    hook_counts = recent_hook_categories(days=7)
    random.shuffle(pool)  # tiebreak randomness
    pool.sort(key=lambda kv: hook_counts.get(kv[1].get("hook_category", ""), 0))

    picked = []
    used_kws = []
    for kw, variant in pool:
        if len(picked) >= n:
            break
        # Avoid back-to-back same keyword in this batch (allow if pool exhausted)
        if used_kws.count(kw) >= max(1, n // max(1, len(by_kw))):
            continue
        picked.append((kw, variant))
        used_kws.append(kw)

    # If we still need more (e.g. only one live keyword), drop the diversity rule
    if len(picked) < n:
        for kw, variant in pool:
            if len(picked) >= n:
                break
            if any(p[0] == kw and p[1]["hook"] == variant["hook"] for p in picked):
                continue
            picked.append((kw, variant))

    scripts = []
    for kw, variant in picked:
        entry = by_kw[kw]
        hashtags = _pick_hashtags(library, entry)
        caption = _build_caption(variant, kw, hashtags, registry_entry=entry)
        scripts.append({
            "hook_category": variant["hook_category"],
            "hook": variant["hook"],
            "scenes": variant["scenes"],
            "caption": caption,
            "hashtags": hashtags,
            "specific_falsifiable_detail": variant.get("turn", "")[:200],
            "affiliate_strategy": {
                "primary_product": entry["product_name"],
                "dm_keyword": entry["keyword"],
                "amazon_asin": entry["asin"],
                "amazon_affiliate_url": affiliate_url_for(entry["asin"]),
                "asin_pending": False,
                "fallback_brands": [],
                # BUG-FIX 2026-05-14: stamp the registry's true affiliate
                # network onto every script. Downstream (DM automation,
                # attribution stamp, future per-channel routing) needs to
                # know whether this is Amazon (3-4%) or Impact (~20%); the
                # caption disclosure now also keys off this. Defaults to
                # "amazon" for back-compat with entries that pre-date the
                # 2026-05-03 reroutes.
                "affiliate_network": entry.get("affiliate_network", "amazon"),
                "affiliate_url": entry.get("affiliate_url"),
            },
        })
    return scripts


# Compatibility stub — keeps the legacy structured arg shape from the prior
# LLM-driven path. Anything that called generate_scripts() with opportunities
# still works; the args are now informational.


def persist_script(script: dict, date_str: str, seq: int) -> Path:
    """Write the full production spec as JSON for the reel-producer."""
    path = SCRIPT_DIR / f"reel-{date_str}-{seq:03d}.json"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "date": date_str,
        "seq": seq,
        **script,
    }
    path.write_text(json.dumps(payload, indent=2))
    return path


def enqueue_for_posting(script: dict, script_path: Path, date_str: str, seq: int):
    """Append a queue entry that the reel-producer will later fill with video_url."""
    queue = []
    if QUEUE_PATH.exists():
        queue = json.loads(QUEUE_PATH.read_text())

    affiliate = script.get("affiliate_strategy", {}) or {}
    # ASIN must be filled in by the pre-ship Chrome lookup step (fill_asins.py)
    # before the producer renders a video. Until then the queue entry is gated
    # at "awaiting_asin" so the reel-producer + poster skip it.
    asin_ready = bool(affiliate.get("amazon_asin"))
    initial_status = "awaiting_video" if asin_ready else "awaiting_asin"

    entry = {
        "name": f"reel_{date_str}_{seq:03d}",
        "status": initial_status,
        "script_path": str(script_path.relative_to(ROOT)),
        "media_type": "REELS",
        "video_url": None,  # filled by reel-producer after MP4 is committed
        "caption": script.get("caption", ""),
        "hashtags": script.get("hashtags", []),
        "affiliate": affiliate,
        "hook": script.get("hook", ""),
    }
    queue.append(entry)
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def main():
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[content-engine] Starting {date_str}")

    opps = load_trends()
    if not opps:
        print("[content-engine] No trends available. Exiting cleanly.")
        return

    print(f"[content-engine] {len(opps)} opportunities available, generating top {DAILY_SCRIPT_COUNT}")
    try:
        scripts = generate_scripts(opps, DAILY_SCRIPT_COUNT)
    except Exception as e:
        print(f"[content-engine] Claude generation failed: {e}")
        return

    written = []
    for i, script in enumerate(scripts, start=1):
        path = persist_script(script, date_str, i)
        enqueue_for_posting(script, path, date_str, i)
        written.append((path.name, script))
        print(f"  Wrote {path.name} — hook: {script.get('hook', '')[:80]}")

    print(f"[content-engine] {len(scripts)} scripts queued, awaiting video production.")

    # Per AGENT COORDINATION PROTOCOL — append to the shared log
    hook_summary = " | ".join(
        f"{w[1].get('hook_category', '?')}: {w[1].get('hook', '')[:50]}"
        for w in written
    ) or "no scripts generated"
    append_log_entry(
        agent="Content Engine",
        ran=f"Generated {len(written)} Reel scripts from {len(opps)} trend opportunities",
        changed=f"automation/scripts/reel-{date_str}-*.json, social/post_queue.json",
        external="none",
        hint=f"Quality Gate should review before Reel Producer renders. Hooks: {hook_summary}",
    )


if __name__ == "__main__":
    main()
