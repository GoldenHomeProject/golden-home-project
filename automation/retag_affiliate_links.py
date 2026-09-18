#!/usr/bin/env python3
"""retag_affiliate_links.py — repoint every affiliate link at a new tracking ID.

Why this exists (2026-09-18)
----------------------------
Amazon closed Associates store ID `goldenhomep0a-20` on 2026-09-18 for not driving
three qualifying purchases within 180 days of signup. That single string is embedded in
478 links across 97 HTML pages, plus the queues, the picks files and the link builder
itself. Every one of them still resolves — visitors see a normal product page — and
every one now earns exactly nothing.

The four per-channel tracking IDs created on 2026-09-02 for attribution
(goldenhomep0a-20, goldenhomep0a-20, goldenhomep0a-20, goldenhomep0a-20) died with the
account too; Manage Your Tracking IDs now lists only the Influencer IDs.

So this is a one-command swap, dry-run by default, for whenever a valid ID exists.

    python3 automation/retag_affiliate_links.py --new-tag <id>            # report only
    python3 automation/retag_affiliate_links.py --new-tag <id> --apply    # rewrite

It deliberately does NOT choose the tag. Picking the wrong one is how this goes wrong:
using the surviving Influencer ID on the same website whose Associates ID was just
closed could read as working around the closure, and that account is the only Amazon
relationship left. A human decides the ID; this just applies it everywhere at once.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every tag that is now dead. goldenhomep0a-20 was the main store ID; the *0e-20 four
# were the per-channel attribution IDs that died with the account.
DEAD_TAGS = (
    "goldenhomep0a-20",
    "goldenhomep0a-20",
    "goldenhomep0a-20",
    "goldenhomep0a-20",
    "goldenhomep0a-20",
)

# Where links live. Skip .git and the media dirs (binary, no tags).
SEARCH_SUFFIXES = (".html", ".json", ".py", ".md", ".txt", ".xml")
SKIP_DIRS = {".git", "node_modules", "__pycache__", "social/carousels",
             "social/reels", "social/pinterest", "videos", "images"}

TAG_RE = re.compile(r"\b[a-z0-9]+-20\b")


def _skip(p: Path) -> bool:
    rel = str(p.relative_to(ROOT))
    return any(rel.startswith(d) for d in SKIP_DIRS)


def scan() -> tuple[dict, Counter]:
    """{path: {tag: count}} plus a total per tag."""
    hits: dict[Path, Counter] = {}
    totals: Counter = Counter()
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in SEARCH_SUFFIXES or _skip(p):
            continue
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        found = Counter()
        for tag in DEAD_TAGS:
            n = text.count(tag)
            if n:
                found[tag] = n
                totals[tag] += n
        if found:
            hits[p] = found
    return hits, totals


def validate(tag: str) -> str | None:
    """Amazon store IDs look like <name>-20 for the US marketplace."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,48}-20", tag):
        return (f"{tag!r} does not look like a US Amazon tracking ID "
                f"(expected lowercase, ending in -20)")
    if tag in DEAD_TAGS:
        return f"{tag!r} is one of the CLOSED tags — that would change nothing"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-tag", required=True, help="the replacement tracking ID")
    ap.add_argument("--apply", action="store_true",
                    help="actually rewrite files (default is a dry run)")
    args = ap.parse_args()

    bad = validate(args.new_tag)
    if bad:
        print(f"[retag] REFUSING: {bad}")
        return 1

    hits, totals = scan()
    if not totals:
        print("[retag] no dead tags found — nothing to do")
        return 0

    print(f"[retag] dead tags currently in the repo:")
    for tag, n in totals.most_common():
        print(f"    {tag:<22} {n:>5} occurrence(s)")
    print(f"[retag] across {len(hits)} file(s); replacing with {args.new_tag!r}")

    by_type: Counter = Counter()
    for p in hits:
        by_type[p.suffix] += 1
    print(f"[retag] file types: {dict(by_type)}")

    if not args.apply:
        print("\n[retag] DRY RUN — nothing written. Re-run with --apply to rewrite.")
        for p in sorted(hits)[:12]:
            print(f"    would edit {p.relative_to(ROOT)}  {dict(hits[p])}")
        if len(hits) > 12:
            print(f"    ... and {len(hits) - 12} more")
        return 0

    changed = 0
    for p, found in hits.items():
        text = p.read_text(errors="ignore")
        for tag in found:
            text = text.replace(tag, args.new_tag)
        # A JSON file must still parse after the swap, or we have broken a queue.
        if p.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as e:
                print(f"    SKIP {p.relative_to(ROOT)} — would not parse as JSON ({e})")
                continue
        p.write_text(text)
        changed += 1

    print(f"[retag] rewrote {changed} file(s) -> {args.new_tag}")
    leftover, left_totals = scan()
    if left_totals:
        print(f"[retag] WARNING: {sum(left_totals.values())} dead tag(s) still present")
    else:
        print("[retag] verified: no dead tags remain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
