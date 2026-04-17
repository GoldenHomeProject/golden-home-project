"""GHP Repurposer — Agent 5 of the flywheel.

Runs weekly (Mondays). Takes the latest blog post and generates:
- 5 Reel scripts (appended to automation/scripts/, queued for reel-producer)
- 5 Pinterest pin descriptions → automation/pinterest/<date>.json
- 1 email newsletter draft → automation/email/<date>.md
- 10 tweet-length hooks → automation/microcopy/<date>.json

This is the "1 asset → 20 derivatives" multiplier every top creator uses.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _claude_api import call_claude_json

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "blog" / "posts"
SCRIPT_DIR = ROOT / "automation" / "scripts"
PINTEREST_DIR = ROOT / "automation" / "pinterest"
EMAIL_DIR = ROOT / "automation" / "email"
MICROCOPY_DIR = ROOT / "automation" / "microcopy"
QUEUE_PATH = ROOT / "social" / "post_queue.json"

for d in [SCRIPT_DIR, PINTEREST_DIR, EMAIL_DIR, MICROCOPY_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def latest_blog_markdown() -> tuple[Path, str] | None:
    mds = sorted(POSTS_DIR.glob("*.md"), reverse=True)
    if not mds:
        return None
    return mds[0], mds[0].read_text()


def repurpose(source_md: str) -> dict:
    prompt = f"""Repurpose this GHP blog post into 4 downstream asset types.

SOURCE POST:
{source_md[:8000]}

Keep the GHP voice (first-person, specific $, skeptic-to-convert, no "amazing").
Preserve AIDA + Grand Slam framing. Each derivative must stand alone.

Return STRICT JSON:
{{
  "reel_scripts": [
    // 5 scripts. Same schema as content_engine.py output:
    {{
      "hook": "<=12 words, specific $",
      "scenes": [
        {{"n": 1, "duration_sec": 3, "visual_prompt": "...", "on_screen_text": "...", "voiceover": "..."}}
        // 5-7 scenes
      ],
      "caption": "IG caption",
      "hashtags": ["5-7 niche"]
    }}
  ],
  "pinterest_pins": [
    {{
      "title": "<=60 chars, SEO-rich",
      "description": "200-500 chars, keyword dense, first-person, affiliate-link-friendly CTA",
      "hashtags": ["5-8 Pinterest-specific tags"],
      "image_concept": "vertical 1000x1500 pin design description"
    }}
    // 5 pins
  ],
  "email": {{
    "subject_line": "<=50 chars, curiosity-driven, specific $",
    "preheader": "<=100 chars",
    "body_markdown": "400-600 words, personal tone, one main CTA to blog post",
    "primary_cta_text": "button text"
  }},
  "microcopy_hooks": [
    "10 tweet/threads-length hooks (<=280 chars each), each one a different angle on the same content"
  ]
}}"""
    return call_claude_json(prompt, max_tokens=8000)


def enqueue_reel_scripts(scripts: list[dict], date_str: str):
    """Same structure as content_engine output — reel-producer can consume directly."""
    queue = json.loads(QUEUE_PATH.read_text()) if QUEUE_PATH.exists() else []
    for i, s in enumerate(scripts, start=1):
        seq = 900 + i  # 900-range to distinguish repurposed content from daily
        script_path = SCRIPT_DIR / f"reel-{date_str}-{seq:03d}.json"
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "date": date_str,
            "seq": seq,
            "source": "repurpose",
            **s,
        }
        script_path.write_text(json.dumps(payload, indent=2))
        queue.append({
            "name": f"reel_repurpose_{date_str}_{seq:03d}",
            "status": "awaiting_video",
            "script_path": str(script_path.relative_to(ROOT)),
            "media_type": "REELS",
            "video_url": None,
            "caption": s.get("caption", ""),
            "hashtags": s.get("hashtags", []),
            "hook": s.get("hook", ""),
        })
    QUEUE_PATH.write_text(json.dumps(queue, indent=2))


def main():
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"[repurpose] Starting {date_str}")

    result = latest_blog_markdown()
    if not result:
        print("[repurpose] No blog posts to repurpose yet.")
        return
    source_path, source_md = result
    print(f"[repurpose] Source: {source_path.name}")

    try:
        derivatives = repurpose(source_md)
    except Exception as e:
        print(f"[repurpose] Claude generation failed: {e}")
        return

    # 1. Reel scripts → daily pipeline
    reels = derivatives.get("reel_scripts", [])
    if reels:
        enqueue_reel_scripts(reels, date_str)
        print(f"  ✓ {len(reels)} reel scripts queued")

    # 2. Pinterest pins
    pins = derivatives.get("pinterest_pins", [])
    if pins:
        (PINTEREST_DIR / f"{date_str}.json").write_text(json.dumps(pins, indent=2))
        print(f"  ✓ {len(pins)} Pinterest pins drafted")

    # 3. Email newsletter
    email = derivatives.get("email", {})
    if email:
        em_md = (
            f"# {email.get('subject_line', '')}\n\n"
            f"**Preheader:** {email.get('preheader', '')}\n\n"
            f"---\n\n"
            f"{email.get('body_markdown', '')}\n\n"
            f"**CTA:** {email.get('primary_cta_text', '')}\n"
        )
        (EMAIL_DIR / f"{date_str}.md").write_text(em_md)
        print(f"  ✓ Email newsletter drafted")

    # 4. Microcopy hooks
    hooks = derivatives.get("microcopy_hooks", [])
    if hooks:
        (MICROCOPY_DIR / f"{date_str}.json").write_text(json.dumps(hooks, indent=2))
        print(f"  ✓ {len(hooks)} microcopy hooks captured")

    print(f"[repurpose] 1 blog → {len(reels) + len(pins) + (1 if email else 0) + len(hooks)} derivatives")


if __name__ == "__main__":
    main()
