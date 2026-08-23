#!/usr/bin/env python3
"""dedupe_registry.py — collapse duplicate ASIN rows in dm_keyword_registry.json.

promote_vetted was writing its in-memory candidate pool (registry + daily trending picks)
back to disk, so every trending product was re-appended on every run: 619 rows for 107
unique ASINs, 512 of them waste. The pin generator dedupes by ASIN, so it saw a catalogue
where every product was already queued and produced 0 new pins for days — Pinterest output
fell from 8/day to 1/day.

Keeps ONE row per ASIN, preferring (a) status live, (b) the most recent verified_at,
(c) the row carrying a DM keyword, so nothing meaningful is lost. Backs up first.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "social" / "dm_keyword_registry.json"


def score(row: dict) -> tuple:
    return (
        1 if row.get("status") == "live" else 0,
        1 if row.get("keyword") else 0,
        str(row.get("verified_at") or ""),
        len(json.dumps(row)),          # richest record as a final tie-break
    )


def dedupe(rows: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    order: list[str] = []
    for row in rows:
        asin = row.get("asin")
        if not asin:
            continue
        if asin not in best:
            best[asin] = row
            order.append(asin)
        elif score(row) > score(best[asin]):
            best[asin] = row
    return [best[a] for a in order]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    reg = json.loads(REG.read_text())
    out = {}
    for key in ("entries", "vetted"):
        rows = reg.get(key, [])
        deduped = dedupe(rows)
        out[key] = deduped
        print(f"  {key}: {len(rows)} rows -> {len(deduped)} unique")

    # An ASIN promoted into entries should not linger in vetted.
    entry_asins = {e.get("asin") for e in out["entries"]}
    before = len(out["vetted"])
    out["vetted"] = [v for v in out["vetted"] if v.get("asin") not in entry_asins]
    if before != len(out["vetted"]):
        print(f"  vetted: dropped {before - len(out['vetted'])} already promoted to entries")

    if args.dry_run:
        print("[dedupe] --dry-run, nothing written")
        return 0

    shutil.copy2(REG, REG.with_suffix(".json.bak-dedupe-20260823"))
    reg["entries"], reg["vetted"] = out["entries"], out["vetted"]
    REG.write_text(json.dumps(reg, indent=2) + "\n")
    print(f"[dedupe] wrote {REG} (backup kept)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
