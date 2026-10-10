#!/bin/sh
# Copies stdin to the clipboard of the terminal you are sitting at, on macOS
# and Linux alike. One place that knows the clipboard tools, used by tmux
# (copy-command, Alt+Shift+P, Alt+Shift+B), by zsh (Alt+Shift+C, the c
# function) and by nvim's "+ register inside tmux.
#
# Inside tmux the text goes to every attached client via OSC 52. Plain
# `load-buffer -w` is not enough: it reaches only the most recently active
# client, which over SSH can be a terminal open on the remote's own desktop.
#
# The desktop tools (pbcopy, wl-copy, xclip, xsel) run only when the client
# is local. Over SSH they would fill the remote desktop's clipboard - a
# desktop session there leaks DISPLAY/WAYLAND_DISPLAY into the shell - so the
# old ssh -X + xclip route is given up in favour of OSC 52.
#
# CLIP_FROM_TMUX=1 is set by tmux's copy-command: copy-mode has already made
# the buffer and sent OSC 52 to the clients viewing the pane.

# Nothing to copy means leave the clipboard alone. tmux pipes an empty string
# when there is no selection - e.g. Enter right after y - and passing that on
# would wipe what y just copied. (The x keeps trailing newlines, which $(...)
# would otherwise strip.)
text=$(cat; printf x)
text=${text%x}
[ -n "$text" ] || exit 0

remote=
if [ -n "$TMUX" ]; then
  # The pane's own environment goes stale (panes outlive attaches); the
  # session's SSH_CONNECTION is refreshed by update-environment on attach.
  case $(tmux show-environment SSH_CONNECTION 2>/dev/null) in
    SSH_CONNECTION=*) remote=1 ;;
  esac
  if [ -z "$CLIP_FROM_TMUX" ]; then
    printf '%s' "$text" | tmux load-buffer -
    for c in $(tmux list-clients -F '#{client_tty}'); do
      printf '%s' "$text" | tmux load-buffer -w -t "$c" -
    done
  fi
elif [ -n "$SSH_CONNECTION$SSH_TTY" ]; then
  remote=1
  printf '\033]52;c;%s\a' "$(printf '%s' "$text" | base64 | tr -d '\n')" > /dev/tty
fi

[ -z "$remote" ] || exit 0

if command -v pbcopy >/dev/null 2>&1; then
  printf '%s' "$text" | pbcopy
elif [ -n "$WAYLAND_DISPLAY" ] && command -v wl-copy >/dev/null 2>&1; then
  printf '%s' "$text" | wl-copy
elif [ -n "$DISPLAY" ] && command -v xclip >/dev/null 2>&1; then
  # xclip stays behind to serve the selection; detach its output so whoever
  # called this (tmux's copy-pipe) is not left waiting on it.
  printf '%s' "$text" | xclip -selection clipboard >/dev/null 2>&1
elif [ -n "$DISPLAY" ] && command -v xsel >/dev/null 2>&1; then
  printf '%s' "$text" | xsel --clipboard --input
elif [ -z "$TMUX" ]; then
  echo "clip-copy: no clipboard tool found (pbcopy, wl-copy, xclip or xsel)" >&2
  exit 1
fi
