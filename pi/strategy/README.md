# GHP daily strategy brief (always-on Claude)

**Cadence:** 1x/day at 14:00 UTC (10:00 ET morning window) with up to 15 min jitter.
**Host:** `raspberrypi5-ts`
**Driver:** `claude -p --model claude-opus-4-7` (Max subscription, headless)
**Mode:** Read-only briefing. Does NOT take outbound actions.

## Why this exists

The Pi already runs engagement sweeps (2x/day), GHActions posts content,
and the watchdog catches infra rot. What was still missing was *judgment*:
which untapped_warm to prioritize, which content angle to push next, whether
something in the data is off. This script gives Claude one daily look at the
operational state and asks for the top 3 highest-leverage actions for the
next 24h.

Per `feedback_ghp_human_pattern.md` this is 1x/day, not 3-6x. It's an
input to the human (and to the next manual session), not an autonomous
actor.

## Inputs the script feeds to Claude

1. Last 24-36h actions from `social/engagement_log.json`
2. Latest untapped_warm count from the most recent inbox sweep
3. Last 5 posts from `social/posted_archive.json` joined to the newest
   `automation/logs/ig_insights_*.json` (likes/comments/reach where available)
4. `social/post_queue.json` head (next 3 captions)
5. Yesterday's brief (to avoid repeating itself)

## Output

`pi/strategy/YYYY-MM-DD.md` committed to `main` + ntfy ping with the path.

## Operate

```bash
# Trigger one immediate brief
ssh raspberrypi5-ts 'systemctl --user start ghp-daily-strategy.service'

# Tail last run
ssh raspberrypi5-ts 'tail -100 ~/.ghp-strategy/runs/last.log'

# Next fire time
ssh raspberrypi5-ts 'systemctl --user list-timers ghp-daily-strategy.timer'

# Disable
ssh raspberrypi5-ts 'systemctl --user disable --now ghp-daily-strategy.timer'
```

## Install (one-time on Pi)

```bash
bash ~/golden-home-project/pi/strategy/install.sh
```

## Hard constraints encoded in the prompt

- Subscription + free tools only (no paid SaaS, no new API tokens)
- Revenue first
- Never propose raising engagement-sweep cadence above 1-2x/day
- Honor engagement caps: 10 follow / 30 like / 5 comment per day
- Skip `._community` / promo / giveaway accounts
- Do not repeat yesterday's brief verbatim
