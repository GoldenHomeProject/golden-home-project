#!/usr/bin/env python3
"""build_video_links.py — "From our videos": every recent video's product, one tap away.

Instagram captions and YouTube Shorts descriptions cannot carry clickable links, so every
caption says "link in bio". The bio led to links.html, which had not changed since
2026-09-15 and held ZERO product links (found 2026-11-03): a viewer who wanted the item from
a video had nowhere to find it. This rebuilds a section at the top of links.html from the
daily poster's logs (each records the video, its hook and its source script with the ASIN),
newest first, and puts a banner on the homepage pointing at it.

Links use the Instagram tracking ID; ?src=yt on the page swaps them to the YouTube one so
Associates still splits revenue by channel.

Run (Pi, cron):  python3 automation/build_video_links.py
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
from pinterest_pipeline import _short_name, _strip_brand  # noqa: E402

LOGS = ROOT / "automation" / "logs"
LINKS = ROOT / "links.html"
INDEX = ROOT / "index.html"
START, END = "<!-- VIDEO_PICKS_START -->", "<!-- VIDEO_PICKS_END -->"
BSTART, BEND = "<!-- VIDEO_BANNER_START -->", "<!-- VIDEO_BANNER_END -->"
DAYS = 30


def recent_videos() -> list[dict]:
    cut = (datetime.now() - timedelta(days=DAYS)).strftime("%Y-%m-%d")
    out, seen = [], set()
    for f in sorted(LOGS.glob("gh_post_*.json"), reverse=True):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if str(d.get("date", "")) < cut:
            break
        try:
            s = json.loads((ROOT / d.get("source", "")).read_text())
        except (OSError, ValueError):
            continue
        aff = s.get("affiliate_strategy") or {}
        asin = aff.get("amazon_asin")
        name = aff.get("primary_product") or s.get("product_name") or ""
        if not asin or asin in seen or not re.fullmatch(r"[A-Z0-9]{10}", asin):
            continue
        seen.add(asin)
        out.append({"date": d["date"], "hook": (d.get("title") or s.get("hook") or "").strip(),
                    "asin": asin, "name": _strip_brand(_short_name(name, limit=70)),
                    "yt": d.get("youtube")})
    return out


def section(videos: list[dict]) -> str:
    cards = []
    for v in videos:
        day = datetime.strptime(v["date"], "%Y-%m-%d").strftime("%b %-d")
        url = f"https://www.amazon.com/dp/{v['asin']}?tag=ghpig-20&ascsubtag=links_{v['date'].replace('-', '')}"
        cards.append(
            f'<a class="vp-card" href="{html.escape(url)}" rel="sponsored nofollow noopener" target="_blank">'
            f'<span class="vp-date">{day}</span>'
            f'<span class="vp-hook">{html.escape(v["hook"])}</span>'
            f'<span class="vp-name">{html.escape(v["name"])}</span>'
            f'<span class="vp-btn">View on Amazon &rarr;</span></a>')
    return f"""{START}
<style>
.vp-wrap{{margin:8px 0 28px}}.vp-wrap h2{{font-size:1.15rem;margin:0 0 4px;color:var(--gold,#d4a745)}}
.vp-wrap p.vp-sub{{font-size:.85rem;color:var(--text-secondary,#a8a4a0);margin:0 0 14px}}
.vp-card{{display:block;text-decoration:none;color:inherit;padding:14px 16px;margin:0 0 10px;
 border:1px solid rgba(212,167,69,.25);border-radius:12px;background:rgba(255,255,255,.03)}}
.vp-date{{display:block;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted,#8a857c)}}
.vp-hook{{display:block;font-weight:600;margin:2px 0 4px}}
.vp-name{{display:block;font-size:.85rem;color:var(--text-secondary,#a8a4a0)}}
.vp-btn{{display:inline-block;margin-top:8px;font-size:.85rem;font-weight:600;color:var(--gold,#d4a745)}}
</style>
<section class="vp-wrap" id="from-videos">
<h2>From our videos</h2>
<p class="vp-sub">Saw something in a Reel or Short? It's here, newest first. Amazon affiliate links:
we may earn a small commission at no extra cost to you.</p>
{''.join(cards)}
</section>
<script>(function(){{if(new URLSearchParams(location.search).get("src")!=="yt")return;
document.querySelectorAll('#from-videos a[href*="amazon.com/dp/"]').forEach(function(a){{try{{
var u=new URL(a.href);u.searchParams.set("tag","ghpyoutube-20");a.href=u.toString();}}catch(e){{}}}});}})();</script>
{END}"""


BANNER = f"""{BSTART}
<a href="/links.html#from-videos" style="display:block;text-align:center;padding:10px 16px;
background:#d4a745;color:#0a0a0a;font-weight:700;text-decoration:none;font-size:15px">
Saw a product in one of our videos? Find it here &rarr;</a>
{BEND}"""


def put(text: str, block: str, start: str, end: str, anchor: str) -> str:
    if start in text:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), lambda _: block, text, flags=re.S)
    i = text.index(anchor) + len(anchor)
    return text[:i] + "\n" + block + "\n" + text[i:]


def main() -> int:
    vids = recent_videos()
    if not vids:
        print("[video-links] no recent videos found — leaving pages alone")
        return 1
    page = LINKS.read_text()
    if START in page:
        page = put(page, section(vids), START, END, "")
    else:   # first run: right under the profile header, above the Storefront button
        cta = "  <!-- Primary CTA: Amazon Storefront -->"
        page = page.replace(cta, section(vids) + "\n\n" + cta, 1)
    LINKS.write_text(page)
    idx = INDEX.read_text()
    if BSTART not in idx:
        INDEX.write_text(put(idx, BANNER, BSTART, BEND, "<body>"))
    print(f"[video-links] {len(vids)} video products on links.html (newest {vids[0]['date']})")

    def _git(*a):
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True)
    _git("add", str(LINKS), str(INDEX))
    if _git("diff", "--staged", "--quiet").returncode:
        _git("-c", "user.name=GHP Ops", "-c", "user.email=goldenhomeprojectllc@gmail.com",
             "commit", "-q", "-m", f"links page: {len(vids)} video products")
        _git("-c", "rebase.autoStash=true", "pull", "--rebase", "-q", "origin", "main")
        r = _git("push", "-q", "origin", "main")
        print("[video-links] pushed" if r.returncode == 0 else f"[video-links] push failed {r.stderr[:150]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
