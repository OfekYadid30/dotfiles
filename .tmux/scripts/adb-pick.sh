#!/bin/sh
# Shared adb device picker, used by the adbs zsh function and by prefix + a in
# tmux (adb-window.sh). Shows one row per device in fzf and prints the chosen
# serial on stdout. Exits non-zero if cancelled or no devices are attached.
# With --list (the adbl zsh function) it just prints the device table; with
# --current (adbc) it prints only the row of the device ANDROID_SERIAL names.
# Devices are listed by Android version, oldest first; offline ones last.
# After a pick, the chosen device's row is shown on stderr (when that is a
# terminal), so adbs, adbt and prefix + a say which device they picked.

tmp=$(mktemp -d) || exit 1
trap 'rm -rf "$tmp"' EXIT

# One tab-separated row per device: serial, name, model, vendor, bitness,
# android, kernel. The name is the marketing name ("Galaxy S8+") where the
# device has one: an emulator's AVD name, a vendor marketname property, else
# the device name from Settings > About (user-editable). Many devices only
# report the model again there; then the name is "-" rather than a repeat.
row() {
  if [ "$2" != device ]; then
    printf '%s\t-\t(%s)\t-\t-\t-\t-\n' "$1" "$2"
    return
  fi
  adb -s "$1" shell 'getprop ro.product.model; getprop ro.product.manufacturer;
    getprop ro.product.cpu.abilist64; getprop ro.build.version.release; uname -r;
    getprop ro.product.marketname; getprop ro.product.vendor.marketname;
    getprop ro.config.marketing_name; settings get global device_name 2>/dev/null;
    getprop ro.boot.qemu.avd_name' \
    2>/dev/null | tr -d '\r' | awk -v s="$1" '{ v[NR] = $0 } END {
      name = "-"
      if (v[10] != "") { name = v[10]; gsub("_", " ", name) }
      else for (i = 6; i <= 9; i++) if (v[i] != "" && v[i] != "null") { name = v[i]; break }
      if (name == v[1]) name = "-"
      printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n", s, name, v[1], v[2],
        (v[3] != "" ? "64-bit" : "32-bit"), v[4], v[5] }'
}

if [ "$1" = --current ] && [ -z "$ANDROID_SERIAL" ]; then
  echo "adb-pick: ANDROID_SERIAL is not set (pick a device with adbs)" >&2
  exit 1
fi

# Query all devices in parallel (only ANDROID_SERIAL's with --current).
only=; [ "$1" = --current ] && only=$ANDROID_SERIAL
adb devices 2>/dev/null | awk -v only="$only" \
  'NR > 1 && NF && (only == "" || $1 == only) { print $1, $2 }' | {
  n=0
  while read -r serial state; do
    n=$((n + 1))
    row "$serial" "$state" > "$tmp/$(printf %03d "$n")" &
  done
  wait
}

if [ -z "$(ls "$tmp")" ]; then
  if [ "$1" = --current ]; then
    echo "adb-pick: ANDROID_SERIAL=$ANDROID_SERIAL is not attached" >&2
  else
    echo "adb-pick: no devices attached" >&2
  fi
  exit 1
fi

# Device rows by Android version (version order, so 9 < 14), then serial.
# Rows without a version (offline, unauthorized, ...) go last.
sort_by_android() {
  awk -F '\t' '{ print ($6 ~ /^[0-9]/ ? 0 : 1) "\t" $0 }' |
    sort -t "$(printf '\t')" -k1,1n -k7,7V -k2,2 | cut -f 2-
}

# Aligned device table, titles centered. $1 separates cells in device rows;
# $2 and $3 wrap the whole title row (awk -v turns \033 into escape codes).
# $4, if given, limits the table to that one serial.
table() {
  {
    printf 'SERIAL\tNAME\tMODEL\tVENDOR\tBITS\tANDROID\tKERNEL\n'
    cat "$tmp"/* | awk -F '\t' -v s="$4" 's == "" || $1 == s' | sort_by_android
  } | awk -F '\t' -v sep="$1" -v title_on="$2" -v title_off="$3" '
    { for (i = 1; i <= NF; i++) { c[NR, i] = $i; if (length($i) > w[i]) w[i] = length($i) } }
    END {
      for (r = 1; r <= NR; r++) {
        line = ""
        for (i = 1; i <= 7; i++) {
          cell = c[r, i]
          if (r == 1) cell = sprintf("%" int((w[i] + length(cell)) / 2) "s", cell)
          line = line (i > 1 ? (r == 1 ? " | " : sep) : "") sprintf("%-" w[i] "s", cell)
        }
        print (r == 1 ? title_on line title_off : line)
      }
    }'
}

# The "|" in device rows are blue, like the title row and fzf's 2/2 counter.
blue_sep=" \033[34m|\033[39m "

if [ "$1" = --list ] || [ "$1" = --current ]; then
  if [ -t 1 ]; then
    table "$blue_sep" "\033[1;34m" "\033[0m"
  else
    table " | " "" ""
  fi
  exit 0
fi

# Colors follow atuin's default look (Ctrl-R): plain terminal colors, a ">"
# pointer and the selected row in bold tmux-tab gold (#6f5211), no highlight bar.
colors="fg:-1,bg:-1,hl:4,fg+:#6f5211:bold,bg+:-1,hl+:#6f5211:bold:underline,gutter:-1"
colors="$colors,pointer:#6f5211:bold,marker:#6f5211,prompt:-1,query:-1,header:4:bold"
colors="$colors,info:4,separator:8,spinner:2"

# The title row is fzf's header (not selectable); fzf colors it.
pick=$(table "$blue_sep" "" "" | fzf --prompt="adb device> " --header-lines=1 \
  --height=~100% --layout=reverse-list --ansi --pointer=">" --color="$colors")

serial=$(printf '%s' "$pick" | awk '{ print $1 }')
[ -n "$serial" ] || exit 1
[ -t 2 ] && table "$blue_sep" "\033[1;34m" "\033[0m" "$serial" >&2
printf '%s\n' "$serial"
