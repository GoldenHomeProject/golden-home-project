#!/usr/bin/env python3
"""Upload the newest queued presenter reel to YouTube Shorts.

Runs inside the presenter-yt GitHub Action. The Pi's run_presenter_reel.py
drops reel-<date>.mp4 + reel-<date>.json (title/description/privacy) into
social/reels/presenter/; this script uploads the newest one that has no
.uploaded marker, writes the marker, and removes the mp4 from git so the
repo doesn't accumulate video binaries.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "social" / "reels" / "presenter"


def main() -> int:
    if not QUEUE.exists():
        print("[presenter-yt] no queue dir — nothing to do")
        return 0
    jobs = sorted(QUEUE.glob("reel-*.json"))
    todo = [j for j in jobs if not j.with_suffix(".uploaded").exists()]
    if not todo:
        print("[presenter-yt] nothing pending")
        return 0
    job = todo[-1]
    meta = json.loads(job.read_text())
    video = QUEUE / meta["video"]
    if not video.exists():
        print(f"[presenter-yt] video missing for {job.name}; marking skipped")
        job.with_suffix(".uploaded").write_text(json.dumps({"skipped": "video missing"}))
        return 0

    desc_file = QUEUE / (job.stem + ".desc.txt")
    desc_file.write_text(meta.get("description", ""))
    cmd = [sys.executable, str(ROOT / "automation" / "post_to_youtube.py"),
           "--video", str(video),
           "--title", meta.get("title", "Golden Home Project finds")[:95],
           "--description", str(desc_file),
           "--privacy", meta.get("privacy", "public"),
           "--shorts"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-2000:])
    print(r.stderr[-2000:], file=sys.stderr)
    if r.returncode != 0:
        print("[presenter-yt] upload FAILED — leaving job pending for retry")
        desc_file.unlink(missing_ok=True)
        return 1
    job.with_suffix(".uploaded").write_text(
        r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "ok")
    desc_file.unlink(missing_ok=True)
    # Drop the binary from the working tree; the commit step removes it from git.
    video.unlink(missing_ok=True)
    print(f"[presenter-yt] uploaded {video.name}; marker written, binary removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
