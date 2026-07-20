# GHP Daily Trending Roundup (Pi)

Publishes a **fresh, dated best-seller roundup every morning** so the blog promotes
what's actually trending — not the same recycled evergreen products (which sold $0).

## Why it runs on the Pi
Amazon bot-blocks GitHub Actions runner IPs, so a cloud cron can't read the best-seller
charts. The Pi has a residential IP Amazon doesn't challenge. Best Sellers pages are
public (no login needed) — Playwright + `xvfb-run` scrapes them headless.

## What it does (`automation/trending_daily.py`)
1. Scrapes Amazon **Best Sellers** for the day's rotating category (Kitchen, Home,
   Gadgets, Coffee, Bed & Bath, Cleaning …) + a neighbor category for depth.
2. Keeps only proven-demand winners: **$5–35, ≥4.5★, ≥5,000 reviews**.
3. **De-dupes against `social/trending_featured_history.json`** — nothing featured in
   the last 21 days — so every day is genuinely new products.
4. Generates a dated buyer-intent roundup (`blog/posts/YYYY-MM-DD-trending-…-best-sellers.html`),
   inserts it at the top of `blog/index.html`, and writes `social/trending_picks_YYYY-MM-DD.json`.
5. The systemd unit commits + pushes → GitHub Pages deploys it live.

Only `/dp/<ASIN>?tag=goldenhomep06-20` links (ASINs come straight off the live
best-seller grid = Amazon-native proof they exist). Real scraped ratings only.

## Install (once, on the Pi)
```bash
bash ~/golden-home-project/pi/trending/install.sh
```

## Operate
```bash
systemctl --user list-timers ghp-trending.timer   # when it next fires (11:10 UTC)
systemctl --user start ghp-trending.service        # run now
tail -60 ~/.ghp-trending/runs/last.log             # logs
```

## Test without publishing
```bash
# from the repo root, in the venv:
python automation/trending_daily.py --dry-run                       # scrape + print picks, write nothing
python automation/trending_daily.py --from-json social/trending_picks_2026-07-20.json --dry-run
```

## Tuning
Edit constants at the top of `automation/trending_daily.py`:
`MIN_PRICE/MAX_PRICE`, `MIN_RATING`, `MIN_REVIEWS`, `PICKS_PER_POST`,
`FRESH_WINDOW_DAYS`, and `CATEGORY_ROTATION`.
