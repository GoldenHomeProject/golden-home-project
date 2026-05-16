# GHP daily CEO loop — Pi migration (READY, NOT ENABLED)

Pi port of the Mac launchd job `com.goldenhomeproject.daily-loop`. Files are in
the repo so the cutover is a one-command flip, but the timer is **not** enabled
because turning it on without first disabling the Mac launchd would cause
**double execution + commit races at 06:30 local**.

## Cutover steps (manual, requires user confirmation)

On the Mac:
```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.goldenhomeproject.daily-loop.plist
launchctl unload ~/Library/LaunchAgents/com.goldenhomeproject.daily-loop.plist 2>/dev/null
mv ~/Library/LaunchAgents/com.goldenhomeproject.daily-loop.plist \
   ~/Library/LaunchAgents/com.goldenhomeproject.daily-loop.plist.disabled
```

On the Pi (after `bash pi/learnings/install.sh` prereqs done — needs a
working ~/golden-home-project clone with push auth):
```bash
install -m 644 pi/daily-loop/ghp-daily-loop.service ~/.config/systemd/user/
install -m 644 pi/daily-loop/ghp-daily-loop.timer   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ghp-daily-loop.timer
systemctl --user list-timers ghp-daily-loop.timer
```

Verify the next run:
```bash
journalctl --user -u ghp-daily-loop.service -f
```

## Rollback to Mac

On the Pi:
```bash
systemctl --user disable --now ghp-daily-loop.timer
```

On the Mac:
```bash
mv ~/Library/LaunchAgents/com.goldenhomeproject.daily-loop.plist.disabled \
   ~/Library/LaunchAgents/com.goldenhomeproject.daily-loop.plist
launchctl load ~/Library/LaunchAgents/com.goldenhomeproject.daily-loop.plist
```

## Why this is the only Mac launchd job worth migrating

Per the audit (task #74):
- `com.goldenhomeproject.daily-loop` — schedule-driven, no macOS-specific
  frameworks (just `bash` + `claude`), depends on laptop being awake at 06:30.
  **Migrate.**
- All other GHP schedules already live in `.github/workflows/*.yml` running on
  GitHub Actions. Per the rule "Actions wins", they stay there.
