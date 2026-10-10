#!/bin/sh
# Move the current window: blank input sends it to the end, a number inserts
# it at that index and shifts the windows in between over by one (nothing is
# swapped). Past the last window means the end. Focus stays on it.
win="${1:-$(tmux display-message -p '#{window_id}')}"
printf ' index › '

# Read keys one at a time so Esc can cancel immediately.
esc=$(printf '\033') del=$(printf '\177') bs=$(printf '\010')
saved=$(stty -g 2>/dev/null)
trap '[ -n "$saved" ] && stty "$saved"' EXIT
stty -icanon -echo min 1 2>/dev/null
idx=""
while :; do
  c=$(dd bs=1 count=1 2>/dev/null)
  case "$c" in
    "$esc") exit 0 ;;
    "") break ;;  # Enter (the newline is stripped by $(...))
    "$del"|"$bs") [ -n "$idx" ] && { idx=${idx%?}; printf '\b \b'; } ;;
    [0-9]) idx="$idx$c"; printf '%s' "$c" ;;
  esac
done

set -- $(tmux display-message -p -t "$win" '#{session_id} #{window_index} #{window_end_flag}')
sid="$1" cur="$2" is_last="$3"
last=$(tmux display-message -p -t "$sid:{end}" '#{window_index}')
first=$(tmux display-message -p -t "$sid:{start}" '#{window_index}')

if [ -z "$idx" ] || [ "$idx" -ge "$last" ]; then
  [ "$is_last" = 1 ] || tmux move-window -a -s "$win" -t "$sid:{end}"
elif [ "$idx" -lt "$first" ]; then
  tmux move-window -b -s "$win" -t "$sid:{start}"
elif [ "$idx" -gt "$cur" ]; then
  tmux move-window -a -s "$win" -t "$sid:$idx"
elif [ "$idx" -lt "$cur" ]; then
  tmux move-window -b -s "$win" -t "$sid:$idx"
fi
tmux move-window -r -t "$sid"  # close the gap it left
tmux select-window -t "$win"
