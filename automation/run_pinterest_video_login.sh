#!/usr/bin/env bash
# One-time: open the system Chromium (has H.264) on the Pi's desktop with the video-pin
# profile so the owner can sign in to Pinterest by hand. View it via Raspberry Pi Connect
# -> Screen sharing. Close the window when signed in.
set -u
PROFILE="$HOME/.config/ghp-chromium-video"
mkdir -p "$PROFILE"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export DISPLAY="${DISPLAY:-:0}"
exec /usr/bin/chromium --user-data-dir="$PROFILE" --no-first-run \
    "https://www.pinterest.com/login/"
