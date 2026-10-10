#!/bin/sh
# Status-line helper. Usage:
#   status-git.sh branch <path>     the branch (or detach@<sha>) at <path>
#   status-git.sh pad left|right <session_id> <session_name> <path> <client_width>
#   status-git.sh arrow left|right <session_id> <session_name> <path> <client_width>
#
# pad prints spaces that keep the window list (status-justify centre) at the
# true centre of the screen whatever the branch name's length: the shorter of
# status-left/right is padded up to the longer one - but only as far as there
# is room. When the windows do not fit centred, the padding shrinks, so they
# use all the space between the session name and the branch instead of leaving
# a gap on the short side.
#
# arrow prints the green style for the < (left) or > (right) marker tmux draws
# when the window list is cut, if a window cut off on that side has
# @need_attention. tmux does not say which windows it cut, so this redoes its
# math (format_draw_put_list in tmux's format-draw.c): the list gets the width
# between status-left and status-right, the current window is kept centred,
# and each marker takes a cell. Extra arguments are ignored: the format passes
# them only so tmux re-runs this as soon as they change.

branch() {
  { git -C "$1" symbolic-ref --quiet --short HEAD 2>/dev/null ||
    git -C "$1" rev-parse --short HEAD 2>/dev/null | sed 's/^/detach@/'; } |
    tr -d '\n' | cut -c1-40
}

# Display width: drop #[style] runs, count UTF-8 characters (not bytes).
width() {
  printf '%s' "$1" | sed 's/#\[[^]]*\]//g' | LC_ALL=C tr -d '\200-\277' | wc -c | tr -d ' '
}

# The pad width for $side; needs sid name path cols b.
padding() {
  diff=$(( $(width "$b") - $(width "$name") ))
  [ "$1" = right ] && diff=$(( -diff ))
  [ "$diff" -gt 0 ] || { echo 0; return; }

  # Each side is its text plus two spaces and two powerline glyphs.
  list=$(tmux display-message -p -t "$sid" \
    '#{W:#{T:window-status-format},#{T:window-status-current-format}}')
  free=$(( cols - $(width "$name") - $(width "$b") - 8 - $(width "$list") ))
  [ "$free" -lt "$diff" ] && diff=$free
  [ "$diff" -gt 0 ] && echo "$diff" || echo 0
}

case "$1" in
  branch) branch "$2" ;;
  pad)
    side=$2 sid=$3 name=$4 path=$5 cols=$6
    b=$(branch "$path")
    n=$(padding "$side")
    [ "$n" -gt 0 ] && printf "%${n}s" ""
    ;;
  arrow)
    side=$2 sid=$3 name=$4 path=$5 cols=$6
    b=$(branch "$path")
    avail=$(( cols - $(width "$name") - $(width "$b") - 8 \
      - $(padding left) - $(padding right) ))
    sep=$(width "$(tmux show-options -gv window-status-separator)")

    # One line per window: active flag, attention flag, the name's width, |,
    # then the tab text. Offsets are in list cells; fs/fe bound the current
    # window.
    total=0 fs=0 fe=0 info=""
    tabs=$(tmux list-windows -t "$sid" -F '#{window_active}#{?@need_attention,1,0}#{w:window_name}|#{?window_active,#{T:window-status-current-format},#{T:window-status-format}}')
    while IFS= read -r line; do
      [ "$total" -gt 0 ] && total=$(( total + sep ))
      w=$(width "${line#*|}")
      case "$line" in 1*) fs=$total fe=$(( total + w )) ;; esac
      # Only the name (after the tab's leading space) turns green, so that
      # is the part that has to be in view.
      nw=${line#??} nw=${nw%%|*}
      case "$line" in ?1*) info="$info $(( total + 1 )):$(( total + 1 + nw ))" ;; esac
      total=$(( total + w ))
    done <<TABS
$tabs
TABS

    [ "$avail" -gt 0 ] && [ "$total" -gt "$avail" ] || exit 0

    centre=$(( fs + (fe - fs) / 2 ))
    start=0
    [ "$centre" -ge $(( avail / 2 )) ] && start=$(( centre - avail / 2 ))
    [ $(( start + avail )) -gt "$total" ] && start=$(( total - avail ))
    vis=$avail
    if [ "$start" -ne 0 ] && [ "$vis" -gt 1 ]; then
      start=$(( start + 1 )) vis=$(( vis - 1 ))
    fi
    [ $(( start + vis )) -lt "$total" ] && [ "$vis" -gt 1 ] && vis=$(( vis - 1 ))
    end=$(( start + vis ))

    # A window counts as hidden only if none of its name is in view: one
    # partly shown at the edge is still green on the bar itself.
    for r in $info; do
      s=${r%:*} e=${r#*:}
      if { [ "$side" = left ] && [ "$e" -le "$start" ]; } ||
         { [ "$side" = right ] && [ "$s" -ge "$end" ]; }; then
        printf '#[fg=#2ea043]'
        break
      fi
    done
    ;;
esac
exit 0
