#!/usr/bin/env python3
"""promote_vetted.py — autonomously turn a verified `vetted[]` product into a
LIVE comment->link keyword so the content flywheel can feature it.

Why this exists:
  asin_discoverer.py grows the `vetted[]` pool (real /dp/ASINs with verified
  stars/reviews/price), but nothing fed those products into the content engine.
  content_engine.py only ships keywords that are BOTH (a) status='live' in
  dm_keyword_registry.json AND (b) have at least one copy_library.json variant.
  So a vetted product was dead weight until a human hand-wrote a keyword + script.

What this does, fully unattended (cap 1 per run):
  1. Pick the most-proven vetted product (highest verified_reviews) that can get
     a unique, comment-friendly keyword.
  2. Derive that keyword (prefer a specific home-niche noun in the name/cats).
  3. Promote vetted[] -> entries[] with status='live' + keyword + promoted_at.
  4. Seed ONE gate-compliant copy_library.json variant built from the product's
     REAL verified_stars / verified_reviews / verified_price (so it passes the
     falsifiable-detail rule with TRUE numbers — never invented).
  5. Self-validate the exact script content_engine would emit through
     content_quality_gate.check_script BEFORE writing. If it would fail the gate,
     refuse to promote (we never seed content that can't ship).
  6. With --commit (Pi cron): git pull --rebase --autostash, commit, push.

Integrity rules honored:
  - Never invents an ASIN or a stat; every number comes from the vetted entry.
  - Never overwrites an existing live keyword; near-dups (COVER/COVERS) skipped.
  - FTC disclosure + comment-CTA are added by content_engine, validated here.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUTOMATION = ROOT / "automation"
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"
COPY_LIBRARY = ROOT / "social" / "copy_library.json"

sys.path.insert(0, str(AUTOMATION))
import content_engine as ce  # noqa: E402
from _claude_api import call_claude_json  # noqa: E402
import content_quality_gate as gate  # noqa: E402

# Specific home-niche nouns, most-specific first. A vetted product's keyword is
# the FIRST of these that appears in its name/categories (and is still free).
PREFERRED_NOUNS = [
    "TURNTABLE", "HANGERS", "ZAPPER", "PITCHER", "TOWELS", "LINER", "CADDY",
    "HAMPER", "ORGANIZER", "CLOSET", "PATIO", "THROW", "BLANKET", "KETTLE",
    "PITCHER", "FILTER", "BASKET", "SHELF", "DRAWER", "RACK", "HOOK", "MIRROR",
    "LAMP", "CART", "BIN", "TRAY", "MAT", "PILLOW", "COVER", "MAT",
]

# Brand / marketing / structural tokens that must never become a keyword if we
# fall back to raw name tokens.
STOPWORDS = {
    "WITH", "AND", "FOR", "THE", "YOUR", "FROM", "PULL", "NON", "SKID", "SLIP",
    "ADHESIVE", "EXPANDABLE", "SLIM", "SPACE", "SAVING", "SMALL", "LARGE",
    "OUTDOOR", "INDOOR", "PIECE", "PIECES", "SET", "SETS", "SOFT", "LINEN",
    "LUXURY", "BABY", "KIDS", "GREEN", "SAGE", "BLUE", "WHITE", "BLACK",
    "FARMHOUSE", "AMAZON", "BASICS", "AMERICAN", "PXRACK", "BAGAIL",
    "VONGRASIG", "MIULEE", "BRITA", "SOLAR", "WATER", "BOHO", "VELVET",
    "TURKISH", "STAINLESS", "STEEL", "NIGHT",
}

# Lowercase descriptors we're happy to use as an adjective in the seeded copy.
GENERIC_CATS = {
    "organization", "storage", "kitchen", "bathroom", "bedroom", "home",
    "best", "cheap", "small", "outdoor", "indoor", "cabinet",
}

PLACE_BY_CAT = {
    "kitchen": "kitchen", "under-sink": "kitchen", "bathroom": "bathroom",
    "closet": "closet", "patio": "patio", "outdoor": "patio",
    "bedroom": "bedroom", "sleep": "bedroom",
}


def _tokens(text: str) -> list[str]:
    return [t.upper() for t in re.split(r"[^A-Za-z]+", text) if len(t) >= 4]


def _near_dup(a: str, b: str) -> bool:
    """True if a and b overlap as a prefix by >=4 chars (COVER ~ COVERS)."""
    a, b = a.upper(), b.upper()
    return a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)))


def derive_keyword(entry: dict, taken: set[str]) -> str | None:
    name = entry.get("product_name", "")
    cats = " ".join(entry.get("categories", []))
    toks = set(_tokens(name) + _tokens(cats))

    def is_free(kw: str) -> bool:
        return not any(_near_dup(kw, t) for t in taken)

    # 1) Prefer a specific home-niche noun present in the product text.
    for noun in PREFERRED_NOUNS:
        if any(_near_dup(noun, t) for t in toks) and is_free(noun):
            return noun
    # 2) Fall back to the first non-stopword name token.
    for tok in _tokens(name):
        if tok not in STOPWORDS and is_free(tok):
            return tok
    return None


def _place(cats: list[str]) -> str:
    for c in cats:
        if c.lower() in PLACE_BY_CAT:
            return PLACE_BY_CAT[c.lower()]
    return "home"


MIN_PRICE, MAX_PRICE, MIN_STARS = 5.0, 35.0, 4.5


def _reviews_value(r):
    """Review counts arrive as int OR as a "1,773" string depending on which script
    wrote the entry; sorting the raw mix raised TypeError and crashed every run."""
    if isinstance(r, int):
        return r
    m = re.search(r"[\d,]+", str(r or ""))
    return int(m.group().replace(",", "")) if m else 0


def _price_value(p):
    m = re.search(r"[\d,]+\.\d{2}", str(p or ""))
    return float(m.group().replace(",", "")) if m else None


def _stars_value(s):
    m = re.search(r"\d+(?:\.\d+)?", str(s or ""))
    return float(m.group()) if m else None


def _descriptor(cats: list[str]) -> str:
    for c in cats:
        cl = c.lower()
        if cl in GENERIC_CATS or " " in cl:
            continue
        if re.fullmatch(r"[a-z][a-z-]*[a-z]", cl):
            return cl + " "
    return ""


def trending_pool(days: int = 10) -> list[dict]:
    """Today's scraped best-sellers, shaped like registry entries."""
    out, seen = [], set()
    for path in sorted((ROOT / "social").glob("trending_picks_*.json"), reverse=True)[:days]:
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for pk in (data if isinstance(data, list) else data.get("picks", [])):
            asin = (pk.get("asin") or "").strip()
            if not asin or asin in seen:
                continue
            seen.add(asin)
            out.append({
                "asin": asin,
                "product_name": pk.get("title") or pk.get("name") or "",
                "categories": [c for c in [pk.get("cat_group"), pk.get("cat_label")] if c],
                "status": "live",
                "verified_price": pk.get("price"),
                "verified_stars": str(pk.get("rating") or ""),
                "verified_reviews": pk.get("reviews"),
                "source": "trending",
            })
    return out


def recent_hooks(limit: int = 15) -> list[str]:
    """Opening lines of what we actually published, so the writer can avoid repeats."""
    archive = ROOT / "social" / "posted_archive.json"
    if not archive.exists():
        return []
    try:
        posts = json.loads(archive.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    out = []
    for post in posts[-limit:]:
        first = (post.get("caption") or "").strip().split("\n")[0].strip()
        if first:
            out.append(first)
    return out


def build_variant(entry: dict, keyword: str) -> dict | None:
    """Write a script for THIS product, from its real numbers.

    This used to be one hardcoded paragraph with the nouns swapped -- every post
    since launch opened "My <room> had been a low-grade mess for longer than I want
    to admit." Post #1 and post #200 were the same story. 14 consecutive Instagram
    posts earned 0 likes and 0 comments, and the YouTube Shorts show "No views",
    because the account reads as exactly what it was: one template on repeat.

    Now each product gets its own script, grounded in its verified title, price,
    rating and review count, and explicitly required to differ from what we already
    published. If generation fails we return None and post NOTHING -- falling back to
    the old template would just re-ship the clone we are trying to kill.
    """
    # Quality gate. Social was promoting a $251.08 product rated 4.1 stars while the
    # blog and trending engines both enforce $5-35 / >=4.5 stars. Expensive, mediocre
    # picks are the least likely to convert and they cost the account credibility.
    _p = _price_value(entry.get("verified_price"))
    _st = _stars_value(entry.get("verified_stars"))
    if _p is not None and not (MIN_PRICE <= _p <= MAX_PRICE):
        print(f"  [skip] {entry.get('asin')} price {entry.get('verified_price')} "
              f"outside ${MIN_PRICE:.0f}-${MAX_PRICE:.0f}")
        return None
    if _st is not None and _st < MIN_STARS:
        print(f"  [skip] {entry.get('asin')} rated {_st} < {MIN_STARS}")
        return None

    cats = entry.get("categories", [])
    place = _place(cats)
    reviews = entry.get("verified_reviews")
    reviews_fmt = f"{_reviews_value(reviews):,}"
    avoid = recent_hooks()
    avoid_block = ("\n".join(f"- {h}" for h in avoid)
                   if avoid else "- (nothing published yet)")

    prompt = f"""Write a short vertical-video script for ONE Amazon product.

PRODUCT (these are the only facts you may state):
  name:     {entry.get('product_name')}
  price:    {entry.get('verified_price')}
  rating:   {entry.get('verified_stars')} stars
  reviews:  {reviews_fmt}
  room:     {place}
  category: {', '.join(cats) if cats else 'home'}

HONESTY RULE - NON-NEGOTIABLE. Nobody here owns or has used this product. NEVER write
"I found", "I bought", "I tried", "my {place} was a mess", "after three weeks", or any
invented anecdote or personal result. Write about the PRODUCT and what its rating and
review count show. Second person ("your drawer", "if your cabinet...") or plain
descriptive voice is fine. Do not invent specs, colours, dimensions or claims that are
not in the name above. Never promise a time-limited price.

VARIETY RULE. These are our last published openers. Your hook must not repeat their
structure, phrasing or premise -- pick a genuinely different angle (a specific use case,
a comparison, a common mistake, who it suits, what the review count implies, a
constraint like renting or small spaces):
{avoid_block}

Return STRICT JSON only:
{{
  "hook_category": "one of: problem_solution, use_case, comparison, mistake, audience_fit, proof",
  "hook": "first line, under 90 chars, specific to THIS product, no fabricated experience",
  "beat1": "2-3 sentences expanding the angle. Concrete. No invented ownership.",
  "turn": "2 sentences on what the product does and what {reviews_fmt} reviews at {entry.get('verified_stars')} stars indicate.",
  "result": "1-2 sentences on the outcome for the reader, plus the price {entry.get('verified_price')}.",
  "scenes": [
    {{"n": 1, "duration_sec": 3, "visual_prompt": "...", "on_screen_text": "SHORT CAPS", "voiceover": "..."}},
    {{"n": 2, "duration_sec": 4, "visual_prompt": "...", "on_screen_text": "SHORT CAPS", "voiceover": "..."}},
    {{"n": 3, "duration_sec": 4, "visual_prompt": "...", "on_screen_text": "SHORT CAPS", "voiceover": "..."}},
    {{"n": 4, "duration_sec": 5, "visual_prompt": "...", "on_screen_text": "SHORT CAPS", "voiceover": "..."}},
    {{"n": 5, "duration_sec": 4, "visual_prompt": "...", "on_screen_text": "SHORT CAPS", "voiceover": "..."}}
  ]
}}"""

    try:
        v = call_claude_json(prompt, max_tokens=1600, max_turns=1, timeout=180)
    except Exception as e:  # noqa: BLE001
        print(f"  [skip] {entry.get('asin')}: script generation failed ({e})")
        return None
    if not isinstance(v, dict):
        print(f"  [skip] {entry.get('asin')}: generator returned {type(v).__name__}")
        return None

    required = ("hook", "beat1", "turn", "result", "scenes")
    missing = [k for k in required if not v.get(k)]
    if missing:
        print(f"  [skip] {entry.get('asin')}: script missing {missing}")
        return None
    v.setdefault("hook_category", "problem_solution")

    # Enforce the honesty rule in code, not just in the prompt.
    banned = re.compile(r"\b(i (found|bought|tried|own|tested|used)|my (kitchen|bathroom|"
                        r"closet|pantry|home|patio|drawer)|after \d+ (weeks|months))\b", re.I)
    blob = " ".join(str(v.get(k, "")) for k in required[:4])
    if banned.search(blob):
        print(f"  [skip] {entry.get('asin')}: script claimed fabricated experience")
        return None

    # And enforce variety: a hook that repeats a published opener is not new content.
    hook_l = v["hook"].strip().lower()
    if any(hook_l[:40] == h.strip().lower()[:40] for h in avoid):
        print(f"  [skip] {entry.get('asin')}: hook duplicates a published opener")
        return None
    return v


def validate_variant(variant: dict, keyword: str, entry: dict) -> tuple[bool, list[str]]:
    """Run the EXACT script content_engine would emit through the quality gate."""
    library = ce.load_copy_library()
    hashtags = ce._pick_hashtags(library, entry)
    caption = ce._build_caption(variant, keyword, hashtags, registry_entry=entry)
    script = {
        "caption": caption,
        "hashtags": hashtags,
        "affiliate_strategy": {
            "primary_product": entry["product_name"],
            "amazon_asin": entry["asin"],
        },
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(script, f)
        tmp = Path(f.name)
    try:
        return gate.check_script(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def run_git(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def commit_and_push(keyword: str, asin: str) -> None:
    rc, out = run_git(["pull", "--rebase", "--autostash"])
    if rc != 0:
        print(f"[promote] git pull failed (continuing to commit locally): {out}")
    run_git(["add", str(REGISTRY), str(COPY_LIBRARY)])
    rc, out = run_git(["commit", "-m",
                       f"Auto-promote vetted product {asin} -> live keyword {keyword}"])
    if rc != 0:
        print(f"[promote] nothing to commit / commit failed: {out}")
        return
    rc, out = run_git(["push"])
    print(f"[promote] push: {'ok' if rc == 0 else 'FAILED ' + out}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true",
                    help="git pull/commit/push after promoting (Pi cron uses this)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be promoted, write nothing")
    args = ap.parse_args()

    reg = json.loads(REGISTRY.read_text())
    entries = reg.get("entries", [])
    # Pool = the vetted registry PLUS today's trending scrape. The registry is a fixed
    # list that goes stale — it was still offering 4th-of-July decorations in August —
    # while trending_picks_<date>.json is rewritten every morning off Amazon's live
    # best-seller charts. Fresh products daily is the whole point; a static pool means
    # recycled posts no matter how good the writer is.
    # Keep the PERSISTED list separate from the in-memory candidate pool. Writing the
    # augmented pool back to disk re-appended every trending product on every run —
    # 16 daily runs left 619 rows for 107 unique ASINs, and the pin generator saw an
    # exhausted catalogue because every unique product was already queued.
    persisted_vetted = reg.get("vetted", [])
    vetted = persisted_vetted + trending_pool()
    if not vetted:
        print("[promote] vetted[] is empty — nothing to promote.")
        return 0

    taken = {e["keyword"].upper() for e in entries if e.get("keyword")}

    # Most-proven first: a high review count is the best signal the product is real
    # and converts. Promote the single best candidate we can name uniquely.
    for entry in sorted(vetted, key=lambda e: _reviews_value(e.get("verified_reviews")),
                        reverse=True):
        if not entry.get("asin") or not entry.get("verified_reviews"):
            continue
        keyword = derive_keyword(entry, taken)
        if not keyword:
            print(f"[promote] {entry['asin']}: no unique keyword available, skipping.")
            continue
        variant = build_variant(entry, keyword)
        if variant is None:
            continue          # rejected by the price/rating gate; message already printed
        ok, reasons = validate_variant(variant, keyword, entry)
        if not ok:
            print(f"[promote] {entry['asin']} kw={keyword}: seeded variant FAILS gate "
                  f"{reasons} — skipping (won't seed unshippable content).")
            continue

        print(f"[promote] selected {entry['asin']} -> keyword {keyword} "
              f"({entry.get('verified_stars')}* / {entry['verified_reviews']} reviews)")
        if args.dry_run:
            print("[promote] --dry-run: writing nothing.")
            return 0

        # 1) vetted -> entries (live)
        promoted = dict(entry)
        promoted["keyword"] = keyword
        promoted["status"] = "live"
        promoted["promoted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        reg["entries"] = entries + [promoted]
        reg["vetted"] = [v for v in persisted_vetted if v.get("asin") != entry["asin"]]
        REGISTRY.write_text(json.dumps(reg, indent=2) + "\n")

        # 2) seed the copy_library variant
        lib = json.loads(COPY_LIBRARY.read_text())
        lib.setdefault("variants", {}).setdefault(keyword, []).append(variant)
        COPY_LIBRARY.write_text(json.dumps(lib, indent=2) + "\n")

        print(f"[promote] LIVE: {keyword} -> {entry['asin']} "
              f"(entries now {len(reg['entries'])}, vetted now {len(reg['vetted'])})")

        if args.commit:
            commit_and_push(keyword, entry["asin"])
        return 0

    print("[promote] no promotable vetted product this run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
