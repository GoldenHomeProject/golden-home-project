#!/usr/bin/env python3
"""hold_untrending_reels.py — Instagram's queue only posts reels for products selling NOW.

Ian, 2026-11-04: "hold the old reels, only post trending ones". A ready REELS entry whose
product is not on today's best-seller scan (social/chart_now.json) is set to
status "held_not_trending" (kept, never deleted); one that comes back onto the chart is
released. Non-reel entries (format images, carousels) are left alone.
Run daily on the Pi before the IG poster.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
Q = ROOT / "social" / "post_queue.json"


def main() -> int:
    try:
        cn = json.loads((ROOT / "social" / "chart_now.json").read_text())
        age = datetime.now(timezone.utc) - datetime.fromisoformat(cn["captured_at"])
        on = {i["asin"] for i in cn.get("items", [])}
    except (OSError, ValueError, KeyError):
        print("[hold-reels] no chart scan - leaving the queue alone")
        return 1
    if age.days > 3 or len(on) < 20:
        print(f"[hold-reels] chart scan stale or thin ({age.days}d, {len(on)}) - leaving the queue alone")
        return 1
    raw = json.loads(Q.read_text())
    q = raw if isinstance(raw, list) else raw.get("queue", [])
    held = released = 0
    for e in q:
        if e.get("media_type") != "REELS" or e.get("status") not in ("ready", "held_not_trending"):
            continue
        asin = e.get("asin")
        if not asin and e.get("script_path"):
            try:
                asin = json.loads((ROOT / e["script_path"]).read_text())["affiliate_strategy"]["amazon_asin"]
            except (OSError, ValueError, KeyError):
                asin = None
        if e["status"] == "ready" and asin not in on:
            e["status"] = "held_not_trending"
            held += 1
        elif e["status"] == "held_not_trending" and asin in on:
            e["status"] = "ready"
            released += 1
    Q.write_text(json.dumps(raw, indent=2))
    ready = sum(1 for e in q if e.get("media_type") == "REELS" and e.get("status") == "ready")
    print(f"[hold-reels] held {held}, released {released}; {ready} trending reels ready")
    if held or released:
        def _git(*a):
            return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True)
        _git("add", str(Q))
        _git("-c", "user.name=GHP Ops", "-c", "user.email=goldenhomeprojectllc@gmail.com",
             "commit", "-q", "-m", f"ig queue: held {held} / released {released} reels by chart")
        _git("-c", "rebase.autoStash=true", "pull", "--rebase", "-q", "origin", "main")
        r = _git("push", "-q", "origin", "main")
        print("[hold-reels] pushed" if r.returncode == 0 else f"[hold-reels] push failed {r.stderr[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
