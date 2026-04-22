"""GHP Content Quality Gate — rejects scripts that violate docs/BRAND_VOICE.md.

Runs between Content Engine and Reel Producer. Scripts that pass are left
in place. Scripts that fail are moved to `automation/content-review-queue/`
and removed from social/post_queue.json so Reel Producer never sees them.

Exit code: 0 always (this is a filter, not an error). Summary printed to stdout.

Reasons a script gets rejected (from docs/BRAND_VOICE.md):
1. Opens with a banned phrase
2. >5 hashtags
3. Product named before line 3
4. Contains banned hashtags
5. >1 exclamation mark
6. >1 long ALL CAPS word (>4 letters)
7. Missing falsifiable detail (no number/dimension/review count in caption)
8. Contains banned hype words (amazing, game-changer, insane, etc.)
"""
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "automation" / "scripts"
REVIEW_QUEUE = ROOT / "automation" / "content-review-queue"
REVIEW_QUEUE.mkdir(parents=True, exist_ok=True)
POST_QUEUE = ROOT / "social" / "post_queue.json"

BANNED_OPENERS = [
    r"^\s*i\s+spent\s+\$",
    r"^\s*\$\d+\s+turned\s+my",
    r"^\s*\$\d+\s+made\s+my",
    r"^\s*\$\d+\s+fixed\s+my",
    r"^\s*i\s+tested",
    r"^\s*you\s+need\s+this",
    r"^\s*game\s+changer",
    r"^\s*stop\s+scrolling",
    r"^\s*pov:",
    r"^\s*\$\d",  # any price-leading
]

BANNED_HASHTAGS = {
    "#gamechanger", "#musthave", "#viral", "#trending", "#fyp",
}

BANNED_HYPE_WORDS = [
    r"\bamazing\b", r"\bgame[-\s]?changer\b", r"\byou\s+won'?t\s+believe\b",
    r"\binsane\b", r"\bliterally\b", r"\blife[-\s]?changing\b",
    r"\bmust[-\s]?have\b", r"\bviral\b", r"\bobsessed\b",
]

FALSIFIABLE_PATTERN = re.compile(
    r"(\b\d+\s*(in|inch|inches|lb|lbs|oz|ml|ft|feet|cm|mm|year|yr|month|day|hour|minute|star|review)s?\b"
    r"|\b\d+[,.]?\d*\s*(reviews?|ratings?|stars?)\b"
    r"|\b\d+%\b"
    r"|\b\d+\s*piece\b)",
    re.IGNORECASE,
)

# Session 7: comment-to-DM CTA is mandatory (see docs/BRAND_VOICE.md + docs/REVENUE_RESEARCH_2026-04-21.md)
DM_CTA_PATTERN = re.compile(
    r"\bcomment\s+[A-Z]{3,}\b.*\b(dm|message|send)\b",
    re.IGNORECASE,
)


def first_n_chars(text: str, n: int = 40) -> str:
    return text.strip()[:n].lower()


def check_script(script_path: Path) -> tuple[bool, list[str]]:
    """Return (is_valid, reasons_failed)."""
    try:
        data = json.loads(script_path.read_text())
    except Exception as e:
        return False, [f"unreadable JSON: {e}"]

    caption = data.get("caption", "")
    hashtags = data.get("hashtags", [])
    primary_product = (data.get("affiliate_strategy") or {}).get("primary_product", "")

    reasons: list[str] = []

    # 1. Banned openers
    head = first_n_chars(caption, 60)
    for pattern in BANNED_OPENERS:
        if re.search(pattern, head, re.IGNORECASE):
            reasons.append(f"banned opener (matches /{pattern}/)")
            break

    # 2. Hashtag count
    if len(hashtags) > 5:
        reasons.append(f"too many hashtags: {len(hashtags)} (max 5)")

    # 3. Banned hashtags
    banned_found = [h for h in hashtags if h.lower().strip() in BANNED_HASHTAGS]
    if banned_found:
        reasons.append(f"banned hashtags: {banned_found}")

    # 4. Product named before line 3
    if primary_product:
        product_keyword = primary_product.split()[0].lower() if primary_product.split() else ""
        if product_keyword and len(product_keyword) > 3:
            lines = caption.split("\n")
            for line_num, line in enumerate(lines[:3], start=1):
                if product_keyword in line.lower():
                    reasons.append(f"product '{primary_product}' named in line {line_num} (must be line 3+)")
                    break

    # 5. Too many exclamation marks
    excl_count = caption.count("!")
    if excl_count > 1:
        reasons.append(f"too many exclamation marks: {excl_count} (max 1)")

    # 6. Long ALL CAPS words
    caps_words = re.findall(r"\b[A-Z]{5,}\b", caption)
    if len(caps_words) > 1:
        reasons.append(f"too many ALL CAPS long words: {caps_words}")

    # 7. Missing falsifiable detail
    if not FALSIFIABLE_PATTERN.search(caption):
        reasons.append("no falsifiable detail (needs dimension / review count / % / piece count)")

    # 8. Banned hype words
    for pattern in BANNED_HYPE_WORDS:
        if re.search(pattern, caption, re.IGNORECASE):
            reasons.append(f"banned hype word (matches /{pattern}/)")

    # 9. Missing comment-to-DM CTA (required for revenue funnel)
    if not DM_CTA_PATTERN.search(caption):
        reasons.append("missing comment-to-DM CTA ('comment KEYWORD and I'll DM you ...')")

    return len(reasons) == 0, reasons


def remove_from_queue(script_path: Path):
    """Remove any post_queue entry referencing this script."""
    if not POST_QUEUE.exists():
        return
    queue = json.loads(POST_QUEUE.read_text())
    rel = str(script_path.relative_to(ROOT))
    filtered = [entry for entry in queue if entry.get("script_path") != rel]
    if len(filtered) != len(queue):
        POST_QUEUE.write_text(json.dumps(filtered, indent=2))


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Only gate today's scripts — earlier days are already in production
    scripts = sorted(SCRIPT_DIR.glob(f"reel-{today}-*.json"))
    if not scripts:
        print(f"[quality-gate] No scripts for {today} to review.")
        return

    passed, failed = 0, 0
    for s in scripts:
        ok, reasons = check_script(s)
        if ok:
            print(f"  PASS  {s.name}")
            passed += 1
        else:
            print(f"  FAIL  {s.name}")
            for r in reasons:
                print(f"        - {r}")
            # Move to review queue
            dest = REVIEW_QUEUE / s.name
            shutil.move(str(s), str(dest))
            remove_from_queue(s)
            # Write reasons alongside
            (REVIEW_QUEUE / f"{s.stem}.reasons.txt").write_text(
                "\n".join(reasons) + f"\n\nReviewed: {datetime.now(timezone.utc).isoformat()}\n"
            )
            failed += 1

    print(f"[quality-gate] {passed} passed, {failed} rejected to {REVIEW_QUEUE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
