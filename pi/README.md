# GHP Pi-resident automation

The Raspberry Pi 5 (`raspberrypi5.local`, Tailscale `100.125.57.45`) runs the
always-on background brain. This directory holds every GHP-specific job that
lives on the Pi. **Additive to GitHub Actions, not a replacement.**

## What runs on the Pi

| Job | Cadence | Path | Status |
|---|---|---|---|
| `ghp-watchdog.service` | continuous (60s loop) | `pi/watchdog/` | active |
| `ghp-self-review.timer` | weekly Mon 11:00 local | `pi/learnings/` | active |
| `ghp-daily-loop.timer` | daily 06:30 local | `pi/daily-loop/` | **disabled** — see `pi/daily-loop/README.md` for the Mac→Pi cutover |

## What stays on GitHub Actions (do not migrate)

Everything in `.github/workflows/`. Per the rule **Actions wins** for anything
that already runs reliably there:
`trend-scout.yml`, `content-generator.yml`, `reel-producer.yml`,
`daily-poster.yml`, `instagram-poster.yml`, `blog-writer.yml`,
`engagement-monitor.yml`, `ig-insights.yml`, `repurpose.yml`, `ceo-review.yml`.

## What stays on the Mac

| Job | Why it stays |
|---|---|
| `com.goldenhomeproject.daily-loop` (launchd) | Already ported (`pi/daily-loop/`) but Mac job is **still authoritative** until user explicitly flips the cutover. Until then, this is the only thing keeping the morning loop alive when the Pi is being rebooted or in maintenance. |

## Install order on a fresh Pi

```bash
# 1. Prereqs
sudo apt update && sudo apt install -y gh jq curl git
gh auth login          # device-flow; needs repo + workflow scopes
git clone https://github.com/GoldenHomeProject/golden-home-project ~/golden-home-project
cd ~/golden-home-project
git config user.email goldenhomeprojectllc@gmail.com
git config user.name "GHP Pi Bot"

# 2. Linger so user units survive logout
sudo loginctl enable-linger "$USER"

# 3. Install services
bash pi/watchdog/install.sh
bash pi/learnings/install.sh
# (daily-loop install only after Mac launchd is disabled — see that subdir)
```

## Conventions

- **All Pi services are systemd user units** (`systemctl --user`), installed to
  `~/.config/systemd/user/`. No `sudo` after first `enable-linger`.
- **Logs go to journald**, durable artifacts go to `~/ghp-watchdog/logs/` or to
  the repo (`pi/learnings/proposals/`, `pi/learnings/journal.jsonl`).
- **No secrets on disk in plaintext.** The single shared secret is the
  `NTFY_TOPIC` value, which already exists in `~/claude-skill/config/env` and
  is read-only from these scripts. Never overwritten.
- **Subscription + free tools only.** All LLM calls go through `claude -p` (the
  CLI on the Max subscription), never the Anthropic API.

## How to rip everything back to the Mac

```bash
# On the Pi:
systemctl --user disable --now ghp-watchdog.service
systemctl --user disable --now ghp-self-review.timer
systemctl --user disable --now ghp-daily-loop.timer 2>/dev/null
```

Nothing in this directory mutates the Mac. The Mac launchd job in
`~/Library/LaunchAgents/com.goldenhomeproject.daily-loop.plist` was untouched
by this work.
