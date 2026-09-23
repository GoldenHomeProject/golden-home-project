#!/usr/bin/env python3
"""Repoint already-published Pinterest pins from DEAD Amazon Associates tags to
the live one, by editing each pin's destination link in the Pi's persistent
Chromium profile (same profile + launch shape as post_pinterest.py).

WHY: the Associates account behind `goldenhomep06-20` (and its per-channel
`ghppinterest0e-20` tracking ID) was CLOSED 2026-09-18. The reapproved account's
tag is `goldenhomep0a-20`. Retagging the repo changed every FUTURE link, but a
published pin keeps the URL it was created with — ~214 live pins, the channel
that produced every sale GHP has made, kept sending clicks to a dead tag.

⚠️ `goldenhomep0a-20` is NOT a typo. A March 2026 doc
(docs/solutions/logic-errors/env-amazon-associate-tag-typo.md) says it was; that
is now exactly inverted. Do not "fix" NEW_TAG back to 06.

What it does per run:
  1. Inventory (read-only): pages through the profile's Created grid via the
     same UserActivityPinsResource request the grid itself makes. The live link
     on Pinterest is the source of truth, not social/pinterest_post_log.json
     (the log misses manual/probe pins and never recorded the 0e-20 pins).
  2. For up to --max pins still carrying a dead tag: open the pin, More actions
     -> Edit Pin, read #WebsiteField, swap ONLY the tag value, Save.
  3. Re-inventories and marks each saved pin verified only if Pinterest now
     returns the new link.

Safety:
  * Out-of-repo ledger ~/.ghp-engagement/pin_repoint_ledger.json (git resets
    can't erase it). A pin is never edited again once verified, and is given up
    after MAX_ATTEMPTS.
  * The edit is idempotent anyway: the field is read first and only a dead tag
    is ever replaced; everything else in the URL is byte-identical.
  * Any login wall / challenge / captcha / rate-limit / block text -> write
    ~/.ghp-engagement/pin_repoint_STOP, ntfy the owner, exit 2. Every later run
    refuses to start until a human deletes that file. Never solves CAPTCHAs.
  * Skips the run (exit 0) if another job's Chromium holds the profile.
  * Human pace: randomized per-run count, 40-140 s between edits, occasional
    longer pauses, hard wall-clock cap.
  * When nothing is left, disables its own systemd timer.

Usage (on Pi):
  xvfb-run -a ~/.ghp-engagement/venv/bin/python automation/repoint_pin_links.py --dry
  xvfb-run -a ... repoint_pin_links.py --no-dry --max 1 --verify-ui   # first real edit
  xvfb-run -a ... repoint_pin_links.py --no-dry                       # scheduled batches
  python3 automation/repoint_pin_links.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

NEW_TAG = "goldenhomep0a-20"          # LIVE (reapproved 2026-09-18)
DEAD_TAGS = ("goldenhomep06-20",      # closed 2026-09-18
             "ghppinterest0e-20")     # per-channel ID, died with the account
assert NEW_TAG not in DEAD_TAGS

USERNAME = "goldenhomeprojectllc"
CREATED_URL = f"https://www.pinterest.com/{USERNAME}/_created/"
PROFILE_DIR = Path.home() / ".config" / "ghp-chromium"
CHROMIUM_BIN = "/usr/bin/chromium"
STATE_DIR = Path.home() / ".ghp-engagement"
LEDGER_PATH = STATE_DIR / "pin_repoint_ledger.json"
INVENTORY_PATH = STATE_DIR / "pin_repoint_inventory.json"
STOP_PATH = STATE_DIR / "pin_repoint_STOP"
NTFY_ENV = Path.home() / "claude-skill" / "config" / "env"   # read-only
TIMER_UNIT = "ghp-pin-repoint.timer"

DEFAULT_MAX = 22
MAX_ATTEMPTS = 3
RUN_WALL_CLOCK_S = 75 * 60

_TAG_RE = re.compile(r"([?&]tag=)(" + "|".join(map(re.escape, DEAD_TAGS)) + r")(?=&|#|$)")

# Specific phrases only: pin pages carry arbitrary description/ad text, so a
# generic word like "spam" or "temporarily" would false-positive.
CHALLENGE_PHRASES = (
    "verify you're a human", "verify you are a human", "are you a robot",
    "complete the captcha", "security check", "unusual activity",
    "you've been blocked", "your account has been blocked",
    "we've temporarily limited", "too many requests", "try again later",
    "suspicious activity", "confirm it's you", "log in to see more",
)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def swap_tag(url: str | None) -> str | None:
    """Return url with a dead tag value replaced by NEW_TAG, else None.
    Only the tag value changes; ASIN, ascsubtag, order of params are kept."""
    if not url:
        return None
    new, n = _TAG_RE.subn(lambda m: m.group(1) + NEW_TAG, url)
    if n != 1:
        return None
    return new


def has_dead_tag(url: str | None) -> bool:
    return bool(url) and bool(_TAG_RE.search(url))


def selftest() -> int:
    a = "https://www.amazon.com/dp/B01KBEOL5E?tag=goldenhomep06-20&ascsubtag=pinterest"
    assert swap_tag(a) == "https://www.amazon.com/dp/B01KBEOL5E?tag=goldenhomep0a-20&ascsubtag=pinterest"
    b = "https://www.amazon.com/dp/B08N9Q24M9?tag=ghppinterest0e-20&ascsubtag=pinterest"
    assert swap_tag(b) == "https://www.amazon.com/dp/B08N9Q24M9?tag=goldenhomep0a-20&ascsubtag=pinterest"
    assert swap_tag("https://www.amazon.com/dp/X?tag=goldenhomep0a-20&ascsubtag=pinterest") is None
    assert swap_tag("https://www.amazon.com/dp/X?ascsubtag=pinterest&tag=goldenhomep06-20") \
        == "https://www.amazon.com/dp/X?ascsubtag=pinterest&tag=goldenhomep0a-20"
    assert swap_tag("https://www.amazon.com/dp/X?tag=goldenhomep06-201") is None  # no prefix match
    assert swap_tag("https://goldenhomeproject.com/x.html") is None
    assert swap_tag(None) is None
    assert has_dead_tag(a) and not has_dead_tag(swap_tag(a))
    print("selftest ok")
    return 0


# ---------------------------------------------------------------- state ----

def load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def save_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, p)


def load_ledger() -> dict:
    led = load_json(LEDGER_PATH, {})
    led.setdefault("pins", {})
    led.setdefault("runs", [])
    return led


def ntfy(title: str, body: str, priority: str = "default") -> None:
    topic = ""
    try:
        for line in NTFY_ENV.read_text().splitlines():
            if line.startswith("NTFY_TOPIC="):
                topic = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    except Exception:
        pass
    if not topic:
        return
    subprocess.run(["curl", "-sf", "-m", "10", "-H", f"Title: {title}",
                    "-H", f"Priority: {priority}", "-H", "Tags: pushpin",
                    "-d", body, f"https://ntfy.sh/{topic}"], capture_output=True)


def hard_stop(reason: str, detail: str = "") -> int:
    STOP_PATH.write_text(json.dumps({"ts": now(), "reason": reason, "detail": detail}, indent=2))
    msg = (f"Pin repoint STOPPED: {reason}. {detail} "
           f"No further runs until {STOP_PATH} is deleted.")
    print(f"[repoint] !! {msg}")
    ntfy("GHP pin repoint stopped", msg, "high")
    return 2


def profile_busy() -> bool:
    out = subprocess.run(["pgrep", "-f", "config/ghp-chromium"], capture_output=True, text=True).stdout
    for pid in out.split():
        try:
            comm = Path(f"/proc/{pid}/comm").read_text().strip()
        except OSError:
            continue
        if comm.startswith(("chrome", "chromium")):
            return True
    return False


def jitter(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


# ------------------------------------------------------------- browser ----

class Challenge(Exception):
    pass


def check_page(page, where: str) -> None:
    url = page.url
    if any(s in url for s in ("/login", "/signup", "captcha", "challenge")):
        raise Challenge(f"{where}: redirected to {url}")
    try:
        # Pinterest loads an INVISIBLE reCAPTCHA Enterprise anchor on normal pages
        # (256x60, visibility:hidden) — presence alone is not a challenge. Only a
        # captcha frame the user could actually see counts.
        shown = page.evaluate("""() => [...document.querySelectorAll('iframe')].filter(f => {
            if (!/captcha|arkoselabs|hcaptcha/i.test(f.src || '')) return false;
            const r = f.getBoundingClientRect(), s = getComputedStyle(f);
            return r.width > 20 && r.height > 20 && s.visibility !== 'hidden'
                   && s.display !== 'none' && parseFloat(s.opacity || '1') > 0.1;
        }).map(f => f.src.slice(0, 80))""")
        if shown:
            raise Challenge(f"{where}: visible captcha frame {shown[0]}")
        body = page.locator("body").inner_text(timeout=3000).lower()
    except Challenge:
        raise
    except Exception:
        return
    hit = next((p for p in CHALLENGE_PHRASES if p in body), None)
    if hit:
        raise Challenge(f"{where}: page says {hit!r}")


def fetch_inventory(page, rate_flags: list) -> list[dict]:
    """Read-only: every pin in the Created grid with its live link."""
    first: dict = {}

    def on_req(r):
        if "UserActivityPinsResource/get" in r.url and not first:
            first["url"], first["headers"] = r.url, r.headers
    page.on("request", on_req)
    page.goto(CREATED_URL, wait_until="domcontentloaded", timeout=30000)
    jitter(5, 7)
    check_page(page, "created grid")
    for _ in range(4):
        if first:
            break
        page.mouse.wheel(0, random.randint(1500, 2200))
        jitter(1.5, 2.5)
    page.remove_listener("request", on_req)
    if not first:
        raise RuntimeError("Created grid never issued UserActivityPinsResource (layout changed?)")

    q = urllib.parse.parse_qs(urllib.parse.urlparse(first["url"]).query)
    data = json.loads(q["data"][0])
    src = q.get("source_url", [f"/{USERNAME}/_created/"])[0]
    hdr = {k: v for k, v in first["headers"].items() if k.lower() != "cookie"}
    pins: dict[str, dict] = {}
    bm = None
    for _ in range(40):
        data["options"]["bookmarks"] = [bm] if bm else []
        url = ("https://www.pinterest.com/resource/UserActivityPinsResource/get/?"
               + urllib.parse.urlencode({"source_url": src,
                                         "data": json.dumps(data, separators=(",", ":")),
                                         "_": str(int(time.time() * 1000))}))
        r = page.request.get(url, headers=hdr)
        if r.status == 429:
            rate_flags.append("inventory 429")
            raise Challenge("inventory: HTTP 429 rate limited")
        if r.status != 200:
            raise RuntimeError(f"inventory HTTP {r.status}: {r.text()[:160]}")
        rr = r.json().get("resource_response", {})
        for x in rr.get("data") or []:
            pins[x["id"]] = {"id": x["id"], "link": x.get("link"),
                             "board": (x.get("board") or {}).get("name"),
                             "created_at": x.get("created_at")}
        bm = rr.get("bookmark")
        if not bm or bm == "-end-" or not rr.get("data"):
            break
        jitter(2, 4)
    return list(pins.values())


def open_edit_modal(page, pin_id: str):
    page.goto(f"https://www.pinterest.com/pin/{pin_id}/", wait_until="domcontentloaded", timeout=30000)
    jitter(4, 7)
    check_page(page, f"pin {pin_id}")
    if "/pin/" not in page.url:
        raise RuntimeError(f"pin page redirected to {page.url} (deleted?)")
    field = page.locator("#WebsiteField")
    candidates = page.locator("button[aria-label='More actions']:not([data-test-id])")
    for i in range(min(candidates.count(), 3)):
        candidates.nth(i).click()
        jitter(1, 2)
        item = page.locator("[data-test-id='pin-action-dropdown-edit-pin']")
        if item.count():
            item.first.click()
            field.wait_for(state="visible", timeout=10000)
            jitter(1, 2)
            check_page(page, f"edit modal {pin_id}")
            return field
        page.keyboard.press("Escape")
        jitter(0.5, 1)
    raise RuntimeError("no 'Edit Pin' action found (not our pin, or layout changed)")


def dialog_button(page, label: str):
    # Scope to the edit dialog and match EXACT text: the page behind it has its
    # own "Save" (save-to-board) button, and the dialog also has "Delete".
    return page.locator("[role='dialog'] button").filter(
        has_text=re.compile(rf"^\s*{label}\s*$")).first


def cancel_modal(page) -> None:
    try:
        dialog_button(page, "Cancel").click(timeout=4000)
    except Exception:
        page.keyboard.press("Escape")
    jitter(1, 2)


def edit_pin(page, pin: dict, dry: bool) -> tuple[str, str | None, str | None]:
    """Returns (status, old, new)."""
    field = open_edit_modal(page, pin["id"])
    current = field.input_value()
    if not has_dead_tag(current):
        cancel_modal(page)
        return ("already_ok", current, None)
    new = swap_tag(current)
    if not new:
        cancel_modal(page)
        return ("unexpected_link", current, None)
    if pin.get("link") and pin["link"] != current:
        # Field disagrees with the inventory: don't guess, leave it for a human.
        cancel_modal(page)
        return ("inventory_mismatch", current, new)
    if dry:
        print(f"  [DRY] {pin['id']}: {current}\n        -> {new}")
        cancel_modal(page)
        return ("dry_ok", current, new)

    field.click()
    jitter(0.4, 0.9)
    field.press("Control+a")
    field.fill(new)
    jitter(0.8, 1.6)
    if field.input_value() != new:
        cancel_modal(page)
        return ("fill_failed", current, new)

    update_status: list[int] = []

    def on_resp(r):
        if "/resource/" in r.url and "/update/" in r.url:
            update_status.append(r.status)
    page.on("response", on_resp)
    dialog_button(page, "Save").click(timeout=6000)
    try:
        field.wait_for(state="detached", timeout=12000)
        closed = True
    except Exception:
        closed = False
    jitter(1.5, 3)
    page.remove_listener("response", on_resp)
    if 429 in update_status:
        raise Challenge(f"pin {pin['id']}: save returned HTTP 429")
    check_page(page, f"after save {pin['id']}")
    if not closed:
        cancel_modal(page)
        return ("save_unconfirmed", current, new)
    if update_status and all(s >= 400 for s in update_status):
        return (f"save_http_{update_status[-1]}", current, new)
    return ("saved", current, new)


def verify_ui(page, pin_id: str, expected: str) -> str:
    field = open_edit_modal(page, pin_id)
    val = field.input_value()
    cancel_modal(page)
    return val if val == expected else f"MISMATCH: {val}"


def disable_timer() -> None:
    subprocess.run(["systemctl", "--user", "disable", "--now", TIMER_UNIT], capture_output=True)


# ---------------------------------------------------------------- main ----

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=DEFAULT_MAX, help="edit cap for this run")
    ap.add_argument("--dry", action="store_true", default=True)
    ap.add_argument("--no-dry", dest="dry", action="store_false")
    ap.add_argument("--dry-open", type=int, default=2,
                    help="in --dry, also open this many edit modals (then Cancel)")
    ap.add_argument("--verify-ui", action="store_true",
                    help="after each save, reopen the pin's edit modal and read the field back")
    ap.add_argument("--exact", action="store_true",
                    help="edit exactly --max (default: random 70-100%% of --max)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    selftest()

    if STOP_PATH.exists():
        print(f"[repoint] STOP file present, refusing to run: {STOP_PATH.read_text().strip()}")
        return 2
    if profile_busy():
        print("[repoint] another job's Chromium holds the profile — skipping this run")
        return 0
    for f in PROFILE_DIR.glob("Singleton*"):   # stale locks from a killed run
        try:
            f.unlink()
        except OSError:
            pass

    from playwright.sync_api import sync_playwright

    led = load_ledger()
    run = {"ts": now(), "dry": args.dry, "results": {}}
    started = time.time()
    rate_flags: list[str] = []
    saved_this_run: dict[str, str] = {}

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR), executable_path=CHROMIUM_BIN,
            headless=False, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = ctx.new_page()
        try:
            inv = fetch_inventory(page, rate_flags)
            save_json(INVENTORY_PATH, {"ts": now(), "pins": inv})
            dead = [x for x in inv if has_dead_tag(x["link"])]
            # Anything the ledger says we saved that Pinterest now shows fixed.
            for x in inv:
                e = led["pins"].get(x["id"])
                if e and e.get("status") == "saved" and x["link"] == e.get("new"):
                    e["status"], e["verified_at"] = "verified", now()
            targets = [x for x in dead
                       if led["pins"].get(x["id"], {}).get("status") != "gave_up"
                       and led["pins"].get(x["id"], {}).get("attempts", 0) < MAX_ATTEMPTS]
            gave_up = [x for x in dead if x not in targets]
            print(f"[repoint] inventory: {len(inv)} pins, {len(dead)} with a dead tag "
                  f"({len(targets)} eligible, {len(gave_up)} given up)")
            run["inventory_total"], run["dead_before"] = len(inv), len(dead)

            if not dead:
                print("[repoint] nothing left to repoint — disabling timer")
                save_json(LEDGER_PATH, led)
                if not args.dry:
                    disable_timer()
                    ntfy("GHP pin repoint complete",
                         f"All pins now use {NEW_TAG}. Timer disabled.")
                ctx.close()
                return 0

            random.shuffle(targets)
            if args.dry:
                for x in targets:
                    print(f"  would repoint {x['id']} [{x['board']}] {x['link']}")
                batch = targets[:max(0, args.dry_open)]
            else:
                n = args.max if args.exact else random.randint(max(1, int(args.max * 0.7)), args.max)
                batch = targets[:n]
                print(f"[repoint] editing {len(batch)} this run")

            fails_in_row = 0
            for i, pin in enumerate(batch):
                if time.time() - started > RUN_WALL_CLOCK_S:
                    print("[repoint] wall-clock cap reached; stopping for this run")
                    break
                e = led["pins"].setdefault(pin["id"], {"attempts": 0})
                if not args.dry:
                    e["attempts"] = e.get("attempts", 0) + 1
                    e["last_try"] = now()
                    save_json(LEDGER_PATH, led)   # count the attempt before acting
                try:
                    status, old, new = edit_pin(page, pin, args.dry)
                except Challenge:
                    raise
                except Exception as ex:
                    status, old, new = f"error:{str(ex)[:120]}", pin.get("link"), None
                print(f"[repoint] {pin['id']}: {status}")
                run["results"][pin["id"]] = status
                if args.dry:
                    continue
                e.update({"old": old, "status": status})
                if status == "saved":
                    e.update({"new": new, "saved_at": now()})
                    saved_this_run[pin["id"]] = new
                    if args.verify_ui:
                        jitter(3, 6)
                        v = verify_ui(page, pin["id"], new)
                        e["verify_ui"] = v
                        print(f"[repoint]   verify (reopened edit modal): {v}")
                        if v.startswith("MISMATCH"):
                            save_json(LEDGER_PATH, led)
                            ctx.close()
                            return hard_stop("verification mismatch", f"pin {pin['id']} {v}")
                    fails_in_row = 0
                elif status == "already_ok":
                    e["status"] = "verified"
                    fails_in_row = 0
                else:
                    fails_in_row += 1
                    if e["attempts"] >= MAX_ATTEMPTS:
                        e["status"] = "gave_up"
                save_json(LEDGER_PATH, led)
                if fails_in_row >= 2:
                    print("[repoint] 2 failures in a row — stopping this run (not a hard stop)")
                    break
                if i < len(batch) - 1:
                    pause = random.uniform(40, 140)
                    if random.random() < 0.15:
                        pause += random.uniform(120, 300)
                    time.sleep(pause)

            # Independent check: Pinterest's own data must now show the new link.
            if saved_this_run:
                jitter(20, 40)
                inv2 = {x["id"]: x for x in fetch_inventory(page, rate_flags)}
                save_json(INVENTORY_PATH, {"ts": now(), "pins": list(inv2.values())})
                ok = 0
                for pid, new in saved_this_run.items():
                    live = (inv2.get(pid) or {}).get("link")
                    ent = led["pins"][pid]
                    if live == new:
                        ent["status"], ent["verified_at"] = "verified", now()
                        ok += 1
                    else:
                        ent["status"] = "saved_unverified"
                        ent["live_after_save"] = live
                        print(f"[repoint] !! {pid} saved but live link is {live}")
                run["verified"] = ok
                run["dead_after"] = sum(1 for x in inv2.values() if has_dead_tag(x["link"]))
                print(f"[repoint] verified via inventory: {ok}/{len(saved_this_run)}; "
                      f"dead-tag pins remaining: {run['dead_after']}")
        except Challenge as ch:
            run["stopped"] = str(ch)
            led["runs"].append(run)
            save_json(LEDGER_PATH, led)
            try:
                page.screenshot(path=str(STATE_DIR / "pin_repoint_stop.png"))
            except Exception:
                pass
            ctx.close()
            return hard_stop("Pinterest challenge/limit", str(ch))
        ctx.close()

    led["runs"].append(run)
    save_json(LEDGER_PATH, led)
    return 0


if __name__ == "__main__":
    sys.exit(main())
