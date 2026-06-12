#!/usr/bin/env python3
"""Pi-resident GHP presenter-reel orchestrator with full rotation.

Each run advances ONE entry through reel_rotation.json (counter persisted in
.reel_rotation_state) and renders via the HF GPU (LTX-2 API) + auto-publishes to IG.
Rotates content/products/hook every run; outfit/lighting rotates too, but an entry
whose variant_verified=false falls back to the proven tee_daylight variant so an
unverified outfit can never auto-post a bad render.

Fails SAFE: any render error (e.g. HF ZeroGPU quota exhausted) aborts BEFORE publish
and does NOT advance the counter, so the same entry is retried next run.
"""
import datetime
import json
import random
import subprocess
import sys
from pathlib import Path

PRES = Path.home() / ".ghp-presenter"
REPO = Path.home() / "golden-home-project"
PY = str(PRES / "venv" / "bin" / "python")
CFG = PRES / "reel_rotation.json"
STATE = PRES / ".reel_rotation_state"
FAILSTREAK = PRES / ".reel_fail_streak"
STREAK_ALERT = 3  # consecutive no-post nights that means genuinely broken, not a 1-off quota skip
LOG = PRES / "run.log"
ENV_FILE = Path.home() / "claude-skill" / "config" / "env"
FALLBACK_VARIANT = "out/variants/tee_daylight.png"


def log(msg: str) -> None:
    line = f"{datetime.datetime.now(datetime.UTC).isoformat()} {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line)


def notify(title: str, body: str, priority: str = "default") -> None:
    """Best-effort ntfy push so a nightly post outcome surfaces without GitHub email."""
    try:
        topic = ""
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("NTFY_TOPIC="):
                topic = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
        if not topic:
            return
        subprocess.run(
            ["curl", "-sf", "-m", "10", "-H", f"Title: {title}",
             "-H", f"Priority: {priority}", "-H", "Tags: ghp,presenter,warning",
             "-d", body, f"https://ntfy.sh/{topic}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def bump_streak() -> int:
    try:
        n = int(FAILSTREAK.read_text().strip())
    except (ValueError, FileNotFoundError, OSError):
        n = 0
    n += 1
    FAILSTREAK.write_text(str(n))
    return n


def reset_streak() -> None:
    FAILSTREAK.write_text("0")


def ffdur(path: Path, stream: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries",
         "stream=duration", "-of", "default=nk=1:nw=1", str(path)],
        capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def main() -> int:
    cfg = json.loads(CFG.read_text())
    rot = cfg["rotation"]
    idx = 0
    if STATE.exists():
        try:
            idx = int(STATE.read_text().strip())
        except ValueError:
            idx = 0
    entry = rot[idx % len(rot)]

    verified = bool(entry.get("variant_verified"))
    variant = entry["variant"] if verified else FALLBACK_VARIANT
    seed = random.randint(1000, 99999)
    log(f"===== reel idx={idx} name={entry['name']} kw={entry['keywords']} "
        f"variant={variant} verified={verified} seed={seed} =====")

    # Resolve this entry's DM keywords -> registry products -> real listing
    # photos, so composite() can overlay product cards (image+name+price).
    try:
        reg = json.loads((REPO / "social" / "dm_keyword_registry.json").read_text())
        by_kw = {}
        for e in list(reg.get("entries", [])) + list(reg.get("vetted", [])):
            kw = (e.get("keyword") or "").strip().upper()
            if kw:
                by_kw[kw] = e
        prods = []
        for kw in [k.strip().upper() for k in entry["keywords"].split(",") if k.strip()]:
            e = by_kw.get(kw)
            if not e:
                continue
            img = REPO / "social" / "product_images" / f"{e['asin']}.jpg"
            if not img.exists():
                continue
            name = (e.get("product_name") or "").split("(")[0].split(",")[0].strip()
            prods.append({"image": str(img), "name": name[:34],
                          "price": e.get("verified_price", "")})
        (PRES / "out" / "products_for_video.json").write_text(json.dumps(prods, indent=1))
        log(f"[products] {len(prods)} card(s) for overlay: "
            f"{[p['name'] for p in prods]}")
    except Exception as exc:  # cards are an enhancement, never block the reel
        log(f"[products] resolve failed (non-fatal): {exc}")
        try:
            (PRES / "out" / "products_for_video.json").unlink()
        except FileNotFoundError:
            pass

    r = subprocess.run(
        [PY, "make_reel.py", "--script", entry["script"], "--variant", variant,
         "--polish", "raw", "--seed", str(seed), "--duration", "12.0",
         "--name", "reel_auto"],
        cwd=str(PRES))
    if r.returncode != 0:
        streak = bump_streak()
        log(f"[abort] render failed rc={r.returncode} (likely HF quota) — no post, "
            f"counter NOT advanced (retry same entry next run); fail_streak={streak}")
        # A single quota skip is expected (esp. Sunday verify week) — stay silent.
        # Only alert when the pipeline is genuinely stuck for several nights.
        if streak >= STREAK_ALERT:
            notify("GHP presenter STUCK",
                   f"{streak} consecutive nights with no post (last={entry['name']}, "
                   f"render rc={r.returncode}). Likely NOT just quota — check HF token / Space.",
                   "high")
        return 1

    final = PRES / "out" / "reel_auto_final.mp4"
    v, a = ffdur(final, "v:0"), ffdur(final, "a:0")
    log(f"[check] video={v}s audio={a}s")
    if a > v + 0.25:
        bump_streak()
        log("[abort] audio longer than video — truncation risk, no post")
        notify("GHP reel BROKEN",
               f"{entry['name']}: audio {a}s > video {v}s — truncation bug, no post. "
               f"Script likely too long for the 12s cap.", "high")
        return 1

    p = subprocess.run(
        [PY, str(REPO / "automation" / "reel_publisher.py"),
         "--video", str(final), "--keywords", entry["keywords"],
         "--hook", entry["hook"], "--publish"],
        cwd=str(REPO))
    if p.returncode != 0:
        bump_streak()
        log(f"[fail] publish rc={p.returncode} — counter NOT advanced (retry next run)")
        notify("GHP reel BROKEN",
               f"render OK but publish rc={p.returncode} for {entry['name']} — "
               f"likely Meta token/API issue.", "high")
        return 1

    STATE.write_text(str((idx + 1) % len(rot)))
    reset_streak()
    log(f"[ok] published {entry['name']}; next idx={(idx + 1) % len(rot)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
