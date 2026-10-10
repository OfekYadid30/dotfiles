#!/bin/sh
# The green "needs attention" tab (@need_attention). Usage:
#   attn.sh on|off|tog|track [pane]
# The pane defaults to $TMUX_PANE, the pane this runs in - not whichever window
# is focused when it runs - so `sleep 5; attn_on` marks the window it was typed
# in even after you switch away.
#
# This is the only thing that touches the flag: attn_on/attn_off/attn_tog, the
# M-F binding, and the Claude Code / opencode hooks all call it. There is one
# flag per window (a window option): the tab is green or it is not.
#
# When an agent's pane is closed, its exit hook runs after tmux has already
# dropped the pane, so `off` can no longer ask tmux for the pane's window.
# Every call (and `track`, run when an agent starts) records the pane's window
# in @attn_win_<pane> so `off` still knows which window to clear.

pane=${2:-$TMUX_PANE}
if [ -z "$pane" ]; then
  echo "attn: not inside tmux" >&2
  exit 1
fi

map="@attn_win_$pane"
win=$(tmux display-message -p -t "$pane" '#{window_id}' 2>/dev/null)
if [ -n "$win" ]; then
  tmux set-option -g "$map" "$win"
else
  win=$(tmux show-options -gqv "$map")
  tmux set-option -gu "$map" 2>/dev/null
  [ -n "$win" ] || exit 0
fi

on() { tmux set-option -w -t "$win" @need_attention 1; }
off() { tmux set-option -w -u -t "$win" @need_attention 2>/dev/null; }

case "$1" in
  on) on ;;
  off) off ;;
  tog)
    if [ -n "$(tmux show-options -wqv -t "$win" @need_attention)" ]; then
      off
    else
      on
    fi
    ;;
  track) ;;
  *)
    echo "usage: attn.sh on|off|tog|track [pane]" >&2
    exit 2
    ;;
esac
