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

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "automation" / "scripts"
SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
SOCIAL_DIR = ROOT / "social"
TREND_FEED = SOCIAL_DIR / "trend_feed.json"
QUEUE_PATH = SOCIAL_DIR / "post_queue.json"

AMAZON_TAG = "goldenhomep06-20"
DAILY_SCRIPT_COUNT = 3


AIDA_GRANDSLAM_SYSTEM = """You are the Content Engine for Golden Home Project LLC.

Every script you produce MUST satisfy BOTH frameworks simultaneously:

AIDA structure (scene-by-scene):
- Scene 1 (Attention): HOOK. Specific $ amount + surprising claim. <=3 seconds.
- Scenes 2-3 (Interest): the PROBLEM. Relatable pain. "I was tired of..."
- Scenes 4-5 (Desire): the TRANSFORMATION. Before → after. Value stacked.
- Scene 6 (Action): single CTA. "Everything linked in bio."

Grand Slam Offer value equation (Hormozi):
value = (Dream_Outcome × Perceived_Likelihood) / (Time_Delay × Effort)
- Dream outcome: crystal clear ("kitchen looks $10k renovated")
- Perceived likelihood: specific $ + social proof words
- Time delay: "5 minutes", "one afternoon", "same day"
- Effort: "no tools", "no landlord permission", "one Amazon box"

GHP voice rules (non-negotiable):
- NEVER say "amazing", "game-changer", "you won't believe"
- Always specific dollar amounts in the hook
- Use "I" not "we" — personal, not corporate
- Skeptic-to-convert tone: "I was skeptical. I was wrong."
- Conversational, not salesy — like texting a friend

Posting rules:
- Reels only (REELS media_type), 20-30 seconds total
- 5-7 scenes, each 3-5 seconds
- On-screen text MUST be readable on mobile (big, short lines)
- Voiceover = casual speech, <12 words per scene
"""


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
    prompt = f"""Using the AIDA + Grand Slam frameworks from your system prompt,
produce {len(top)} Reel production scripts — one per opportunity below.

OPPORTUNITIES:
{json.dumps(top, indent=2)}

For EACH opportunity, return ONE script object. Total output: JSON array of {len(top)} objects.

Schema:
[
  {{
    "opportunity_rank": 1,
    "product_category": "from input",
    "target_price": "$XX",
    "hook": "one sentence <= 12 words, specific $, mobile-optimized",
    "aida_breakdown": {{
      "attention": "hook scene description",
      "interest": "problem setup",
      "desire": "transformation scene",
      "action": "CTA scene"
    }},
    "value_equation": {{
      "dream_outcome": "string",
      "perceived_likelihood": "string (why believable)",
      "time_delay": "string (how fast)",
      "effort_sacrifice": "string (minimal work)"
    }},
    "scenes": [
      {{
        "n": 1,
        "duration_sec": 3,
        "visual_prompt": "detailed image description for generation",
        "on_screen_text": "MAX 6 WORDS",
        "voiceover": "conversational line, <12 words"
      }}
      // 5-7 scenes total
    ],
    "caption": "IG caption, hook repeated + 3-5 hashtags, <=2200 chars",
    "hashtags": ["5-7 niche hashtags, no generic spam"],
    "affiliate_strategy": {{
      "primary_product": "name",
      "amazon_search_url": "https://www.amazon.com/s?k=<encoded>&tag={AMAZON_TAG}",
      "fallback_brands": ["Mamma Mia / Eli & Elm / Best Choice if fit"]
    }}
  }}
]

Output STRICT JSON only. No prose, no fences."""

    return call_claude_json(
        prompt,
        system=AIDA_GRANDSLAM_SYSTEM,
        max_tokens=6000,
    )


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

    entry = {
        "name": f"reel_{date_str}_{seq:03d}",
        "status": "awaiting_video",  # reel-producer flips to "ready"
        "script_path": str(script_path.relative_to(ROOT)),
        "media_type": "REELS",
        "video_url": None,  # filled by reel-producer after MP4 is committed
        "caption": script.get("caption", ""),
        "hashtags": script.get("hashtags", []),
        "affiliate": script.get("affiliate_strategy", {}),
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

    for i, script in enumerate(scripts, start=1):
        path = persist_script(script, date_str, i)
        enqueue_for_posting(script, path, date_str, i)
        print(f"  Wrote {path.name} — hook: {script.get('hook', '')[:80]}")

    print(f"[content-engine] {len(scripts)} scripts queued, awaiting video production.")


if __name__ == "__main__":
    main()
