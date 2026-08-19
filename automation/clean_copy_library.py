#!/usr/bin/env python3
"""clean_copy_library.py — rewrite the invented personal stories in copy_library.json.

Instagram was shipping captions like "Three weeks ago this cabinet was where things went
to die… I added a Simple Houseware 2-tier chrome sliding basket" and "The only thing that
changed was the pillow." Nobody at GHP owns or has used these products. 34 text fields in
the hand-crafted library carried that kind of invented anecdote.

It is dishonest to readers, it is what Google's helpful-content system penalises, and the
FTC treats an endorsement as a claim about genuine use. The same ban is already enforced
on the blog and in promote_vetted; the library predates both.

This rewrites each affected variant from the product's VERIFIED data — rating, review
count, price, stated specs — in second person or plain description, then refuses to write
anything that still trips the ban.

    python3 automation/clean_copy_library.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _claude_api import call_claude_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "social" / "copy_library.json"
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"

BANNED = re.compile(
    r"\b(i (added|bought|found|tried|own|tested|used|swapped|installed|keep)\b|"
    r"my (kitchen|cabinet|closet|pantry|bathroom|bedroom|desk|nightstand|home|"
    r"drawer|counter|apartment)\b|three weeks ago|last (month|week) i\b|"
    r"i lost track|since i (added|bought|started))", re.I)

TEXT_KEYS = ("hook", "beat1", "turn", "result")


def product_for(keyword: str) -> dict:
    reg = json.loads(REGISTRY.read_text())
    for e in reg.get("entries", []) + reg.get("vetted", []):
        if (e.get("keyword") or "").upper() == keyword.upper():
            return e
    return {}


def rewrite(variant: dict, keyword: str, product: dict) -> dict | None:
    name = product.get("product_name") or "this product"
    prompt = f"""Rewrite this Instagram caption so it contains NO invented personal experience.

PRODUCT (the only facts you may state):
  name:    {name}
  price:   {product.get('verified_price') or 'unknown'}
  rating:  {product.get('verified_stars') or 'unknown'} stars
  reviews: {product.get('verified_reviews') or 'unknown'}

CURRENT COPY (dishonest — it invents a personal story):
  hook:   {variant.get('hook','')}
  beat1:  {variant.get('beat1','')}
  turn:   {variant.get('turn','')}
  result: {variant.get('result','')}

RULES:
- Nobody here owns or has used this product. NEVER write "I added", "I bought", "I tried",
  "my kitchen/cabinet/closet", "three weeks ago", or any invented anecdote or result.
- Write in second person ("if your cabinet…", "you get…") or plain description.
- Use only the verifiable facts above plus what the product obviously does. Do not invent
  dimensions, materials, colours or claims not implied by the name.
- Keep the same 4-part shape and roughly the same length. Keep it concrete and specific —
  a real reason someone would want it, not hype.
- Do NOT name the product in the hook (it must appear later in the caption).

Return STRICT JSON: {{"hook": "...", "beat1": "...", "turn": "...", "result": "..."}}"""
    try:
        out = call_claude_json(prompt, max_tokens=1200, max_turns=3, timeout=180)
    except Exception as e:  # noqa: BLE001
        print(f"    generation failed: {e}")
        return None
    if not isinstance(out, dict) or not all(out.get(k) for k in TEXT_KEYS):
        print("    generator returned an incomplete variant")
        return None
    blob = " ".join(str(out[k]) for k in TEXT_KEYS)
    if BANNED.search(blob):
        print(f"    rewrite STILL fabricated ({BANNED.search(blob).group(0)!r}) — skipping")
        return None
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=99)
    args = ap.parse_args()

    lib = json.loads(LIB.read_text())
    variants = lib.get("variants", {})
    fixed = skipped = 0

    for keyword, vlist in variants.items():
        if not isinstance(vlist, list):
            continue
        product = product_for(keyword)
        for i, v in enumerate(vlist):
            if not isinstance(v, dict):
                continue
            blob = " ".join(str(v.get(k, "")) for k in TEXT_KEYS)
            scenes = v.get("scenes") or []
            vo = " ".join(str(s.get("voiceover", "")) for s in scenes if isinstance(s, dict))
            if not BANNED.search(blob + " " + vo):
                continue
            if fixed >= args.limit:
                break
            print(f"  {keyword}[{i}] — {BANNED.search(blob + ' ' + vo).group(0)!r}")
            new = rewrite(v, keyword, product)
            if not new:
                skipped += 1
                continue
            for k in TEXT_KEYS:
                v[k] = new[k]
            # Scene voiceovers carry the same invented story; retell them from the new copy.
            for n, s in enumerate(scenes):
                if isinstance(s, dict) and BANNED.search(str(s.get("voiceover", ""))):
                    s["voiceover"] = [new["hook"], new["beat1"], new["beat1"],
                                      new["turn"], new["result"]][min(n, 4)]
            fixed += 1
            print(f"    -> {new['hook'][:78]}")

    print(f"\n[clean] rewrote {fixed} variant(s), skipped {skipped}")
    if args.dry_run:
        print("[clean] --dry-run, library not written")
        return 0
    if fixed:
        shutil.copy2(LIB, LIB.with_suffix(".json.bak-20260819"))
        LIB.write_text(json.dumps(lib, indent=2) + "\n")
        print(f"[clean] wrote {LIB} (backup kept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
