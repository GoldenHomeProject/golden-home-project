"""GHP Content Engine — Agent 2 of the flywheel.

Reads social/trend_feed.json, produces 3 Reel scripts per day using
AIDA structure + Hormozi Grand Slam Offer value equation + GHP COSTAR voice.

Outputs per script:
- automation/scripts/reel-<date>-NNN.json — full production spec
- Appended to social/post_queue.json — ready for instagram-poster.yml

Each script is structured as 5-7 scenes (1080x1920 Reel format), each with:
- visual prompt (for future image gen)
- on-screen text (large, mobile-readable)
- voiceover line (conversational, <12 words)
- scene duration (seconds)

The reel-producer agent consumes these to render actual MP4s.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _claude_api import call_claude_json
from agent_log import append_log_entry

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "automation" / "scripts"
SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
SOCIAL_DIR = ROOT / "social"
TREND_FEED = SOCIAL_DIR / "trend_feed.json"
QUEUE_PATH = SOCIAL_DIR / "post_queue.json"
DM_REGISTRY_PATH = SOCIAL_DIR / "dm_keyword_registry.json"

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


AIDA_GRANDSLAM_SYSTEM = """You are the Content Engine for Golden Home Project LLC.

Before writing anything, you MUST follow the canonical brand voice in docs/BRAND_VOICE.md.
The rules below are a summary — the doc is the source of truth. If there's any conflict,
the doc wins.

## Structure (AIDA applied to mobile Reels)
- Scene 1 (Attention): HOOK. One of the 8 hook categories from BRAND_VOICE.md
  (Confession / Confrontation / Sensory / Before-after / Question /
   Story fragment / Micro-insight / Wrong-until-proven-right). <= 3 seconds.
  The hook NEVER contains a price or the product name.
- Scenes 2-3 (Interest): the problem. 2-3 sensory beats, no product yet.
- Scenes 4-5 (Desire): the TURN — product named here for the first time,
  with ONE specific falsifiable detail (dimensions / material / review count).
- Scene 6 (Action): comment-to-DM CTA. ALWAYS format as:
  "Comment [KEYWORD] and I'll DM you the product link."
  KEYWORD is a single ALL-CAPS word tied to the product (LINK, PILLOW, COVER, etc.).
  Never "link in bio" alone. Never "RUN don't walk". This CTA is mandatory.

## Grand Slam Offer value equation (Hormozi)
value = (Dream_Outcome × Perceived_Likelihood) / (Time_Delay × Effort)
- Dream outcome: concrete sensory image, not adjectives
- Perceived likelihood: specific detail + one piece of social proof
- Time delay: "5 minutes", "one afternoon" — only if true
- Effort: "no tools", "no drilling" — only if true

## BANNED OPENERS — auto-reject if the caption's first 40 chars match any of these
- "I spent $X and..."     - "$X turned my..."
- "$X made my..."         - "$X fixed my..."
- "I tested..."           - "You NEED this..."
- "GAME CHANGER"          - "Stop scrolling..."
- "POV:"                  - Any price-first line

## Voice rules (non-negotiable)
- Ban words: amazing, game-changer, game changer, you won't believe, insane,
  literal, literally, life-changing, must-have, viral, obsessed.
- Admit things. Say "I was wrong" out loud when true.
- Specific over superlative. "Tomatoes actually slice clean" beats "amazing knife".
- One problem per post. Never list 5 products.
- No emoji in the hook line. Max 1 exclamation mark in the whole caption.
- Conversational, like texting a friend who asked for a recommendation.

## Caption structure (180–220 words max)
HOOK (one of 8 categories, no banned opener, no price, no product name)
BEAT 1 — problem, sensory, no product yet (price may appear here, line 3+)
TURN — product named with ONE falsifiable detail
RESULT — 1-2 concrete outcomes, not adjectives
DM CTA — "Comment [KEYWORD] and I'll DM you the product link. [affiliate — I earn if you buy via my link]"
3–5 strategic hashtags. Allowed Amazon-family discovery tags (use ONE per post, rotate):
#amazonhomefinds, #amazonhomehacks, #amazonmusthaves, #amazongadgets.
Banned (no discovery value): #gamechanger, #musthave, #viral, #fyp, #trending.

## Posting rules
- Reels only (REELS media_type), 20-30 seconds total
- 5-7 scenes, each 3-5 seconds
- On-screen text MUST be readable on mobile (big, short lines)
- Voiceover = casual speech, <12 words per scene

## Product naming rules — CRITICAL (anti-hallucination)
Affiliate revenue depends on the product actually existing on Amazon under
the brand we name. The Content Engine has previously hallucinated brand names
("Mamma Mia" sofa cover — that brand does not exist; the real seller is
Paulato by GA.I.CO). That cost us trust and shipped 3 reels with broken
affiliate funnels. Do not let it happen again.

When you fill `affiliate_strategy.primary_product`:
- ONLY use a brand name if you are highly confident that brand sells this
  product on amazon.com under that exact name. If you are not sure, OMIT
  the brand entirely and write a generic descriptor that a human can
  resolve to a real ASIN later (e.g. "stretch sofa slipcover for 4-seat
  couch, jacquard pattern" — NOT "Mamma Mia sofa cover").
- Prefer brands you have seen referenced in the trend opportunity input.
  If the input names a brand, use that brand verbatim.
- NEVER invent a brand to sound premium. Generic > fake-branded.
- `fallback_brands` should ONLY contain brands you are confident exist on
  Amazon in this category. Empty list is acceptable. Better empty than wrong.
- If you reference a review count or star rating in the script's
  `specific_falsifiable_detail`, that detail must be plausible for a real
  Amazon listing in the category — not invented.
"""


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


def generate_scripts(opportunities: list[dict], n: int = DAILY_SCRIPT_COUNT) -> list[dict]:
    if not opportunities:
        return []

    top = opportunities[:n]
    assigned_categories = pick_under_used_categories(len(top))
    category_defs = {
        "confession": "vulnerable, human admission. e.g. 'I avoided opening that cabinet for two years.'",
        "confrontation": "calls out received wisdom. e.g. 'Everyone says just buy a new couch. That's not the answer.'",
        "sensory": "puts reader IN the room with sensory detail (smell, sound, touch, light), NO price.",
        "before_after": "cinematic jump in time. e.g. 'Three weeks ago this drawer was crushed granola bars.'",
        "question": "genuine Socratic question the reader has silently wondered.",
        "story_fragment": "unresolved narrative fragment. e.g. 'My dog sat on the new cover and stared at me like I'd betrayed him.'",
        "micro_insight": "one sharp observation, uncommon truth. e.g. 'The reason your counters never stay clean is that nothing on them has a home.'",
        "wrong_until_right": "admit a mistake. e.g. 'I had the wrong pillow for a decade and didn't know it.'",
    }

    live_dm = load_live_dm_entries()
    if not live_dm:
        print("[content-engine] dm_keyword_registry has no live entries — refusing to ship.")
        return []

    per_opp = []
    for i, opp in enumerate(top):
        per_opp.append({
            "opportunity": opp,
            "assigned_hook_category": assigned_categories[i],
            "category_definition": category_defs[assigned_categories[i]],
        })

    prompt = f"""Produce {len(top)} Reel production scripts — one per opportunity below.

You MUST follow the brand voice in docs/BRAND_VOICE.md (summarized in your system prompt).

For each opportunity, I have ASSIGNED a hook category. Use that category for the hook.
Do NOT use banned openers. Do NOT put price or product name in the hook.

OPPORTUNITIES_WITH_HOOK_ASSIGNMENT:
{json.dumps(per_opp, indent=2)}

LIVE_DM_KEYWORDS — you MUST select one keyword per script from this list. Each keyword
has a Meta Business Suite comment-to-DM automation behind it that DMs the matching ASIN
to commenters. If you invent a keyword that's not on this list, the entire DM funnel
silently fails for that reel and we earn $0 from it. Pick the entry whose `categories`
or `product_name` best matches the opportunity. If no entry fits, pick the closest one
and reframe the script to fit that product — DO NOT invent a new keyword.

{json.dumps(live_dm, indent=2)}

Return a JSON array of {len(top)} script objects. Schema per object:

{{
  "opportunity_rank": 1,
  "hook_category": "confession | confrontation | sensory | before_after | question | story_fragment | micro_insight | wrong_until_right",
  "product_category": "from input",
  "target_price": "$XX",
  "hook": "one sentence <= 14 words. NO price, NO product name, NO banned openers. Must match assigned hook category.",
  "aida_breakdown": {{
    "attention": "hook scene description",
    "interest": "problem setup (sensory, no product yet)",
    "desire": "TURN — product named with ONE falsifiable detail",
    "action": "quiet CTA"
  }},
  "value_equation": {{
    "dream_outcome": "concrete sensory image, not adjectives",
    "perceived_likelihood": "specific detail + one social proof element",
    "time_delay": "only if truthfully fast",
    "effort_sacrifice": "only if truthfully low"
  }},
  "scenes": [
    {{"n": 1, "duration_sec": 3, "visual_prompt": "...", "on_screen_text": "MAX 6 WORDS", "voiceover": "<12 words"}}
    // 5-7 scenes total
  ],
  "caption": "180-220 words. Structure: HOOK -> BEAT 1 (problem, sensory) -> TURN (product named with falsifiable detail) -> RESULT (concrete) -> DM CTA -> 3-5 hashtags. Price appears no earlier than line 3. No banned openers. Max 1 exclamation mark. No emoji in hook line. The DM CTA MUST be the literal sentence: 'Comment <KEYWORD> and I'll DM you the link.' where <KEYWORD> is the EXACT keyword you selected from LIVE_DM_KEYWORDS (uppercase, no quotes). Then on the next line: 'Amazon affiliate — I earn a small commission at no extra cost to you.'",
  "hashtags": ["3-5 hashtags only. Priority: 1 branded, 1 niche <500k posts, 1 trending, optional 1-2 more. BANNED: #amazonfinds #homedecor #homehacks #gamechanger #musthave #viral"],
  "specific_falsifiable_detail": "the one concrete detail used in the TURN (e.g. '4.8 stars from 2,400 reviews', 'cotton/bamboo 15lb', 'fits up to 110in sectional')",
  "affiliate_strategy": {{
    "primary_product": "Product name from the SELECTED LIVE_DM_KEYWORDS entry's product_name (you may shorten/rephrase but DO NOT swap to a different product). NEVER invent a brand.",
    "dm_keyword": "the EXACT keyword from LIVE_DM_KEYWORDS you selected (uppercase, must match an entry)",
    "amazon_asin": "the ASIN from the SELECTED LIVE_DM_KEYWORDS entry — copy it verbatim",
    "fallback_brands": []
  }}
}}

Output STRICT JSON array only. No prose, no fences."""

    raw = call_claude_json(
        prompt,
        system=AIDA_GRANDSLAM_SYSTEM,
        max_tokens=6000,
        max_turns=1,   # pure one-shot JSON — no tool-use agentic loop needed
        retries=2,     # 2x300s + sleep ≈ 10min ceiling, fits in 15min workflow cap
        timeout=240,   # 4min per attempt; if it can't write 3 scripts in 4min, the SDK is stalled
    )

    # Enforce the registry: any script whose dm_keyword isn't a live entry
    # gets rewritten to use the registry's canonical ASIN + product_name, and
    # the affiliate_url is locked in. This guarantees every shipped reel has
    # a working comment-to-DM funnel.
    by_kw = {e["keyword"]: e for e in live_dm}
    safe = []
    for script in raw or []:
        aff = script.get("affiliate_strategy") or {}
        kw = (aff.get("dm_keyword") or "").upper().strip()
        entry = by_kw.get(kw)
        if not entry:
            print(f"[content-engine] DROPPING script — dm_keyword {kw!r} not in live registry")
            continue
        # Lock to canonical registry values — never trust LLM ASIN
        aff["dm_keyword"] = entry["keyword"]
        aff["amazon_asin"] = entry["asin"]
        aff["amazon_affiliate_url"] = affiliate_url_for(entry["asin"])
        aff["asin_pending"] = False
        aff["primary_product"] = entry["product_name"]
        script["affiliate_strategy"] = aff
        safe.append(script)
    return safe


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
