#!/usr/bin/env python3
"""Pop the next un-DMed creator from strategy/path_c_dm_queue.json and
ship the DM via automation/send_ig_dm.py.

Cron-friendly entry point that wraps send_ig_dm with queue logic.
Exits 0 with "no candidates" if all targets already DMed within their
14-day window (see send_ig_dm.py guard).

Run (cron on Pi):
    xvfb-run -a ~/.ghp-engagement/venv/bin/python automation/path_c_send_next.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "strategy" / "path_c_dm_queue.json"
LOG = ROOT / "social" / "engagement_log.json"
SENDER = ROOT / "automation" / "send_ig_dm.py"
RECENT_DAYS = 14


def recently_dmed(handle: str) -> bool:
    if not LOG.exists():
        return False
    try:
        data = json.loads(LOG.read_text())
    except Exception:
        return False
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).isoformat()
    for a in reversed(data.get("actions", [])):
        if (a.get("target") or "").lower() == handle.lower() \
                and (a.get("action") or "").startswith("dm_") \
                and (a.get("timestamp") or "") > cutoff:
            return True
    return False


def main() -> int:
    if not QUEUE.exists():
        print(f"[path-c] queue missing: {QUEUE.relative_to(ROOT)}", file=sys.stderr)
        return 1
    queue = json.loads(QUEUE.read_text())
    # Sort by priority asc, lower priority = more urgent.
    queue.sort(key=lambda q: q.get("priority", 999))

    candidate = None
    for q in queue:
        h = (q.get("handle") or "").strip()
        if not h:
            continue
        if recently_dmed(h):
            print(f"[path-c] skipping @{h} — DMed in last {RECENT_DAYS}d")
            continue
        candidate = q
        break

    if candidate is None:
        print("[path-c] no candidates left in window; nothing to send")
        return 0

    handle = candidate["handle"]
    body = candidate["body"]
    print(f"[path-c] sending DM to @{handle} ({len(body)} chars)")

    # Write body to a tmpfile and invoke send_ig_dm.py
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".txt", delete=False, dir="/tmp",
    ) as f:
        f.write(body)
        body_path = f.name

    cmd = [sys.executable, str(SENDER), "--handle", handle, "--body-file", body_path]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=180)
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    # send_ig_dm exits 0 on sent/dry_run_ok/already_dmed_in_window
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
