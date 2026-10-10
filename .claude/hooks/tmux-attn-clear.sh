#!/usr/bin/env bash
cat >/dev/null  # drain stdin, unused

# Same switch as attn_off (see ~/.tmux/scripts/attn.sh): clears the window's
# green tab, whoever turned it on.
if [ -n "$TMUX" ] && [ -n "$TMUX_PANE" ]; then
  sh "$HOME/.tmux/scripts/attn.sh" off 2>/dev/null
fi

exit 0
