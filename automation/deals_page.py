#!/usr/bin/env python3
"""deals_page.py — goldenhomeproject.com/r/deals: every verified price drop, refreshed daily.

Why (2026-11-24, Black Friday week): the click audit showed ~4 real people a month reach
Amazon from us, so the content that gets the few visitors we have must be the highest
buying intent we can honestly offer. That is a price drop we observed ourselves:
price_drops.py compares today's chart price with our own daily snapshots (14-day median).

One page, linked from every reel caption, YouTube description and deals pin this week.
Honesty rules: price bands only (exact prices go stale and Associates requires current
ones), the % is ours and says what it is measured against, no product photos, no claims
that we used anything.

Tracking: default tag is the website's; ?src=pin|yt|ig and ?v=A|B retag in the browser,
the same way the /r/ reel pages and gift guides do.

    python3 automation/deals_page.py [--min-pct 8] [--max 30]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
from brand import price_band  # noqa: E402

SOCIAL = ROOT / "social"
OUT = ROOT / "r" / "deals.html"
SITE = "https://goldenhomeproject.com"
TAG = "goldenhomep0a-20"                      # website/direct (affiliate_links.CHANNEL_TAGS)
TEMPLATE = ROOT / "blog" / "posts" / "best-bathroom-essentials.html"

RETAG = ('<script>(function(){var q=new URLSearchParams(location.search);'
         'var t={A:"ghpbranda-20",B:"ghpbrandb-20"}[q.get("v")]||'
         '{pin:"ghppinterest-20",yt:"ghpyoutube-20",ig:"ghpig-20"}[q.get("src")];if(!t)return;'
         'var s="deals_"+(q.get("src")||"pin");'
         "document.querySelectorAll('a[href*=\"amazon.com/dp/\"]').forEach(function(a){try{"
         'var u=new URL(a.href);u.searchParams.set("tag",t);'
         'u.searchParams.set("ascsubtag",(u.searchParams.get("ascsubtag")||"deals")+"_"+s);'
         "a.href=u.toString();}catch(e){}});})();</script>")


def _short(name: str, limit: int = 72) -> str:
    name = re.split(r"\s[|–—-]\s|,", name or "")[0].strip()
    if len(name) <= limit:
        return name
    return name[:limit].rsplit(" ", 1)[0].rstrip(" ,-") + "…"


def load() -> tuple[list[dict], str]:
    drops = json.loads((SOCIAL / "price_drops.json").read_text()).get("drops", [])
    chart = json.loads((SOCIAL / "chart_now.json").read_text())
    cat = {i["asin"]: i.get("category") or "Home" for i in chart.get("items", [])}
    try:
        from pinterest_pipeline import _blocked_product
    except Exception:  # noqa: BLE001 — the filter is a nicety, never a blocker
        def _blocked_product(_n):
            return None
    rows = []
    for d in drops:
        if d.get("asin") not in cat:          # only products on today's chart
            continue
        if _blocked_product(d.get("title", "")):
            continue
        if (d.get("rating") or 0) < 4.3 or (d.get("reviews") or 0) < 1000:
            continue
        rows.append({**d, "category": cat[d["asin"]]})
    return rows, (chart.get("captured_at") or "")[:10]


def render(rows: list[dict], day: str) -> str:
    when = datetime.fromisoformat(day).strftime("%B %-d, %Y") if day else ""
    title = "Black Friday home deals we tracked ourselves"
    desc = (f"{len(rows)} Amazon home best-sellers priced below their usual price, checked "
            f"against our own daily price tracking. Updated {when}.")
    url = f"{SITE}/r/deals"
    head = TEMPLATE.read_text().split("<body>")[0]
    head = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', "", head, flags=re.S)
    head = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)} | Golden Home Project</title>",
                  head, flags=re.S)
    for attr in ('name="description"', 'property="og:description"'):
        head = re.sub(rf'(<meta {attr} content=")[^"]*', lambda m: m.group(1) + html.escape(desc), head)
    head = re.sub(r'(<meta property="og:title" content=")[^"]*', lambda m: m.group(1) + html.escape(title), head)
    head = re.sub(r'(<link rel="canonical" href=")[^"]*', lambda m: m.group(1) + url, head)
    head = re.sub(r'(<meta property="og:url" content=")[^"]*', lambda m: m.group(1) + url, head)
    if 'name="robots"' not in head:
        head = head.replace("<head>", '<head>\n  <meta name="robots" content="noindex">', 1)

    sub = f"deals_{day.replace('-', '')}"
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["category"], []).append(r)
    sections = []
    for name, items in sorted(groups.items(), key=lambda kv: -max(i["pct"] for i in kv[1])):
        cards = []
        for r in items:
            facts = " &middot; ".join((f"{r['rating']}&#9733;", f"{int(r['reviews']):,}+ ratings",
                                       html.escape("now " + price_band(r["now"]).lower())))
            basis = ("below its typical price over the past two weeks"
                     if r.get("basis") == "14-day median"
                     else f"lower than when we last saw it ({r['observed_from']})")
            cards.append(f"""    <div class="product-card">
      <span class="pick-badge">About {r['pct']:.0f}% off</span>
      <div class="product-name">{html.escape(_short(r['title']))}</div>
      <div class="product-rating">{facts}</div>
      <ul class="value-stack"><li>About {r['pct']:.0f}% {basis}, from our own daily tracking.</li></ul>
      <a class="cta" href="https://www.amazon.com/dp/{r['asin']}?tag={TAG}&amp;ascsubtag={sub}" rel="sponsored nofollow noopener" target="_blank">Check today's price &rarr;</a>
    </div>""")
        sections.append(f'  <section class="post-section">\n    <h2>{html.escape(name)}</h2>\n'
                        + "\n".join(cards) + "\n  </section>")
    return f"""{head}<body>
<div class="wrap">
  <h1>{html.escape(title)}</h1>
  <div class="affiliate-disclosure">As an Amazon Associate, Golden Home Project earns from qualifying purchases. Deals change by the hour; the live listing is the real price.</div>
  <div class="intro"><p>We check Amazon's home best-seller charts every morning. These {len(rows)} are on the chart today <strong>and</strong> cost less than their typical price over the past two weeks, by our own tracking, not a "was" price from the listing. We have not tested these ourselves; the ratings are the evidence. Updated {when}.</p></div>
{chr(10).join(sections)}
  <a class="back-link" href="/links.html">&larr; More finds from our videos</a>
</div>
{RETAG}
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-pct", type=float, default=8.0)
    ap.add_argument("--max", type=int, default=30)
    args = ap.parse_args()
    rows, day = load()
    rows = sorted((r for r in rows if r["pct"] >= args.min_pct), key=lambda r: -r["pct"])[:args.max]
    if len(rows) < 3:
        print(f"[deals] only {len(rows)} verified drops >= {args.min_pct}% on today's chart; page left as is")
        return 0
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(rows, day))
    print(f"[deals] wrote {OUT} with {len(rows)} deals ({day})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
