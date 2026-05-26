# Pi Engagement Bot — Operations

**Status:** LIVE since 2026-05-25. systemd user timer fires 3× daily (13:30 / 18:30 / 23:30 UTC).
**Host:** `raspberrypi5-ts` (Tailscale `100.125.57.45`)
**User:** `ianmcwherter` (linger enabled)
**Mode:** `--inbox-only` (Step 0 only — sweep + log, no outbound)

## Files

| Where | What |
|---|---|
| `~/golden-home-project/automation/engagement.py` | The script |
| `~/.config/ghp-chromium/` | Logged-in Chromium profile (Wayland-via-xvfb in cron, real labwc when launched manually) |
| `~/.ghp-engagement/venv/` | Python venv with Playwright |
| `~/.ghp-engagement/runs/last.log` | Tail of most recent run |
| `~/.config/systemd/user/ghp-engagement.{service,timer}` | Live unit files (copies versioned in this repo dir) |
| `~/golden-home-project/social/engagement_log.json` | All actions logged here, append-only |

## Operate

```bash
# trigger one immediate sweep
ssh raspberrypi5-ts 'systemctl --user start ghp-engagement.service'

# tail last run
ssh raspberrypi5-ts 'tail -50 ~/.ghp-engagement/runs/last.log'

# see when next sweep fires
ssh raspberrypi5-ts 'systemctl --user list-timers ghp-engagement.timer'

# disable temporarily
ssh raspberrypi5-ts 'systemctl --user stop ghp-engagement.timer'
ssh raspberrypi5-ts 'systemctl --user disable ghp-engagement.timer'
```

## What --inbox-only does

1. Open IG `/direct/requests/` → parse Thread list innerText → list pending request senders
2. Open IG `/direct/inbox/` → parse Thread list innerText → list accepted-but-recent threads
3. Open IG `/notifications/` → parse body innerText → emit `[{handle, action}]` pairs
4. Cross-reference handles against `engagement_log.json` history → emit `untapped_warm` = people who engaged with us but we haven't logged any reciprocation
5. Log everything to `engagement_log.json` with shape `{action: "inbox_sweep", ...}`

## What it does NOT do (yet)

- **No outbound actions.** No likes, follows, comments, DMs. Step 0 sweep only.
- **No DM replies.** Reading inbox to detect, not responding.
- **No accepts.** Pending requests are listed, not auto-accepted.

`--full` mode is a placeholder that errors out. v2 will:
- Auto-follow back people in `untapped_warm` (cap 5/day randomized)
- Auto-comment back when someone replied to our comment (cap 3/day)
- Hard rule: stop on any "action blocked" or 429

## Recovery if IG forces re-auth

If a sweep logs `action: "abort", reason: "login_wall"`:

1. SSH to the Pi, kill any stale Chromium: `pkill -f ghp-chromium`
2. Open Pi Connect screen sharing → connect.raspberrypi.com → RaspberryPi5 → screen
3. On the Pi desktop, run:
   ```bash
   chromium --user-data-dir=$HOME/.config/ghp-chromium --password-store=basic \
            --no-first-run https://www.instagram.com/accounts/login/
   ```
4. Log in as @golden_home_project, save login info, close.
5. Re-trigger: `systemctl --user start ghp-engagement.service`

## Pre-reqs that must stay true

- Pi is on Wayland (labwc) — switched 2026-05-24
- xvfb installed
- Tailscale auto-starts at boot
- SSH auto-starts at boot
- `loginctl show-user ianmcwherter` reports `Linger=yes` (so user services run without an SSH session)
