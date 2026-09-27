#!/usr/bin/env python3
"""rewrite_stat_hooks.py — replace copy_library variants that open on a number.

Until 2026-09-26 the script writer was told it could "make the review count the
argument", and 44 of 62 live variants did: "106,545 reviews on one twin mattress
protector. That's not a fluke." Every reel that opened that way earned 0 likes.
content_engine now skips number-led variants, so each one needs a replacement or
its product drops out of rotation.

For each live keyword, every number-led variant is regenerated with the current
build_variant() prompt (scene-first hooks, proof once and rounded, CTA). The old
variant is moved to `retired_variants` in the same file, not deleted.

Run on the Pi (needs the Claude CLI token):
    python3 automation/rewrite_stat_hooks.py [--max N] [--commit]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "automation"))
import content_engine as ce  # noqa: E402
import promote_vetted as pv  # noqa: E402

LIB = ROOT / "social" / "copy_library.json"
REG = ROOT / "social" / "dm_keyword_registry.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()

    live = {e["keyword"]: e for e in json.loads(REG.read_text())["entries"]
            if e.get("status") == "live"}
    done = failed = 0
    for kw in list(json.loads(LIB.read_text()).get("variants", {})):
        if kw not in live or done >= a.max:
            continue
        lib = json.loads(LIB.read_text())            # re-read: each save is independent
        variants = lib["variants"][kw]
        for i, v in enumerate(list(variants)):
            if done >= a.max:
                break
            if not ce.stat_led(v.get("hook", ""), (v.get("scenes") or [{}])[0]):
                continue
            new = pv.build_variant(live[kw], kw)
            ok, reasons = (pv.validate_variant(new, kw, live[kw]) if new else (False, ["no script"]))
            if not ok:
                failed += 1
                print(f"[rewrite] {kw}: FAILED ({'; '.join(reasons)[:160]}) — old variant kept")
                continue
            new["rewritten_from"] = v.get("hook", "")[:120]
            new["rewritten_at"] = datetime.now(timezone.utc).isoformat()
            retired = dict(v, retired_at=new["rewritten_at"], retired_reason="number-led hook")
            lib.setdefault("retired_variants", {}).setdefault(kw, []).append(retired)
            variants[variants.index(v)] = new
            LIB.write_text(json.dumps(lib, indent=2, ensure_ascii=False) + "\n")
            done += 1
            print(f"[rewrite] {kw}: {v.get('hook','')[:60]!r}\n          -> {new['hook']!r}")
    print(f"[rewrite] rewrote {done}, failed {failed}")

    if a.commit and done:
        g = ["git", "-c", "user.name=GHP Ops", "-c", "user.email=goldenhomeprojectllc@gmail.com"]
        subprocess.run(["git", "add", str(LIB)], cwd=ROOT)
        subprocess.run(g + ["commit", "-qm", f"copy: rewrite {done} number-led hooks as scene-first"], cwd=ROOT)
        subprocess.run(["git", "-c", "rebase.autoStash=true", "pull", "--rebase", "-q", "origin", "main"], cwd=ROOT)
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
