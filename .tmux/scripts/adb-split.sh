#!/bin/sh
# split-window that carries the window's @adb_serial (if any) into the new
# pane as ANDROID_SERIAL. Usage: adb-split.sh <pane_id> <path> [-h|-v]

pane=$1 path=$2 dir=${3:--v}
serial=$(tmux show-options -wqv -t "$pane" @adb_serial)

if [ -n "$serial" ]; then
  tmux split-window "$dir" -t "$pane" -c "$path" -e "ANDROID_SERIAL=$serial"
else
  tmux split-window "$dir" -t "$pane" -c "$path"
fi
