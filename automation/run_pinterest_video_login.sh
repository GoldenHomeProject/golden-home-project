#!/usr/bin/env bash
# One-time: open the system Chromium (has H.264) on the Pi's desktop with the video-pin
# profile so the owner can sign in to Pinterest by hand. View it via Raspberry Pi Connect
# -> Screen sharing. Close the window when signed in.
#
# --password-store=basic: Playwright launches Chromium with it, so the login must be saved
# the same way (a keyring-encrypted session is unreadable to the poster). It also stops the
# "default keyring" password prompt from appearing.
set -u
PROFILE="$HOME/.config/ghp-chromium-video"
mkdir -p "$PROFILE"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export DISPLAY="${DISPLAY:-:0}"
exec /usr/bin/chromium --user-data-dir="$PROFILE" --no-first-run --password-store=basic \
    "https://www.pinterest.com/login/"
