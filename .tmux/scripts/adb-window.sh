#!/bin/sh
# Runs as the first pane of a fresh window (prefix + a). Picks an adb device,
# tags the window with @adb_serial (shown in the tab), then becomes a shell
# with ANDROID_SERIAL set. Splits in this window pick the serial up again via adb-split.sh.

# Same picker as the adbs zsh function. Cancelled or no devices: drop the window.
serial=$(sh "$HOME/.tmux/scripts/adb-pick.sh") || exit 0

tmux set-option -w -t "$TMUX_PANE" @adb_serial "$serial"
ANDROID_SERIAL=$serial exec "${SHELL:-/bin/zsh}" -l
