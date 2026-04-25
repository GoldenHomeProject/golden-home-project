"""Pre-ship ASIN backfill: list scripts that still need a real Amazon ASIN, and
patch them in once the ASIN has been resolved (via a logged-in Chrome browse).

Why this exists:
GHP's Amazon Associates account is pre-approval — PA-API and Creators API are
both gated until 10 qualifying sales / 30 days. Until that unlocks, the daily
content engine emits scripts with `affiliate_strategy.amazon_asin = null` and
`asin_pending = true`, and the queue entry is parked at `status =
"awaiting_asin"` so the reel-producer skips it. A human (or Claude with browser
tools) looks up the canonical ASIN on amazon.com once per script and runs:

    python automation/fill_asins.py list
    python automation/fill_asins.py set reel-2026-04-25-001.json B0XXXXXXXX

The `set` action patches both the reel JSON and the matching post_queue.json
entry — flipping its status to `awaiting_video` so the producer picks it up on
the next run.

Stdlib only — runs locally; no GitHub Actions involvement.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib import parse

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "automation" / "scripts"
QUEUE_PATH = ROOT / "social" / "post_queue.json"
AMAZON_TAG = "goldenhomep06-20"
ASIN_RE = re.compile(r"^[A-Z0-9]{10}$")


def affiliate_url(asin: str) -> str:
    return f"https://www.amazon.com/dp/{asin}?tag={AMAZON_TAG}"


def search_url(product: str) -> str:
    return f"https://www.amazon.com/s?k={parse.quote_plus(product)}"


def iter_pending() -> list[tuple[Path, dict]]:
    """Yield (path, payload) for every reel-*.json missing an ASIN."""
    pending = []
    for path in sorted(SCRIPT_DIR.glob("reel-*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            print(f"  [skip] {path.name}: parse error — {exc}", file=sys.stderr)
            continue
        affiliate = data.get("affiliate_strategy") or {}
        if not affiliate.get("amazon_asin"):
            pending.append((path, data))
    return pending


def cmd_list() -> int:
    pending = iter_pending()
    if not pending:
        print("No scripts pending ASIN backfill.")
        return 0
    print(f"{len(pending)} script(s) awaiting ASIN:\n")
    for path, data in pending:
        product = (data.get("affiliate_strategy") or {}).get("primary_product") or "?"
        print(f"  {path.name}")
        print(f"    product: {product}")
        print(f"    search:  {search_url(product)}")
        print()
    print("Run: python automation/fill_asins.py set <reel-file.json> <ASIN>")
    return 0


def cmd_set(filename: str, asin: str) -> int:
    asin = asin.strip().upper()
    if not ASIN_RE.match(asin):
        print(f"ERROR: '{asin}' is not a valid 10-char ASIN.", file=sys.stderr)
        return 2

    path = SCRIPT_DIR / filename
    if not path.exists():
        print(f"ERROR: {path} does not exist.", file=sys.stderr)
        return 2

    data = json.loads(path.read_text())
    affiliate = data.setdefault("affiliate_strategy", {})
    affiliate["amazon_asin"] = asin
    affiliate["amazon_affiliate_url"] = affiliate_url(asin)
    affiliate["asin_pending"] = False
    path.write_text(json.dumps(data, indent=2))
    print(f"  Updated {path.name} -> {asin}")

    # Patch the queue entry (if present) so the reel-producer picks it up.
    if QUEUE_PATH.exists():
        queue = json.loads(QUEUE_PATH.read_text())
        rel = str(path.relative_to(ROOT))
        patched = 0
        for entry in queue:
            if entry.get("script_path") == rel and entry.get("status") == "awaiting_asin":
                entry["status"] = "awaiting_video"
                entry["affiliate"] = affiliate
                patched += 1
        if patched:
            QUEUE_PATH.write_text(json.dumps(queue, indent=2))
            print(f"  Flipped {patched} queue entry to awaiting_video")
        else:
            print("  No queue entry needed flipping (already past awaiting_asin or absent).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="show all scripts awaiting ASIN backfill")
    s = sub.add_parser("set", help="set ASIN for one reel JSON")
    s.add_argument("filename", help="reel-YYYY-MM-DD-NNN.json (basename only)")
    s.add_argument("asin", help="10-char Amazon ASIN, e.g. B07YL7VD32")
    args = p.parse_args()
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "set":
        return cmd_set(args.filename, args.asin)
    return 1


if __name__ == "__main__":
    sys.exit(main())
