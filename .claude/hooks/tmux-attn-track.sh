#!/usr/bin/env bash
cat >/dev/null  # drain stdin, unused

# Records which window this pane is in, so closing the pane can still clear
# that window's green tab (see ~/.tmux/scripts/attn.sh track). Doesn't change
# the tab.
if [ -n "$TMUX" ] && [ -n "$TMUX_PANE" ]; then
  sh "$HOME/.tmux/scripts/attn.sh" track 2>/dev/null
fi

exit 0
