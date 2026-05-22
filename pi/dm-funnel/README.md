# DM funnel — Pi-side audit + backup

Meta Business Suite already runs automated keyword → DM replies for every entry
in `social/dm_keyword_registry.json` with `status: live`. This Pi job is the
backup that catches comments Meta missed (rate-limited windows, edge cases) and
gives us a single durable engagement log.

## What it does

Every 15 min:
1. Pulls last 25 posts for `@golden_home_project` via `/{ig-id}/media`
2. Pulls comments on each post via `/{media-id}/comments`
3. Matches comment text against live keywords
4. Posts a public reply via `/{comment-id}/replies` ("Sent you a DM with the link!")
5. Logs to `social/engagement_log.json`
6. Tracks replied comment ids in `~/.ghp-dm-funnel/replied_comments.json` (idempotent)

## What it doesn't do

- Doesn't send DMs (Meta's automation does that, server-side, before we'd see the comment)
- Doesn't touch other accounts' posts
- Doesn't follow, like, or comment proactively
- No detection-evasion, no spoofing, no auth tricks — pure Graph API with the
  existing business token

## Install

```bash
# 1. Store the existing Meta credentials in pass (one-time):
echo '<META_ACCESS_TOKEN>' | pass insert -e ghp/meta_access_token
echo '973754055831729'     | pass insert -e ghp/ig_business_account_id

# 2. Run installer
bash ~/golden-home-project/pi/dm-funnel/install.sh

# 3. Smoke-test once
systemctl --user start ghp-dm-funnel.service
journalctl --user -u ghp-dm-funnel.service -n 50 --no-pager
```

## Disable

```bash
systemctl --user disable --now ghp-dm-funnel.timer
```
