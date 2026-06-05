#!/usr/bin/env python3
"""Automated, integrity-safe publisher for GHP AI-presenter Reels.

The expensive lesson (April 2026 dead-ASIN incident, 82% hallucinated ASINs -> $0):
NEVER emit an affiliate link for a product we haven't verified. So this publisher is
**vetted-product-first**: it resolves every featured product against the live registry
(social/dm_keyword_registry.json) and REFUSES to run if any product isn't a verified
entry. Content is built around real links, never the other way around.

Flow:
  1. resolve_products([keywords])  -> verified registry entries (or hard fail)
  2. build_caption(...)            -> hook + products + FTC disclosure + live DM keyword + tags
  3. host_public(mp4)              -> catbox.moe public URL (Graph needs a public video_url)
  4. post_reel(url, caption)       -> Meta Graph REELS container -> poll -> publish
  5. log to logs/posting_log.json

Default is --dry-run (resolve + caption + validate, NO publish). Pass --publish to go live.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import subprocess
from datetime import datetime, date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from affiliate_links import build_affiliate_url  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "social" / "dm_keyword_registry.json"
TOKENS = Path(__file__).parent / "logs" / "meta_tokens.json"
LOG_FILE = Path(__file__).parent / "logs" / "posting_log.json"
GRAPH_API = "https://graph.facebook.com/v21.0"

DISCLOSURE = ("As an Amazon Associate, Golden Home Project earns from qualifying purchases. "
              "#ad #affiliate")
DEFAULT_TAGS = ["#kitchenfinds", "#amazonfinds", "#homehacks", "#kitchengadgets",
                "#under20", "#homeorganization", "#cleantok", "#founditonamazon"]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def load_registry() -> dict:
    return json.loads(REGISTRY.read_text())


def resolve_products(keywords: list[str], reg: dict) -> list[dict]:
    """Map keywords -> verified registry entries. Hard-fail on any miss / non-live.

    A featured product MUST be a live `entries[]` row (so the comment->DM funnel works)
    OR a `vetted[]` row (verified ASIN, links ok even without a DM automation yet).
    Anything else is an integrity violation -> refuse.
    """
    by_kw = {e["keyword"].upper(): e for e in reg.get("entries", []) if "keyword" in e}
    by_asin = {e["asin"]: e for e in reg.get("entries", []) + reg.get("vetted", [])
               if e.get("asin")}
    out = []
    for k in keywords:
        ku = k.strip().upper()
        entry = by_kw.get(ku) or by_asin.get(k.strip().upper())
        if not entry:
            raise SystemExit(
                f"REFUSING: '{k}' is not a verified product in the registry. "
                f"Add+verify it (asin_discoverer / Pi) before featuring it. "
                f"Never emit an unverified affiliate link.")
        if entry in reg.get("entries", []) and entry.get("status") != "live":
            raise SystemExit(
                f"REFUSING: keyword '{ku}' exists but status != 'live' "
                f"(DM funnel would silently drop). Activate the Meta automation first.")
        out.append(entry)
    return out


def affiliate_url_for(entry: dict, subtag: str) -> str:
    """Prefer an explicit reroute (sjv.io etc.); else build a /dp/ASIN?tag= URL."""
    if entry.get("affiliate_url"):
        return entry["affiliate_url"]
    return build_affiliate_url(entry["asin"], "instagram", subtag=subtag)


def verify_alive(entry: dict) -> tuple[bool, str]:
    """Best-effort liveness check on the Amazon /dp/ page.

    Amazon frequently serves a bot wall to plain HTTP clients, so this is advisory:
    a clear 'Page Not Found' is a hard NO; a bot wall is 'unknown' (defer to the Pi
    Playwright discoverer for authoritative verification). Reroute (sjv.io) links are
    assumed-good if they carry a verified_destination from the registry.
    """
    if entry.get("affiliate_url"):
        return (bool(entry.get("verified_destination")),
                f"reroute -> {entry.get('verified_destination', 'unverified')}")
    asin = entry["asin"]
    url = f"https://www.amazon.com/dp/{asin}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        body = r.text.lower()
        if "page not found" in body or "looking for something" in body:
            return False, "dp page: NOT FOUND"
        if "robot check" in body or "api-services-support@amazon" in body or "captcha" in body:
            return True, "dp page: bot-wall (unknown, defer to Pi verify)"
        if "producttitle" in body or 'id="dp"' in body or "add to cart" in body:
            return True, "dp page: product renders"
        return True, f"dp page: {r.status_code} (inconclusive)"
    except Exception as e:  # noqa: BLE001
        return True, f"dp check error (advisory): {e}"


def build_caption(hook: str, products: list[dict], subtag: str,
                  primary_keyword: str, tags: list[str]) -> tuple[str, list[dict]]:
    lines = [hook, ""]
    links = []
    for i, e in enumerate(products, 1):
        url = affiliate_url_for(e, subtag)
        name = e.get("product_name", e.get("asin"))
        lines.append(f"{i}. {name}")
        links.append({"slot": i, "keyword": e.get("keyword"), "asin": e.get("asin"),
                      "product_name": name, "url": url})
    lines += [
        "",
        f"\U0001f4ac Comment \"{primary_keyword}\" and I'll reply with the links — or tap the link in my bio.",
        "",
        DISCLOSURE,
        "",
        " ".join(tags),
    ]
    return "\n".join(lines), links


def host_public(mp4: Path) -> str:
    """Upload to catbox.moe -> public URL (Graph REELS needs a public video_url)."""
    with open(mp4, "rb") as f:
        r = requests.post("https://catbox.moe/user/api.php",
                          data={"reqtype": "fileupload"},
                          files={"fileToUpload": f}, timeout=120)
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise SystemExit(f"catbox upload failed: {url!r}")
    return url


def post_reel(video_url: str, caption: str) -> dict:
    tok = json.loads(TOKENS.read_text())
    page_token, ig_id = tok["page_access_token"], tok["ig_business_account_id"]
    # 1. create REELS container
    r = requests.post(f"{GRAPH_API}/{ig_id}/media", data={
        "media_type": "REELS", "video_url": video_url,
        "caption": caption, "access_token": page_token}).json()
    cid = r.get("id")
    if not cid:
        return {"success": False, "stage": "container", "error": r}
    # 2. poll until FINISHED (video transcode)
    for _ in range(30):
        time.sleep(6)
        s = requests.get(f"{GRAPH_API}/{cid}", params={
            "fields": "status_code,status", "access_token": page_token}).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            return {"success": False, "stage": "processing", "error": s}
    else:
        return {"success": False, "stage": "processing", "error": "timeout"}
    # 3. publish
    p = requests.post(f"{GRAPH_API}/{ig_id}/media_publish", data={
        "creation_id": cid, "access_token": page_token}).json()
    if "id" in p:
        return {"success": True, "media_id": p["id"], "container_id": cid}
    return {"success": False, "stage": "publish", "error": p}


def log_result(entry: dict) -> None:
    logs = []
    if LOG_FILE.exists():
        try:
            logs = json.loads(LOG_FILE.read_text())
        except json.JSONDecodeError:
            pass
    logs.append({"timestamp": datetime.now().isoformat(), **entry})
    LOG_FILE.write_text(json.dumps(logs, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="path to the rendered vertical reel mp4")
    ap.add_argument("--keywords", required=True,
                    help="comma-separated registry keywords/ASINs for featured products, in order")
    ap.add_argument("--hook", required=True, help="first caption line")
    ap.add_argument("--primary-keyword", help="DM funnel keyword (default = first product's)")
    ap.add_argument("--tags", default=",".join(DEFAULT_TAGS))
    ap.add_argument("--publish", action="store_true", help="actually post (default: dry-run)")
    args = ap.parse_args()

    reg = load_registry()
    kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
    products = resolve_products(kws, reg)
    subtag = date.today().isoformat()
    primary = (args.primary_keyword or products[0].get("keyword") or "LINK").upper()
    caption, links = build_caption(args.hook, products, subtag, primary,
                                   [t.strip() for t in args.tags.split(",")])

    print("=== RESOLVED PRODUCTS (all verified in registry) ===")
    for L in links:
        ok, why = verify_alive(next(p for p in products if p.get("asin") == L["asin"]))
        print(f"  [{L['slot']}] {L['keyword'] or '-':8} {L['asin']:12} {'OK ' if ok else 'DEAD'} {why}")
        print(f"       {L['url']}")
    print("\n=== CAPTION ===\n" + caption)

    sidecar = Path(args.video).with_suffix(".post.json")
    sidecar.write_text(json.dumps(
        {"video": args.video, "hook": args.hook, "primary_keyword": primary,
         "products": links, "caption": caption}, indent=2))
    print(f"\n[sidecar] {sidecar}")

    if not args.publish:
        print("\n[DRY-RUN] nothing posted. Re-run with --publish to go live.")
        return 0

    print("\n[publish] hosting video...")
    video_url = host_public(Path(args.video))
    print(f"[publish] public url: {video_url}")
    res = post_reel(video_url, caption)
    log_result({"platform": "instagram_reel", "video": args.video,
                "video_url": video_url, "products": links, **res})
    if res.get("success"):
        print(f"SUCCESS: Reel published. media_id={res['media_id']}")
        return 0
    print(f"FAILED at {res.get('stage')}: {res.get('error')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
