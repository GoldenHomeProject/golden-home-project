# Pi ASIN Discoverer — Operations

**Status:** Ported from GH Actions 2026-05-27. systemd user timer fires daily at 06:00 UTC (+ up to 30min random delay).
**Host:** `raspberrypi5-ts`
**User:** `ianmcwherter` (linger enabled)

## Why the Pi and not GitHub Actions

The 2026-05-27 dispatch test (`gh run view 26521552977`) confirmed Amazon serves a Robot Check / interstitial to GH Actions runner IPs — the `[data-component-type="s-search-result"]` selector never renders. The Pi has a residential IP Amazon has never challenged, and already runs the engagement bot through Playwright + xvfb-run.

The GH Actions workflow (`.github/workflows/asin-discoverer.yml`) is kept as a `workflow_dispatch`-only backup. Its `workflow_run` auto-trigger is removed.

## Files

| Where | What |
|---|---|
| `~/golden-home-project/automation/asin_discoverer.py` | The script (shared with GH Actions) |
| `~/.ghp-asin-discoverer/venv/` | Python venv with Playwright |
| `~/.ghp-asin-discoverer/runs/last.log` | Tail of most recent run |
| `~/.config/systemd/user/ghp-asin-discoverer.{service,timer}` | Live unit files (sources in this dir) |
| `~/golden-home-project/social/dm_keyword_registry.json` | `vetted[]` pool — appended here |

## Install (one-time)

```bash
ssh raspberrypi5-ts 'bash ~/golden-home-project/pi/asin-discoverer/install.sh'
```

## Operate

```bash
# trigger one immediate run
ssh raspberrypi5-ts 'systemctl --user start ghp-asin-discoverer.service'

# tail last run
ssh raspberrypi5-ts 'tail -80 ~/.ghp-asin-discoverer/runs/last.log'

# see next scheduled run
ssh raspberrypi5-ts 'systemctl --user list-timers ghp-asin-discoverer.timer'

# disable temporarily
ssh raspberrypi5-ts 'systemctl --user stop ghp-asin-discoverer.timer'
ssh raspberrypi5-ts 'systemctl --user disable ghp-asin-discoverer.timer'
```

## What the service does

1. `git pull --rebase` to get fresh `social/trend_feed.json` from main
2. Run `automation/asin_discoverer.py` under `xvfb-run` + the local venv
3. If `social/dm_keyword_registry.json` changed, commit + push (retry 3× to absorb engagement bot races)

## Pre-reqs that must stay true

- xvfb installed (already true — engagement bot uses it)
- Linger enabled for `ianmcwherter` (already true)
- Repo cloned at `~/golden-home-project` with credentials cached for push

## Recovery if Amazon starts blocking the Pi too

If `last.log` shows `search failed: ... no qualifying organic result` for multiple runs in a row, Amazon has fingerprinted the Pi. Options in order of preference:

1. Add `playwright-stealth` to the venv, restart from `install.sh`
2. Rotate the Playwright User-Agent (edit `automation/asin_discoverer.py` constant)
3. Run through a residential rotating proxy (cost: $)
4. Move discovery to manual SiteStripe lookups again
