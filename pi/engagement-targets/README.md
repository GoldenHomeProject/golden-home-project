# engagement-targets — daily ranked list for human-paced action

Pi job that runs once a day at 06:15 ET and produces a 10-post ranked engagement
target file. **No automated engagement.** The human (you) opens the list on
your phone and taps through in ~2 min.

## Why this exists

Outbound engagement on Instagram (liking other people's posts, following niche
accounts, leaving genuine comments) has no sanctioned automation path —
Instagram's Graph API deliberately doesn't expose it. The only ToS-clean
options are:

1. Do it manually
2. Have a human do it with a curated, pre-ranked target list

This script makes #2 a 2-minute morning routine instead of a 30-minute discovery
loop.

## What it uses (all sanctioned)

- `GET /ig_hashtag_search?user_id={ig-id}&q={hashtag}` — resolves hashtag → id
- `GET /{hashtag-id}/recent_media` — last 25 posts for that hashtag

Both are official Meta Graph API endpoints documented for Instagram business
accounts.

## Scoring

Higher = better target:
- Smaller accounts (likes < 5000) are favored — bigger accounts won't notice us
- Newer posts (last 24h) score higher
- Some baseline engagement (likes >= 10) — zero-engagement posts often dead

## Output

- `social/engagement_targets_YYYY-MM-DD.json` — dated archive
- `social/engagement_targets_latest.json` — always-current copy for phone link

## Install

```bash
bash ~/golden-home-project/pi/engagement-targets/install.sh
# Run once now:
systemctl --user start ghp-engagement-targets.service
cat ~/golden-home-project/social/engagement_targets_latest.json | jq .
```

## Disable

```bash
systemctl --user disable --now ghp-engagement-targets.timer
```
