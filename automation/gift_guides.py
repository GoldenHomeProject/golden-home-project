#!/usr/bin/env python3
"""gift_guides.py — holiday gift-guide pages by recipient and budget (Q4 2026).

Marketing dept, 2026-11-05 (Ian's mandate: "get us sales and revenue"): gift searches by
recipient + budget are the highest-intent Pinterest searches of the year, planned 30-45
days ahead. Each guide is a real page on our site (pins link here, ?v=A|B keeps the brand
test's attribution), rebuilt daily from today's best-seller scan so every pick is selling
now, under the budget, 4.5+ stars with thousands of reviews, and judged giftable.

Honesty: every line about a product comes from its listing title, rating and review count.
No "we love", no "perfect for everyone", no claims the title does not make.

Run (Pi cron, after chart_scan.py):  python3 automation/gift_guides.py
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
import pinterest_pipeline as pp  # noqa: E402
from brand import price_band  # noqa: E402
from content_quality_gate import fabrication_match  # noqa: E402

POSTS = ROOT / "blog" / "posts"
STATE = ROOT / "social" / "gift_guides.json"
TEMPLATE = POSTS / "best-bathroom-essentials.html"   # site head + styles
SITE = "https://goldenhomeproject.com"

GUIDES = [
    dict(slug="housewarming-gifts-for-new-homeowners-under-25", cap=25,
         title="Housewarming Gifts for New Homeowners Under $25",
         who="someone who just moved into their first house",
         search="housewarming gifts for new homeowners"),
    dict(slug="first-apartment-gifts-under-30", cap=30,
         title="First Apartment Gifts Under $30",
         who="someone setting up their first apartment", search="first apartment gifts"),
    dict(slug="hostess-gifts-under-20", cap=20,
         title="Hostess Gifts Under $20",
         who="the friend hosting dinner or the holidays", search="hostess gifts"),
    dict(slug="stocking-stuffers-for-the-home-under-15", cap=15,
         title="Stocking Stuffers for the Home Under $15",
         who="anyone, small and practical for a stocking", search="stocking stuffers for adults"),
    dict(slug="teacher-gifts-under-15", cap=15,
         title="Teacher Gifts Under $15",
         who="a teacher, something useful for home or a classroom desk", search="teacher gifts"),
    dict(slug="white-elephant-gifts-under-25", cap=25,
         title="White Elephant Gifts Under $25 People Actually Want",
         who="a white elephant or gift-swap exchange", search="white elephant gift ideas"),
]


def _price(p) -> float | None:
    m = re.search(r"[\d,]+\.\d{2}", str(p or ""))
    return float(m.group().replace(",", "")) if m else None


def _num(x) -> float:
    m = re.search(r"[\d,]+(?:\.\d+)?", str(x or ""))
    return float(m.group().replace(",", "")) if m else 0.0


def candidates(cap: float) -> list[dict]:
    on_chart = {i["asin"] for i in pp.chart_now()}
    items = [dict(i, chart=True) for i in pp.chart_now() if (_price(i.get("price")) or 99) <= cap]
    # Under-$15 guides run short on chart products; add our other vetted, proven products.
    seen = {i["asin"] for i in items}
    reg = json.loads((ROOT / "social" / "dm_keyword_registry.json").read_text())
    for e in pp.registry_entries(reg):
        a = e.get("asin")
        pr = _price(e.get("verified_price"))
        if (not a or a in seen or e.get("status") != "live" or pr is None or not 5 <= pr <= cap
                or _num(e.get("verified_stars")) < 4.5 or _num(e.get("verified_reviews")) < 1000
                or pp._blocked_product(e.get("product_name") or "")):
            continue
        seen.add(a)
        items.append({"asin": a, "name": e.get("product_name") or "", "price": e.get("verified_price"),
                      "rating": _num(e.get("verified_stars")), "reviews": int(_num(e.get("verified_reviews"))),
                      "rank": 99, "chart": a in on_chart})
    if not items:
        return []
    ents = [{"asin": i["asin"], "product_name": i["name"], "verified_stars": str(i.get("rating")),
             "verified_reviews": i.get("reviews"), "categories": [i.get("category", "")]} for i in items]
    scores = pp.giftability(ents)
    good = [i for i in items if scores.get(i["asin"], 0) >= 7]
    return sorted(good, key=lambda i: (-scores.get(i["asin"], 0), i.get("rank") or 99))[:20]


def choose(g: dict, cands: list[dict]) -> list[dict]:
    if len(cands) < 4:
        return []
    lst = "\n".join(f"{n}: {c['name']}" for n, c in enumerate(cands))
    try:
        from _claude_api import _load_token_file
        _load_token_file()
    except Exception:
        pass
    prompt = (f"Gift guide: {g['title']} - for {g['who']}.\nBest-selling products under the budget:\n"
              f"{lst}\nPick the 6 that make the best gifts for that person (fewer if fewer fit; "
              "no two of the same type). For each give a short reason it suits them, using ONLY "
              "facts in its title (no claims about quality, durability or results, no first "
              "person, no prices or numbers unless in the title, under 16 words). Reply ONLY JSON: "
              '{"picks": [{"i": <index>, "type": "<generic item, 2-4 words, Title Case>", '
              '"why": "<reason>"}], "intro": "<2 sentences on what makes a good gift for this '
              'person, general advice, no product claims>"}')
    d = None
    for _attempt in range(2):          # the CLI occasionally answers without JSON
        try:
            out = subprocess.run(["claude", "-p", "--max-turns", "1"], input=prompt,
                                 capture_output=True, text=True, timeout=180).stdout
            d = json.loads(re.search(r"\{.*\}", out, re.S).group())
            break
        except Exception as e:  # noqa: BLE001
            print(f"  [gift] {g['slug']}: claude reply unusable ({str(e)[:60]})")
    if not d:
        return []
    picks = []
    for p in d.get("picks", [])[:6]:
        try:
            c = cands[int(p["i"])]
        except (KeyError, ValueError, IndexError):
            continue
        text = f"{p.get('type', '')} {p.get('why', '')}"
        allowed = set(re.findall(r"\d+", c["name"]))
        if ("$" in text or fabrication_match(text)
                or any(n not in allowed for n in re.findall(r"\d+", text))):
            continue
        picks.append({**c, "type": p.get("type", ""), "why": p.get("why", "")})
    if len(picks) < 4:
        return []
    g["intro"] = d.get("intro", "") if not fabrication_match(d.get("intro", "")) else ""
    return picks


def render(g: dict, picks: list[dict]) -> str:
    head = TEMPLATE.read_text().split("<body>")[0]
    now = datetime.now()
    month = now.strftime("%B %Y")
    title = f"{g['title']} ({month})"
    desc = (f"{len(picks)} {g['title'].lower()}, each rated 4.5 stars or higher across "
            f"thousands of ratings. Updated {now:%B %-d, %Y}.")
    url = f"{SITE}/blog/posts/{g['slug']}.html"
    head = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)} | Golden Home Project</title>", head, flags=re.S)
    head = re.sub(r'(<meta name="description" content=")[^"]*', lambda m: m.group(1) + html.escape(desc), head)
    head = re.sub(r'(<link rel="canonical" href=")[^"]*', lambda m: m.group(1) + url, head)
    head = re.sub(r'(<meta property="og:title" content=")[^"]*', lambda m: m.group(1) + html.escape(title), head)
    head = re.sub(r'(<meta property="og:description" content=")[^"]*', lambda m: m.group(1) + html.escape(desc), head)
    head = re.sub(r'(<meta property="og:url" content=")[^"]*', lambda m: m.group(1) + url, head)
    sub = f"gift-{g['slug'][:24]}-{now:%Y%m%d}"
    cards = []
    for p in picks:
        reviews = f"{int(p['reviews']):,}+ ratings" if p.get("reviews") else ""
        cards.append(f"""    <div class="product-card">
      <span class="pick-badge">{html.escape(p['type'])}</span>
      <div class="product-name">{html.escape(p['name'])}</div>
      <div class="product-rating">{p.get('rating')}&#9733; &middot; {reviews} &middot; {price_band(str(p.get('price'))).lower()}</div>
      <ul class="value-stack"><li>{html.escape(p['why'])}</li></ul>
      <a class="cta" href="https://www.amazon.com/dp/{p['asin']}?tag=goldenhomep0a-20&amp;ascsubtag={sub}" rel="sponsored nofollow noopener" target="_blank">See it on Amazon &rarr;</a>
    </div>""")
    ship = ("<p><strong>Shipping:</strong> order by mid-December to have a good chance of "
            "Christmas delivery, and check the delivery date on each listing.</p>"
            if now.month == 12 or (now.month == 11 and now.day >= 20) else "")
    retag = ('<script>(function(){var v=new URLSearchParams(location.search).get("v");'
             'var t={A:"ghpbranda-20",B:"ghpbrandb-20"}[v];if(!t)return;'
             "document.querySelectorAll('a[href*=\"amazon.com/dp/\"]').forEach(function(a){try{"
             'var u=new URL(a.href);u.searchParams.set("tag",t);u.searchParams.set("ascsubtag",'
             '"pinterest_gift_brand"+v);a.href=u.toString();}catch(e){}});})();</script>')
    return f"""{head}<body>
<div class="wrap">
  <div class="breadcrumbs"><a href="/">Home</a> &rsaquo; <a href="/blog/">Blog</a> &rsaquo; Gift Guides</div>
  <h1>{html.escape(title)}</h1>
  <div class="meta">Updated {now:%B %-d, %Y} &middot; Golden Home Project</div>
  <div class="affiliate-disclosure">As an Amazon Associate, Golden Home Project earns from qualifying purchases. Prices and availability change often; check the live listing.</div>
  <div class="intro">
    <p>{html.escape(g.get('intro') or '')}</p>
    <p>{"Every pick is on Amazon's best-seller charts this week, " if all(p.get("chart") for p in picks) else "Every pick is "}under ${g['cap']}, and rated 4.5&#9733; or higher across thousands of ratings. We have not tested these ourselves; the ratings are the evidence.</p>
    {ship}
  </div>
  <section class="post-section">
{chr(10).join(cards)}
  </section>
  <a class="back-link" href="/blog/">&larr; More gift guides and home finds</a>
</div>
{retag}
</body>
</html>
"""


def main() -> int:
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    built = 0
    for g in GUIDES:
        picks = choose(g, candidates(g["cap"]))
        if not picks:
            print(f"  [gift] {g['slug']}: not enough giftable chart products under ${g['cap']} today - keeping the old page")
            continue
        (POSTS / f"{g['slug']}.html").write_text(render(g, picks))
        state[g["slug"]] = {"title": g["title"], "search": g["search"], "cap": g["cap"],
                            "updated": datetime.now().strftime("%Y-%m-%d"),
                            "picks": [{k: p.get(k) for k in ("asin", "name", "type", "why", "price", "rating", "reviews")}
                                      for p in picks]}
        built += 1
        print(f"  [gift] {g['slug']}: {len(picks)} picks")
    STATE.write_text(json.dumps(state, indent=1))
    if built:
        def _git(*a):
            return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True)
        _git("add", str(STATE), *[str(POSTS / f"{g['slug']}.html") for g in GUIDES if (POSTS / f"{g['slug']}.html").exists()])
        _git("-c", "user.name=GHP Ops", "-c", "user.email=goldenhomeprojectllc@gmail.com",
             "commit", "-q", "-m", f"gift guides: {built} refreshed")
        _git("-c", "rebase.autoStash=true", "pull", "--rebase", "-q", "origin", "main")
        r = _git("push", "-q", "origin", "main")
        print("[gift] pushed" if r.returncode == 0 else f"[gift] push failed {r.stderr[:150]}")
    print(f"[gift] {built} guides built")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
