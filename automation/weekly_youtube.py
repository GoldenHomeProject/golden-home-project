#!/usr/bin/env python3
"""weekly_youtube.py — one regular (landscape) YouTube video a week, with links that work.

YouTube made links in Shorts descriptions untappable in the Shorts player (2023), so the
daily Shorts' Amazon links get no clicks. A landscape video is never a Short, and its
description links ARE clickable. This stitches the week's daily videos into one 16:9 video
(brand panel left, the vertical clip right), adds YouTube chapters, and lists every
product with a working link. Ian asked for it 2026-11-03.

Runs in GitHub Actions (weekly-youtube.yml) where the YouTube token lives.
    python3 automation/weekly_youtube.py --yt-token /tmp/yt_token.json
    python3 automation/weekly_youtube.py --dry          # build only, no upload
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
from brand import CREAM, GOLD, INK, MUTED, font  # noqa: E402

LOGS = ROOT / "automation" / "logs"
REELS = ROOT / "social" / "reels"
W, H = 1920, 1080
CLIP_W = 608           # 1080x1920 scaled to the frame height
CLIP_X = W - CLIP_W - 150


def short_name(name: str, limit: int = 46) -> str:
    n = re.split(r"[,|(]| - ", name)[0].strip()
    parts = n.split()
    if len(parts) > 2 and (len(parts[0]) >= 3 and parts[0].isupper()
                           or re.match(r"^[A-Z][a-z]+[A-Z]", parts[0])):
        n = " ".join(parts[1:])                       # drop a leading brand token
    if len(n) > limit:
        n = n[:limit].rsplit(" ", 1)[0]
    # never end on a dangling connector ("...Set of", "...for")
    n = re.sub(r"(\s+(of|for|with|and|to|the|a|set|set of|pack|in|x|fits|up|upto|fits upto))+$", "", n, flags=re.I)
    return n.strip(" -,")


def week_items(days: int = 7, max_items: int = 8) -> list[dict]:
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out, seen = [], set()
    for f in sorted(LOGS.glob("gh_post_*.json")):
        try:
            d = json.loads(f.read_text())
            s = json.loads((ROOT / d.get("source", "")).read_text())
        except (OSError, ValueError):
            continue
        if str(d.get("date", "")) < cut:
            continue
        aff = s.get("affiliate_strategy") or {}
        asin, video = aff.get("amazon_asin"), REELS / str(d.get("video") or "")
        key = " ".join(short_name(aff.get("primary_product") or "").lower().split()[-2:])
        if not asin or asin in seen or key in seen or not video.is_file():
            continue
        seen.update({asin, key})                      # one fitted sheet a week, not two
        out.append({"date": d["date"], "asin": asin, "video": video,
                    "hook": (d.get("title") or s.get("hook") or "").strip().rstrip("."),
                    "name": short_name(aff.get("primary_product") or s.get("product_name") or "")})
    return out[-max_items:]


def _wrap(d, text, f, w):
    lines, cur = [], ""
    for word in text.split():
        t = f"{cur} {word}".strip()
        if d.textlength(t, font=f) <= w:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def panel(path: Path, kicker: str, title: str, sub: str, big: str = "") -> Path:
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    full = big == "full"
    x, y, tw = 140, (330 if full else 220), (W - 280 if full else CLIP_X - 260)
    d.rectangle([x, y, x + 22, y + 22], fill=GOLD)
    kf = font(30)
    k = kicker.upper()
    while d.textlength(k, font=kf) > tw - 40 and " " in k:   # never run under the clip
        k = k.rsplit(" ", 1)[0]
    d.text((x + 40, y - 6), k, font=kf, fill=MUTED)
    y += 70
    if big and big != "full":
        d.text((x, y), big, font=font(150), fill=GOLD)
        y += 180
    tf = font(96 if full else 68)
    for ln in _wrap(d, title, tf, tw)[:4]:
        d.text((x, y), ln, font=tf, fill=INK)
        y += 112 if full else 82
    y += 24
    for ln in _wrap(d, sub, font(38, bold=False), tw)[:3]:
        d.text((x, y), ln, font=font(38, bold=False), fill=MUTED)
        y += 50
    d.text((x, H - 120), "goldenhomeproject.com", font=font(32), fill=GOLD)
    img.save(path)
    return path


def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-600:])


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                        "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30",
       "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]


def card_segment(png: Path, secs: float, out: Path) -> Path:
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", str(secs), "-i", str(png),
         "-f", "lavfi", "-t", str(secs), "-i", "anullsrc=r=44100:cl=stereo",
         "-shortest", *ENC, str(out)])
    return out


def item_segment(png: Path, clip: Path, out: Path) -> Path:
    fc = (f"[1:v]scale={CLIP_W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={CLIP_W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1[c];[0:v][c]overlay={CLIP_X}:0[v]")
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(png), "-i", str(clip),
         "-filter_complex", fc, "-map", "[v]", "-map", "1:a?", "-shortest", *ENC, str(out)])
    return out


def ts(sec: float) -> str:
    s = int(sec)
    return f"{s // 60}:{s % 60:02d}"


def build(items: list[dict], work: Path) -> tuple[Path, list[tuple[float, str]]]:
    n = len(items)
    segs, chapters, t = [], [], 0.0
    intro = card_segment(panel(work / "intro.png", f"This week · {n} finds",
                               f"{n} home finds people are buying this week",
                               "Every link is in the description below.", big="full"),
                         3.0, work / "s00.mp4")
    segs.append(intro)
    t += duration(intro)
    for i, it in enumerate(items, 1):
        png = panel(work / f"p{i:02d}.png", it["hook"][:70] or "this week", it["name"],
                    "Link in the description", big=f"#{i}")
        seg = item_segment(png, it["video"], work / f"s{i:02d}.mp4")
        chapters.append((0.0 if i == 1 else t, f"#{i} {it['name']}"))
        t += duration(seg)
        segs.append(seg)
    segs.append(card_segment(panel(work / "outro.png", "Thanks for watching",
                                   "Every product from this video is linked below",
                                   "More from our videos: goldenhomeproject.com/links.html",
                                   big="full"), 4.0, work / "s99.mp4"))
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    out = work / "weekly.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", "-movflags", "+faststart", str(out)])
    return out, chapters


def description(items, chapters, day: str) -> str:
    d = day.replace("-", "")
    lines = [f"{len(items)} home finds from this week's Shorts, and here the links actually work.", ""]
    for i, it in enumerate(items, 1):
        lines += [f"#{i} {it['name']}",
                  f"https://www.amazon.com/dp/{it['asin']}?tag=ghpyoutube-20&ascsubtag=ghp-yt-weekly-{d}"]
    lines += ["", "Chapters:"] + [f"{ts(t)} {label}" for t, label in chapters]
    lines += ["", "Every product from our videos: https://goldenhomeproject.com/links.html?src=yt",
              "", "As an Amazon Associate I earn from qualifying purchases. Prices change; "
              "check the listing.", "", "#amazonfinds #homeorganization #homefinds"]
    return "\n".join(lines)


def upload(video: Path, title: str, desc: str, token_path: str) -> str | None:
    import requests
    sys.path.insert(0, str(ROOT / "automation"))
    from github_daily_poster import refresh_yt_token
    tok = refresh_yt_token(token_path)
    headers = {"Authorization": f"Bearer {tok.get('token') or tok.get('access_token')}"}
    meta = {"snippet": {"title": title[:100], "description": desc[:4900], "categoryId": "26",
                        "tags": ["amazon finds", "home organization", "home finds", "amazon home"]},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    init = requests.post("https://www.googleapis.com/upload/youtube/v3/videos"
                         "?uploadType=resumable&part=snippet,status",
                         headers={**headers, "Content-Type": "application/json",
                                  "X-Upload-Content-Type": "video/mp4"}, json=meta, timeout=30)
    if init.status_code != 200:
        print(f"[weekly-yt] init failed {init.status_code} {init.text[:200]}")
        return None
    with open(video, "rb") as f:
        r = requests.put(init.headers["Location"], data=f, timeout=600,
                         headers={**headers, "Content-Type": "video/mp4",
                                  "Content-Length": str(video.stat().st_size)})
    vid = r.json().get("id")
    print(f"[weekly-yt] uploaded https://youtube.com/watch?v={vid}" if vid else f"[weekly-yt] upload failed {r.text[:200]}")
    return vid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yt-token")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--out", help="keep the built video here (dry runs)")
    args = ap.parse_args()
    items = week_items()
    if len(items) < 4:
        print(f"[weekly-yt] only {len(items)} videos this week — skipping")
        return 0
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = f"{len(items)} Amazon Home Finds People Are Buying This Week ({datetime.now():%b %-d})"
    with tempfile.TemporaryDirectory() as tmp:
        video, chapters = build(items, Path(tmp))
        desc = description(items, chapters, day)
        print(f"[weekly-yt] built {duration(video):.0f}s video, {len(items)} items\n{title}\n{desc}")
        if args.out:
            Path(args.out).write_bytes(video.read_bytes())
        if args.dry or not args.yt_token:
            return 0
        vid = upload(video, title, desc, args.yt_token)
    (LOGS / f"yt_weekly_{day}.json").write_text(json.dumps(
        {"date": day, "youtube": vid, "title": title, "items": [i["asin"] for i in items]}, indent=1))
    return 0 if vid else 1


if __name__ == "__main__":
    raise SystemExit(main())
