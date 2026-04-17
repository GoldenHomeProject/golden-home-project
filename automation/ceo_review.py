"""GHP CEO Review — Agent 6 (meta) of the flywheel.

Runs Sundays. Reads every feedback signal the flywheel has produced this week,
asks Claude (reasoning as CEO) to identify what's working, what's not, what
to double down on or kill.

Output: BUSINESS_BRAIN.md gets a new WEEKLY REVIEW section appended.
Also: RESUME_PROMPT.md gets the next-session priority list updated.

This is the closed-loop feedback that turns data → strategy → better content next week.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _claude_api import call_claude

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "automation" / "logs"
BRAIN_PATH = ROOT / "BUSINESS_BRAIN.md"
POSTED_ARCHIVE = ROOT / "social" / "posted_archive.json"
TREND_DIR = ROOT / "automation" / "trends"


def gather_week_signals() -> dict:
    """Collect last 7 days of logs + archive + trends."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    signals: dict = {"week_ending": datetime.now(timezone.utc).strftime("%Y-%m-%d")}

    # Engagement logs
    eng_logs = sorted(LOG_DIR.glob("engagement_*.json"))[-7:]
    signals["engagement_week"] = [json.loads(p.read_text()) for p in eng_logs]

    # IG insights logs
    ins_logs = sorted(LOG_DIR.glob("ig_insights_*.json"))[-7:]
    signals["ig_insights_week"] = [json.loads(p.read_text()) for p in ins_logs]

    # Posted archive (last 14 entries — captures 1 week of 2x/day cadence)
    if POSTED_ARCHIVE.exists():
        archive = json.loads(POSTED_ARCHIVE.read_text())
        signals["recent_posts"] = archive[-14:]

    # Trend feeds to look for patterns
    trend_files = sorted(TREND_DIR.glob("*.json"))[-7:]
    signals["trend_feeds"] = [json.loads(p.read_text()) for p in trend_files]

    return signals


def ceo_analysis(signals: dict) -> str:
    prompt = f"""You are the CEO of Golden Home Project LLC. Review this week's raw data
and produce a strategic weekly review.

DATA:
{json.dumps(signals, indent=2, default=str)[:15000]}

Produce a markdown weekly review with these sections:

## WEEKLY REVIEW — {signals['week_ending']}

### What worked (ranked by $ signal)
- List top 3 content pieces by engagement. Cite like_count, comments_count, permalink.
- Note specific hooks/angles/categories that outperformed.

### What didn't work
- List 2-3 underperformers. Identify the pattern.

### Flywheel health
- Trend Scout: did it produce diverse, actionable opportunities?
- Content Engine: are scripts hitting AIDA + Grand Slam bars?
- Reel Producer: are reels posting successfully?
- Blog Writer: how many new posts? Any indexed in GSC yet?
- Repurposer: is 1→20 multiplier actually firing?

### Next week priorities (ranked by $ ROI)
- 3-5 concrete actions. Each tied to a specific agent or workflow.
- Call out any agent that needs a prompt/framework tweak.

### Hypothesis to test next week
- One specific bet + how you'll measure it.

Keep total length under 800 words. Be specific, not generic. If the data is too
sparse to draw conclusions, SAY SO explicitly rather than making things up."""

    return call_claude(prompt, max_tokens=3000)


def append_to_brain(review: str):
    if not BRAIN_PATH.exists():
        return
    brain = BRAIN_PATH.read_text()
    separator = "\n\n---\n\n"
    brain += separator + review.strip() + "\n"
    BRAIN_PATH.write_text(brain)


def main():
    print("[ceo-review] Gathering week signals...")
    signals = gather_week_signals()

    total_points = (
        len(signals.get("engagement_week", []))
        + len(signals.get("ig_insights_week", []))
        + len(signals.get("recent_posts", []))
    )
    if total_points == 0:
        print("[ceo-review] No data points this week. Skipping review.")
        return

    print(f"[ceo-review] Analyzing {total_points} data points...")
    review = ceo_analysis(signals)
    append_to_brain(review)

    # Also save standalone
    out = LOG_DIR / f"ceo_review_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    out.write_text(review)
    print(f"[ceo-review] Review written → BUSINESS_BRAIN.md + {out}")


if __name__ == "__main__":
    main()
