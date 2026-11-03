#!/usr/bin/env python3
"""generate_format_pins.py — daily pins in a ROTATING format (Ian, 2026-11-03: "your content
is too generic and too repetitive and follows the same format and layout").

Each run makes --max pins, picking the formats used least recently, so no layout repeats
two days running. Formats: collage, howto (their own generators), problem_fix, versus,
mistakes, size_guide, room_cart, checklist (pin_formats.py). Products come from today's
all-category chart scan (social/chart_now.json): proven sellers only.

Honesty gates on every line Claude writes: no "$" (price bands are computed), no digits
unless they appear in the listing title, fabrication gate (no first-person experience),
no pointing at the photo. Size guides use the FACTS table only.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))

import brand_ab  # noqa: E402
import pin_formats as pf  # noqa: E402
from affiliate_links import BRAND_TAGS, build_affiliate_url  # noqa: E402
from brand import price_band  # noqa: E402
from content_quality_gate import fabrication_match  # noqa: E402
import pinterest_pipeline as pp  # noqa: E402

SOCIAL = ROOT / "social"
PINS_DIR = SOCIAL / "pinterest"
QUEUE_PATH = SOCIAL / "pinterest_queue.json"
SITE = "https://goldenhomeproject.com"
DISCLOSURE = "Amazon affiliate — small commission at no extra cost to you."

FORMATS = ["problem_fix", "versus", "mistakes", "size_guide", "room_cart", "checklist",
           "collage", "howto"]

# Standard sizes only. Mattress dimensions are the US standard; curtain lengths are the
# common stock panel lengths; towel sizes are labelled "typical" because brands vary.
FACTS = {
    "mattress": dict(kicker="sheet sizes", headline="Mattress sizes, in inches",
                     rows=[("Twin", "38 x 75"), ("Twin XL", "38 x 80"), ("Full", "54 x 75"),
                           ("Queen", "60 x 80"), ("King", "76 x 80"), ("California King", "72 x 84")],
                     note="Standard US mattress sizes. Check the sheet's pocket depth against your "
                          "mattress height too.", cats=("Bedding", "Sheets")),
    "curtains": dict(kicker="window treatments", headline="Curtain lengths, and where each one lands",
                     rows=[("To the sill", "63 in"), ("Below the sill", "84 in"),
                           ("To the floor, rod above frame", "95 in"), ("Tall ceilings", "108 in")],
                     note="Common stock panel lengths. Measure from the rod to where you want the "
                          "hem, then pick the nearest length.", cats=("Window Treatments", "Home Décor")),
    "towels": dict(kicker="bath linens", headline="Towel sizes, so you buy the right one",
                   rows=[("Washcloth", "13 x 13 in"), ("Hand towel", "16 x 30 in"),
                         ("Bath towel", "27 x 52 in"), ("Bath sheet", "35 x 60 in")],
                   note="Typical sizes; brands vary by an inch or two, so check the listing.",
                   cats=("Bath Linens", "Bath")),
}


def claude_json(prompt: str):
    try:
        from _claude_api import _load_token_file
        _load_token_file()
    except Exception:
        pass
    try:
        out = subprocess.run(["claude", "-p", "--max-turns", "1"], input=prompt,
                             capture_output=True, text=True, timeout=180).stdout
        m = re.search(r"\{.*\}", out, re.S)
        return json.loads(m.group()) if m else None
    except Exception as e:  # noqa: BLE001
        print(f"  [fmt] claude unavailable: {str(e)[:80]}")
        return None


RULES = ("Rules: plain second person, specific and useful. NO prices or '$', NO numbers or "
         "digits unless that exact number is in a product title given above, NO brand names, "
         "NO first-person experience ('I', 'my', 'we tried'), NO claims you cannot see in the "
         "titles (no 'best', 'durable', 'lasts years'). Reply with ONLY JSON.")


def _texts(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [t for v in obj.values() for t in _texts(v)]
    if isinstance(obj, list):
        return [t for v in obj for t in _texts(v)]
    return []


def honest(obj, titles: list[str]) -> str | None:
    """Return why the text fails, or None if it passes every gate."""
    allowed = set(re.findall(r"\d+", " ".join(titles)))
    for t in _texts(obj):
        if "$" in t:
            return f"price in text: {t[:50]}"
        bad = [n for n in re.findall(r"\d+", t) if n not in allowed]
        if bad:
            return f"unsourced number {bad[0]}: {t[:50]}"
        if fabrication_match(t) or pp._POINTS_AT_PHOTO.search(t):
            return f"fabricated/photo claim: {t[:50]}"
    return None


def chart_items() -> list[dict]:
    return pp.chart_now()


def used_recently(queue: list[dict]) -> dict:
    last = {}
    for e in queue:
        f = e.get("format")
        if f in FORMATS:
            last[f] = max(last.get(f, ""), str(e.get("queued_at") or e.get("id", "")[len(f) + 1:]))
    return last


def link_for(asin: str, variant: str, tag: str) -> str:
    hub = pp._hub_containing(asin)
    if hub and random.random() < 0.5:
        return f"{hub}?v={variant}"
    return build_affiliate_url(asin, "pinterest", subtag=f"{tag}_brand{variant}", tag=BRAND_TAGS[variant])


def band_of(it) -> str:
    return price_band(str(it.get("price") or ""))


def detail_of(it) -> str:
    t = brand_ab.tape_text(it.get("name", ""))
    return t or (f"{it['rating']} stars on Amazon" if it.get("rating") else "")


# ---------------------------------------------------------------- builders
def build_problem_fix(items, pin_id, v, out):
    it = random.choice(items[:40])
    name, board = it["name"], pp.board_for({"product_name": it["name"]})[0]
    got = claude_json(
        f"Product title: {name}\nWrite a Pinterest 'problem -> fix' pin. JSON: "
        '{"headline": "<4-8 words naming the everyday problem>", "problem": "<one sentence, '
        'the frustrating moment, under 18 words>", "fix": "<one sentence naming the '
        'feature from the title that addresses it, under 18 words; describe the feature, do '
        'NOT promise results (no keeps/stays/never/will)>", "photo_query": "<2-4 word stock '
        'photo search for the room or moment, no people>", "title": "<Pinterest title <=90 '
        'chars: search phrase first>"}\n' + RULES)
    if not got or honest(got, [name]):
        print(f"  [fmt] problem_fix rejected: {got and honest(got, [name])}")
        return None
    bg = PINS_DIR / f"bg-{pin_id}.jpg"
    ok = pp.fetch_pexels(got.get("photo_query") or name, bg, product=name)
    if not ok:
        ok = pp.scene_pin_image(f"{board} {name}", bg, seed=random.randint(1, 9999))
        ok = ok and pp._judge_scene(bg)[0]
    pf.problem_fix(v, pp._search_phrase(board), got["headline"], got["problem"], got["fix"],
                   bg if ok else None, detail_of(it), band_of(it), out)
    title = got["title"]
    _tw = set(re.findall(r"[a-z]+", title.lower())); _nw = set(re.findall(r"[a-z]+", name.lower()))
    if _tw and len(_tw & _nw) / len(_tw) >= 0.6:   # a raw product name is not a pin title
        title = f"{pp._search_phrase(board).title()}: {got['headline']}"
    return dict(asin=it["asin"], board=board, title=title,
                desc=f"{got['problem']} {got['fix']} {detail_of(it)}, {band_of(it).lower()} when we checked.",
                tag="pf", ai=False)


def _by_cat(items):
    by = {}
    for it in items:
        if it.get("category") != "Movers":
            by.setdefault(it["category"], []).append(it)
    return by


def build_versus(items, pin_id, v, out):
    by = _by_cat(items)
    cats = [c for c, xs in by.items() if len(xs) >= 3]
    random.shuffle(cats)
    for cat in cats[:3]:
        cand = by[cat][:10]
        lst = "\n".join(f"{i}: {c['name']}" for i, c in enumerate(cand))
        got = claude_json(
            f"Best-selling products:\n{lst}\nPick TWO that are genuine alternatives for the SAME "
            "job (e.g. two kinds of shower curtain, fleece vs sherpa throw) — same item type, "
            "different approach. If no such pair exists reply {\"skip\": true}. Otherwise JSON: "
            "{\"a\": <index>, \"b\": <index>, \"headline\": \"<'X or Y: which ...?' under 9 "
            "words, generic types>\", \"left\": {\"type\": \"<A's generic type, 2-4 words>\", "
            "\"picks\": [\"<a reason to choose A, from A's title, under 9 words, do NOT start "
            "with 'pick'>\", \"<...>\"]}, \"right\": {same for B}, \"title\": \"<Pinterest "
            "title <=90 chars>\"}\n" + RULES)
        if not got or got.get("skip"):
            continue
        try:
            a, b2 = cand[int(got["a"])], cand[int(got["b"])]
        except (KeyError, ValueError, IndexError):
            continue
        why = honest({k: got[k] for k in ("headline", "left", "right", "title")}, [a["name"], b2["name"]])
        if why:
            print(f"  [fmt] versus rejected: {why}")
            continue
        got["left"]["band"], got["right"]["band"] = band_of(a), band_of(b2)
        pf.versus(v, cat.lower(), got["headline"], got["left"], got["right"], out)
        board = pp.board_for({"product_name": a["name"]})[0]
        return dict(asin=a["asin"], board=board, title=got["title"],
                    desc=(f"{got['headline']} Option 1: {got['left']['type']}. Option 2: "
                          f"{got['right']['type']}. Both are on Amazon's best-seller chart right now."),
                    tag="vs", ai=False)
    return None


def build_mistakes(items, pin_id, v, out):
    it = random.choice(items[:40])
    board = pp.board_for({"product_name": it["name"]})[0]
    got = claude_json(
        f"Product title: {it['name']}\nWrite a Pinterest '3 mistakes people make buying <this "
        "type of item>' pin. JSON: {\"type\": \"<generic item type, plural, 1-3 words>\", "
        "\"items\": [{\"mistake\": \"<under 9 words>\", \"instead\": \"<what to do instead, "
        "under 20 words>\"}, x3], \"title\": \"<Pinterest title <=90 chars>\"}\n"
        "Mistakes must be general buying or setup advice true for any product of this type.\n" + RULES)
    if not got or len(got.get("items") or []) < 3 or honest(got, [it["name"], "3"]):
        print(f"  [fmt] mistakes rejected: {got and honest(got, [it['name']])}")
        return None
    headline = f"3 mistakes people make buying {got['type']}"
    pf.mistakes(v, pp._search_phrase(board), headline, got["items"], out)
    return dict(asin=it["asin"], board=board, title=got["title"],
                desc=" ".join(f"{x['mistake']}: {x['instead']}" for x in got["items"]),
                tag="mk", ai=False)


def build_size_guide(items, pin_id, v, out):
    key = random.choice(list(FACTS))
    fx = FACTS[key]
    pool = [i for i in items if i["category"] in fx["cats"]] or items
    it = pool[0]
    pf.size_guide(v, fx["kicker"], fx["headline"], fx["rows"], fx["note"], out)
    board = pp.board_for({"product_name": it["name"]})[0]
    return dict(asin=it["asin"], board=board, title=f"{fx['headline']}: quick reference"[:90],
                desc=f"{fx['headline']}. {fx['note']} Save this for when you shop.", tag="sg", ai=False)


def build_room_cart(items, pin_id, v, out):
    by = _by_cat(items)
    cats = [c for c, xs in by.items() if len(xs) >= 5]
    random.shuffle(cats)
    for cat in cats[:3]:
        cand = by[cat][:10]
        lst = "\n".join(f"{i}: {c['name']}" for i, c in enumerate(cand))
        got = claude_json(
            f"Best-selling products:\n{lst}\nPick 3 or 4 DIFFERENT, complementary items that "
            "refresh ONE specific room or spot together (no two of the same type). If that is not "
            "possible reply {\"skip\": true}. Otherwise JSON: {\"room\": \"<the room or spot, "
            "e.g. 'small bathroom', 'front porch'>\", \"items\": [{\"i\": <index>, \"type\": "
            "\"<generic type 2-4 words, Title Case>\", \"why\": \"<one fact from that title, "
            "under 7 words>\"}], \"title\": \"<Pinterest title <=90 chars>\"}\n" + RULES)
        if not got or got.get("skip") or not 3 <= len(got.get("items") or []) <= 4:
            continue
        try:
            picks = [cand[int(x["i"])] for x in got["items"]]
        except (KeyError, ValueError, IndexError):
            continue
        names = [p["name"] for p in picks]
        why = honest({"room": got["room"], "items": [{k: x[k] for k in ("type", "why")} for x in got["items"]],
                      "title": got["title"]}, names)
        if why or len({x["type"].lower() for x in got["items"]}) < len(picks):
            print(f"  [fmt] room_cart rejected: {why or 'duplicate types'}")
            continue
        total = sum(float(re.sub(r"[^\d.]", "", str(p.get("price") or "0")) or 0) for p in picks)
        tb = price_band(f"${total:.2f}")
        rows = [{"type": x["type"], "why": x["why"], "band": band_of(p)} for x, p in zip(got["items"], picks)]
        headline = f"Refresh a {got['room']} for {tb.lower()}"
        pf.room_cart(v, cat.lower(), headline, rows, f"All {len(picks)} for {tb.lower()}", out)
        board = pp.board_for({"product_name": picks[0]["name"]})[0]
        return dict(asin=picks[0]["asin"], board=board, title=got["title"],
                    desc=f"{headline}: " + ", ".join(r["type"] for r in rows) +
                         ". Every pick is on Amazon's best-seller chart right now.", tag="rc", ai=False)
    return None


CHECKLIST_JOBS = {
    "Bath": "a bathroom deep-clean", "Cleaning": "a weekend kitchen deep-clean",
    "Bedding": "a guest room ready for holiday visitors", "Sheets": "a fresh-sheets bed reset",
    "Home Storage": "a closet clear-out", "Home": "an entryway that stays tidy",
    "Kitchen": "a pantry and fridge reset before the holidays",
    "Window Treatments": "a bedroom that sleeps darker and warmer",
    "Bath Linens": "a towel and linen closet refresh", "Home Décor": "a cozy living room for winter",
    "Seasonal Décor": "a front porch ready for the season",
}


def build_checklist(items, pin_id, v, out):
    by = _by_cat(items)
    cat = random.choice([c for c in by if c in CHECKLIST_JOBS] or list(by))
    it = by[cat][0]
    job = CHECKLIST_JOBS.get(cat, "a room refresh")
    board = pp.board_for({"product_name": it["name"]})[0]
    got = claude_json(
        f"Write a Pinterest checklist for {job}. JSON: {{\"headline\": \"<5-9 words>\", "
        "\"items\": [\"<5-6 lines, each a CONCRETE action starting with a verb, under 11 "
        "words — things a person actually does, no moods or vague lines>\"], \"title\": "
        "\"<Pinterest title <=90 chars>\"}\n" + RULES)
    if not got or len(got.get("items") or []) < 5 or honest(got, [it["name"]]):
        print(f"  [fmt] checklist rejected: {got and honest(got, [it['name']])}")
        return None
    pf.checklist(v, job, got["headline"], got["items"], out)
    return dict(asin=it["asin"], board=board, title=got["title"],
                desc=got["headline"] + ": " + "; ".join(got["items"]) + ".", tag="cl", ai=False)


BUILDERS = dict(problem_fix=build_problem_fix, versus=build_versus, mistakes=build_mistakes,
                size_guide=build_size_guide, room_cart=build_room_cart, checklist=build_checklist)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=2)
    ap.add_argument("--only", help="force one format (test)")
    ap.add_argument("--dry", action="store_true", help="render to /tmp/fmtgen, leave the queue alone")
    args = ap.parse_args()
    queue = json.loads(QUEUE_PATH.read_text())
    last = used_recently(queue)
    order = [args.only] if args.only else sorted(FORMATS, key=lambda f: last.get(f, ""))
    items = chart_items()
    if not items:
        print("[fmt] no fresh chart scan — nothing to build")
        return 1
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    made = 0
    for fmt in order:
        if made >= args.max:
            break
        if fmt in ("collage", "howto"):
            if args.dry:
                continue
            script = "generate_collage_pins.py" if fmt == "collage" else "generate_howto_pins.py"
            r = subprocess.run([sys.executable, str(ROOT / "automation" / script), "--max", "1"],
                               capture_output=True, text=True, timeout=1500)
            print(r.stdout[-400:])
            if "built 1" in r.stdout:
                made += 1
            continue
        pin_id = f"{fmt}-{date_str}"
        if any(e.get("id") == pin_id for e in queue):
            continue
        variant = brand_ab.variant_for(pin_id)
        out = (Path("/tmp/fmtgen") if args.dry else PINS_DIR) / f"{pin_id}.png"
        try:
            meta = BUILDERS[fmt](items, pin_id, variant, out)
        except Exception as e:  # noqa: BLE001
            print(f"  [fmt] {fmt} failed: {e}")
            meta = None
        if not meta:
            continue
        made += 1
        print(f"  [fmt] {fmt} {variant} -> {out.name} | {meta['title']}")
        if args.dry:
            continue
        queue.append({
            "id": pin_id, "asin": meta["asin"], "board": meta["board"],
            "title": meta["title"][:100],
            "description": (meta["desc"].strip() + " " + DISCLOSURE)[:500],
            "link": link_for(meta["asin"], variant, meta["tag"]),
            "image_path": str(out.relative_to(ROOT)),
            "image_url": f"{SITE}/{out.relative_to(ROOT)}",
            "queued_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "posted": False, "source": "generate_format_pins", "format": fmt, "variant": variant,
        })
    if not args.dry and made:
        # collage/howto generators wrote their own entries; merge ours on top of the latest file
        disk = json.loads(QUEUE_PATH.read_text())
        ids = {e["id"] for e in disk}
        disk += [e for e in queue if e["id"] not in ids]
        QUEUE_PATH.write_text(json.dumps(disk, indent=1))

        def _git(*a):
            return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True)
        _git("add", str(QUEUE_PATH), str(PINS_DIR))
        _git("-c", "user.name=GHP Ops", "-c", "user.email=goldenhomeprojectllc@gmail.com",
             "commit", "-q", "-m", f"formats: {made} pin(s) {date_str}")
        _git("-c", "rebase.autoStash=true", "pull", "--rebase", "-q", "origin", "main")
        r = _git("push", "-q", "origin", "main")
        print("[fmt] pushed" if r.returncode == 0 else f"[fmt] push failed: {r.stderr[:150]}")
    print(f"[fmt] built {made} format pin(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
