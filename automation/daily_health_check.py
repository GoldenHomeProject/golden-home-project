#!/usr/bin/env python3
"""GHP daily output verification — checks that EVERY revenue channel produced
fresh content, not just that the cron exited 0.

Why this exists: three times in June 2026 a pipeline "ran" nightly (green cron)
but produced nothing for days — most painfully Pinterest, dark 6 days behind a
missing-board bug while reels kept posting so the old watchdog stayed green.
The old watchdog only watched ONE feed (social/posted_archive.json). This checks
each channel's actual artifact freshness and pushes a digest to the phone (ntfy):
green = quiet low-priority push, anything stale = loud high-priority push.

Runs daily via ghp-health.timer (08:00 ET). Reuses NTFY_TOPIC from the existing
~/claude-skill/config/env (same topic the uptime watchdog uses).
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path.home() / "golden-home-project"
LEDGER = Path.home() / ".ghp-engagement" / "pinterest_posted_ledger.json"
ENV_FILE = Path.home() / "claude-skill" / "config" / "env"
# Out of the repo on purpose: the 06:30 ghp-daily-loop runs `git reset --hard
# origin/main`, which wiped uncommitted appends to a repo-path log (history
# never accumulated). Same reset-proof pattern as the Pinterest ledger.
DIGEST_LOG = Path.home() / ".ghp-engagement" / "daily_health.log"

NOW = datetime.now(timezone.utc)


def _hours(ts: str) -> float | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (NOW - dt).total_seconds() / 3600.0
    except ValueError:
        return None


def _load(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def check_pinterest() -> dict:
    """Fresh pin within 48h, and the queue isn't starved of pendings."""
    q = _load(REPO / "social" / "pinterest_queue.json", [])
    posted_ts = [p.get("posted_at", "") for p in q if p.get("posted_at")]
    led = _load(LEDGER, {"posted": []}).get("posted", [])
    posted_ts += [e.get("ts", "") for e in led]
    ages = [a for a in (_hours(t) for t in posted_ts) if a is not None]
    last = min(ages) if ages else None
    pending = sum(1 for p in q if not p.get("posted"))
    if last is None:
        return {"name": "Pinterest", "ok": False, "detail": "no posts ever recorded"}
    stale = last > 48
    note = f"last pin {last:.0f}h ago, {pending} pending"
    if pending == 0 and last > 24:
        return {"name": "Pinterest", "ok": False, "detail": note + " (QUEUE EMPTY — generator starved)"}
    return {"name": "Pinterest", "ok": not stale, "detail": note}


def check_reels() -> dict:
    """Daily reel published to IG/YT/FB within 48h (newest gh_post log)."""
    logs = sorted((REPO / "automation" / "logs").glob("gh_post_*.json"))
    if not logs:
        return {"name": "Reels(IG/YT/FB)", "ok": False, "detail": "no gh_post logs"}
    newest = logs[-1]
    try:
        d = newest.stem.replace("gh_post_", "")
        age = _hours(d + "T12:00:00Z")
    except Exception:
        age = None
    data = _load(newest, {})
    plats = [k for k in ("youtube", "instagram", "facebook") if data.get(k)]
    if age is None or age > 48:
        return {"name": "Reels(IG/YT/FB)", "ok": False,
                "detail": f"last {newest.stem.replace('gh_post_', '')} ({'?' if age is None else f'{age:.0f}h'})"}
    return {"name": "Reels(IG/YT/FB)", "ok": True,
            "detail": f"{newest.stem.replace('gh_post_', '')} -> {'+'.join(plats) or 'none?'}"}


def check_youtube_bridge() -> dict:
    """Presenter reel -> YouTube Shorts upload marker within 48h."""
    qdir = REPO / "social" / "reels" / "presenter"
    marks = sorted(qdir.glob("reel-*.uploaded")) if qdir.exists() else []
    real = [m for m in marks if "test" not in m.name]
    if not real:
        return {"name": "YouTube-Shorts", "ok": False, "detail": "no upload markers"}
    newest = real[-1]
    d = newest.stem.replace("reel-", "")
    age = _hours(d + "T23:30:00Z")
    if age is None or age > 48:
        return {"name": "YouTube-Shorts", "ok": False, "detail": f"last {d} ({'?' if age is None else f'{age:.0f}h'})"}
    return {"name": "YouTube-Shorts", "ok": True, "detail": f"uploaded {d}"}


def check_blog() -> dict:
    """Newest blog post within 9 days (weekly cadence + buffer)."""
    posts = sorted((REPO / "blog" / "posts").glob("*.html"))
    if not posts:
        return {"name": "Blog", "ok": False, "detail": "no posts"}
    newest = max(posts, key=lambda p: p.stat().st_mtime)
    age_days = (NOW.timestamp() - newest.stat().st_mtime) / 86400.0
    return {"name": "Blog", "ok": age_days <= 9,
            "detail": f"newest {age_days:.0f}d old ({newest.name[:34]})"}


def ntfy(title: str, body: str, priority: str, tags: str) -> None:
    topic = ""
    try:
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("NTFY_TOPIC="):
                topic = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    except Exception:
        pass
    if not topic:
        print("[health] NTFY_TOPIC missing — cannot push")
        return
    subprocess.run(
        ["curl", "-sf", "-m", "10",
         "-H", f"Title: {title}", "-H", f"Priority: {priority}", "-H", f"Tags: {tags}",
         "-d", body, f"https://ntfy.sh/{topic}"],
        capture_output=True)


def main() -> int:
    checks = [check_pinterest(), check_reels(), check_youtube_bridge(), check_blog()]
    stale = [c for c in checks if not c["ok"]]
    date = NOW.strftime("%Y-%m-%d")

    lines = [f"{'STALE' if not c['ok'] else 'ok   '} {c['name']:18} {c['detail']}" for c in checks]
    digest = f"{date}  " + " | ".join(
        f"{c['name'].split('(')[0]}={'OK' if c['ok'] else 'STALE'}" for c in checks)
    DIGEST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DIGEST_LOG.open("a") as f:
        f.write(digest + "\n")
    print(digest)
    print("\n".join(lines))

    # Notify the owner ONLY when something is broken. Healthy days stay silent —
    # the digest still lands in social/daily_health.log as the self-monitoring
    # record, but no phone push when all channels are fresh (owner's call 6/16:
    # "only email if something is broken or you have a question").
    if stale:
        ntfy(
            f"⚠️ GHP: {len(stale)} channel(s) STALE",
            "Not posting fresh content:\n" + "\n".join(
                f"• {c['name']}: {c['detail']}" for c in stale)
            + "\n\nA pipeline is silently failing — check the Pi.",
            "high", "warning")
        print("[health] STALE — owner notified via ntfy")
    else:
        print("[health] all fresh — no notification (silent on green)")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
