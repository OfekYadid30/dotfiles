#!/usr/bin/env bash
cat >/dev/null  # drain stdin, unused

# The agent in this pane quit: clears the window's green tab only if this pane
# is the one that turned it on (see ~/.tmux/scripts/attn.sh exit).
if [ -n "$TMUX" ] && [ -n "$TMUX_PANE" ]; then
  sh "$HOME/.tmux/scripts/attn.sh" exit 2>/dev/null
fi

exit 0
