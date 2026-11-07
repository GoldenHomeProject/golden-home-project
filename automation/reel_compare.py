#!/usr/bin/env python3
"""reel_compare.py — v1 vs v2 reel comparison for the weekly report (Marketing, 2026-11-07).

Ian approved posting the v2 trend reels on 2026-11-07; they take the daily noon slot on
alternate days (social/reel_v2_schedule.json), v1 reels the days between, so both run at
the same hour. This reads the daily poster's own logs (automation/logs/gh_post_*.json) to
know which Instagram media is v1 and which is v2, pulls each reel's Instagram insights, and
counts comment-for-link replies per keyword from social/engagement_log.json.

Our Meta app has no instagram_manage_insights permission (App Review), so the API gives
only likes, comments and permalinks; plays, average watch time (for watch %), saves and
shares are read off Instagram's own insights screen by the weekly report, using the
permalinks written here. Instagram shows no 3-second-hold number; the report uses
average watch time / reel length as the hold proxy. Link clicks and orders by ascsubtag come from the Amazon
Associates report (the weekly report reads it there): v2 IG = ascsubtag reel_<kw>_*,
v2 Pinterest = reel_<kw>_*_pin, YouTube = ghp-yt-<date> on v2 vs v1 dates.

Run (Pi cron, daily):  python3 automation/reel_compare.py
Writes social/reel_v1_v2_compare.json and prints a short table.
"""
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "automation" / "logs"
OUT = ROOT / "social" / "reel_v1_v2_compare.json"
SINCE = "2026-11-01"
GRAPH = "https://graph.facebook.com/v21.0"
METRICS = "plays,reach,likes,comments,saves,shares,ig_reels_avg_watch_time"


def _tokens():
    t = json.loads((LOGS / "meta_tokens.json").read_text())
    return t["page_access_token"]


def _get(path, token, **params):
    q = urllib.parse.urlencode({**params, "access_token": token})
    try:
        with urllib.request.urlopen(f"{GRAPH}{path}?{q}", timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:120]}


def _length(video: Path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def main() -> int:
    token = _tokens()
    sched = json.loads((ROOT / "social" / "reel_v2_schedule.json").read_text())
    v2_days = set(sched)
    try:
        eng = json.loads((ROOT / "social" / "engagement_log.json").read_text())
        eng = eng if isinstance(eng, list) else eng.get("entries", [])
    except (OSError, ValueError):
        eng = []
    rows = []
    for log in sorted(LOGS.glob("gh_post_*.json")):
        d = json.loads(log.read_text())
        day = d.get("date", "")
        if day < SINCE or not d.get("instagram"):
            continue
        variant = "v2" if d.get("source_kind") == "reel_v2" or day in v2_days and "v2_test" in str(d.get("video")) else "v1"
        m = _get(f"/{d['instagram']}", token, fields="like_count,comments_count,permalink")
        m.pop("id", None)
        vid = ROOT / "social" / "reels" / str(d.get("video") or "")
        length = _length(vid) if vid.exists() else None
        kw = (sched.get(day) or {}).get("keyword") if variant == "v2" else None
        replies = sum(1 for e in eng if e.get("type") == "comment_reply_link"
                      and (kw and e.get("keyword") == kw)) if kw else None
        rows.append({"date": day, "variant": variant, "title": d.get("title"), "ig_media": d["instagram"],
                     "youtube": d.get("youtube"), "length_s": round(length, 1) if length else None,
                     **m, "plays": None, "saves": None, "shares": None, "avg_watch_s": None,
                     "watch_pct": None,  # filled by the weekly report from IG insights
                     "keyword": kw, "link_replies": replies})
    summary = {}
    for v in ("v1", "v2"):
        rs = [r for r in rows if r["variant"] == v]
        if not rs:
            continue
        def avg(k):
            xs = [r[k] for r in rs if isinstance(r.get(k), (int, float))]
            return round(sum(xs) / len(xs), 1) if xs else None
        summary[v] = {"reels": len(rs), **{k: avg(k) for k in
                      ("like_count", "comments_count", "link_replies")}}
    OUT.write_text(json.dumps({"updated": datetime.now().isoformat(timespec="minutes"),
                               "note": "watch_pct = avg watch time / reel length (IG has no 3-second-hold "
                                       "metric). Clicks and orders: Associates report by ascsubtag.",
                               "summary": summary, "reels": rows}, indent=1))
    for v, s in summary.items():
        print(v, s)
    for r in rows:
        print(r["date"], r["variant"], r.get("like_count"), r.get("comments_count"), r.get("permalink"), (r["title"] or "")[:40])
    return 0


if __name__ == "__main__":
    sys.exit(main())
