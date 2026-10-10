#!/usr/bin/env bash
INPUT=$(cat)

# Stop events carry background_tasks (empty = main + all subagents/background
# tasks truly finished); Notification events don't have this field, so the
# `// 0` fallback makes the check a no-op there.
PENDING=$(echo "$INPUT" | jq '.background_tasks | length // 0' 2>/dev/null)
if [ "${PENDING:-0}" -gt 0 ]; then
  exit 0
fi

# Same switch as attn_on (see ~/.tmux/scripts/attn.sh).
if [ -n "$TMUX" ] && [ -n "$TMUX_PANE" ]; then
  sh "$HOME/.tmux/scripts/attn.sh" on 2>/dev/null
fi

exit 0
