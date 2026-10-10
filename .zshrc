export ZSH="$HOME/.oh-my-zsh"
: ${ZSH_CUSTOM:=$ZSH/custom}
ZSH_THEME="robbyrussell"

plugins=(git z sudo colored-man-pages extract)
for plugin in zsh-autosuggestions zsh-syntax-highlighting; do
  if [[ -d "$ZSH_CUSTOM/plugins/$plugin" || -d "$ZSH/plugins/$plugin" ]]; then
    plugins+=("$plugin")
  fi
done
typeset -a _omz_plugins=()
for plugin in "${plugins[@]}"; do
  if [[ -d "$ZSH_CUSTOM/plugins/$plugin" || -d "$ZSH/plugins/$plugin" ]]; then
    _omz_plugins+=("$plugin")
  fi
done
plugins=("${_omz_plugins[@]}")

if [[ -r "$ZSH/oh-my-zsh.sh" ]]; then
  source "$ZSH/oh-my-zsh.sh"
fi

__cmd_exists() { command -v "$1" >/dev/null 2>&1; }

typeset -gi _GIT_BRANCH_MAX_LEN=20

function _update_git_branch_vars() {
  local branch

  if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    unset CURR_GIT_BRANCH CURR_GIT_BRANCH_SHORT
    return
  fi

  branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null)

  if [[ -z "$branch" ]]; then
    branch="$(git rev-parse --short HEAD 2>/dev/null)"
    [[ -n "$branch" ]] && branch="detached@$branch"
  fi

  [[ -z "$branch" ]] && {
    unset CURR_GIT_BRANCH CURR_GIT_BRANCH_SHORT
    return
  }

  export CURR_GIT_BRANCH="$branch"
  export CURR_GIT_BRANCH_SHORT="${branch[1,_GIT_BRANCH_MAX_LEN]}"
}

autoload -Uz add-zsh-hook
add-zsh-hook precmd _update_git_branch_vars


autoload -U colors && colors
CYAN_DIR="%F{#00ffff}"
GOLD="%F{#daa425}%B"
PURPLE_USER="%F{#7a3db8}%B"
RESET="%f%b"

_PROMPT_BASE="${CYAN_DIR}%~${RESET} ${GOLD}❯ ${RESET}"
PROMPT=$_PROMPT_BASE

# Entered lines get the time Enter was pressed (dim, before the dir), while the
# line being typed has none: on Enter the prompt is redrawn with the time, and
# precmd puts the plain prompt back for the next line.
_prompt_time_on_enter() { PROMPT="%F{8}%*%f $_PROMPT_BASE"; zle reset-prompt; }
_prompt_time_reset() { PROMPT=$_PROMPT_BASE; }
autoload -Uz add-zle-hook-widget
add-zle-hook-widget line-finish _prompt_time_on_enter
add-zsh-hook precmd _prompt_time_reset

HISTFILE=$HOME/.zsh_history
HISTSIZE=100000
SAVEHIST=100000
setopt APPEND_HISTORY
setopt INC_APPEND_HISTORY_TIME
setopt HIST_IGNORE_ALL_DUPS
setopt HIST_SAVE_NO_DUPS
setopt HIST_IGNORE_SPACE
setopt EXTENDED_HISTORY
setopt NO_SHARE_HISTORY
setopt HIST_VERIFY

# Everything platform-specific (Homebrew, macOS plugins, where fzf comes from)
# lives in ~/.zshrc.local, one per machine and never shared. Sourced here: after
# oh-my-zsh, whose key bindings would override fzf's, and before atuin, which
# must win Ctrl-R.
[[ -f "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"

# Where .zshrc.local did not set fzf up (the offline machine), fzf 0.48+ carries
# its own key bindings and completion. ~/.local/bin is not on PATH yet here.
if (( ! $+functions[fzf-history-widget] )); then
  for _fzf in fzf "$HOME/.local/bin/fzf"; do
    if __cmd_exists "$_fzf"; then source <("$_fzf" --zsh); break; fi
  done
  unset _fzf
fi

if command ls --color=auto >/dev/null 2>&1; then
  alias ls='ls --color=auto'
  alias ll='ls -lah --color=auto'
elif command ls -G >/dev/null 2>&1; then
  alias ls='ls -G'
  alias ll='ls -laG'
else
  alias ls='ls'
  alias ll='ls -la'
fi

if __cmd_exists ggrep; then
  alias grep='ggrep --color=auto'
elif [[ "$(grep --version 2>/dev/null)" == *GNU* ]]; then
  alias grep='grep --color=auto'
fi

if __cmd_exists bat; then
  alias cat='bat --style=header,grid,changes --paging=never'
  export BAT_THEME="TwoDark"
elif __cmd_exists batcat; then
  alias cat='batcat --style=header,grid,changes --paging=never'
  export BAT_THEME="TwoDark"
fi
alias ..='cd ..'
alias ...='cd ../..'

tmux_remove_ssh_sessions() {
  local s
  while IFS= read -r s; do
    case "$s" in
      SSH|SSH[0-9]*)
        tmux kill-session -t "$s" >/dev/null 2>&1 || true
        ;;
    esac
  done < <(tmux list-sessions -F '#{session_name}' 2>/dev/null || true)
}

# Pick an adb device with fzf and point this shell at it via ANDROID_SERIAL.
# Same picker as prefix + a in tmux (~/.tmux/scripts/adb-pick.sh), which also
# prints the picked device's details (name, model, vendor, ...) as adbl does.
adbs() {
  local serial
  serial=$(sh "$HOME/.tmux/scripts/adb-pick.sh") || return
  export ANDROID_SERIAL=$serial
  echo "ANDROID_SERIAL=$serial"
}

# Like adbs, but also turns the current tmux window into an adb window (as
# prefix + a does): the tab shows the serial and new splits inherit it.
# Only this shell and future panes get ANDROID_SERIAL; other panes already open
# in the window keep their environment, since a process's env can't be changed
# from outside it.
adbt() {
  if [[ -z "$TMUX" ]]; then
    echo "adbt: not inside tmux (use adbs)" >&2
    return 1
  fi
  local serial
  serial=$(sh "$HOME/.tmux/scripts/adb-pick.sh") || return
  export ANDROID_SERIAL=$serial
  tmux set-option -w -t "$TMUX_PANE" @adb_serial "$serial"
  echo "ANDROID_SERIAL=$serial (this pane + new panes in this window)"
}

# Which adb device this shell targets.
adbw() { echo "$ANDROID_SERIAL"; }

# Print all adb devices with their details (same table as the adbs picker).
adbl() { sh "$HOME/.tmux/scripts/adb-pick.sh" --list; }

# Like adbl, but only the device ANDROID_SERIAL points at (fails if unset).
adbc() { sh "$HOME/.tmux/scripts/adb-pick.sh" --current; }

# The green "needs attention" tab in tmux (~/.tmux/scripts/attn.sh). They act
# on the window this shell is in, not the one you are looking at, so
# `sleep 60; attn_on` flags this window even after you have moved on.
attn_on()  { sh "$HOME/.tmux/scripts/attn.sh" on; }
attn_off() { sh "$HOME/.tmux/scripts/attn.sh" off; }
attn_tog() { sh "$HOME/.tmux/scripts/attn.sh" tog; }

# attn <command> [args...]: clears the green tab, runs the command, and turns
# the tab green when it finishes, so the window says when it is done. The
# arguments are run as given ("$@"), so quotes in them survive as typed. The
# tab goes green even if the command fails or is Ctrl-C'd, and attn returns
# the command's exit status. The alias's trailing space makes zsh expand an
# alias in the word after it (attn ll), as with sudo; "function" keeps that
# alias from touching this definition when .zshrc is sourced again.
function attn() {
  if (( $# == 0 )); then
    echo "usage: attn <command> [args...]" >&2
    return 2
  fi
  attn_off
  { "$@" } always { attn_on }
}
alias attn='attn '
(( $+functions[compdef] )) && compdef _precommand attn

print -Pn "\e]11;#191724\a"

typeset -gA ZSH_HIGHLIGHT_STYLES
ZSH_HIGHLIGHT_STYLES[command]='fg=#ffd6e7,bold'
ZSH_HIGHLIGHT_STYLES[hashed-command]='fg=#ffd6e7,bold'
ZSH_HIGHLIGHT_STYLES[builtin]='fg=#ffd6e7,bold'
ZSH_HIGHLIGHT_STYLES[function]='fg=#ffd6e7,bold'
ZSH_HIGHLIGHT_STYLES[alias]='fg=#ffd6e7,bold'
ZSH_HIGHLIGHT_STYLES[precommand]='fg=#ffd6e7,bold'
ZSH_HIGHLIGHT_STYLES[unknown-command]='fg=#ffd6e7'
ZSH_HIGHLIGHT_STYLES[unknown-token]='fg=#ffd6e7'
ZSH_HIGHLIGHT_STYLES[comment]='fg=#e0af68'
ZSH_HIGHLIGHT_STYLES[path]='fg=#5ecbff'
ZSH_HIGHLIGHT_STYLES[path_prefix]='fg=#5ecbff'
ZSH_HIGHLIGHT_STYLES[path_path]='fg=#5ecbff'

autoload -Uz bracketed-paste-magic
zle -N bracketed-paste bracketed-paste-magic

export ASM_LSP_CONFIG="$HOME/.config/asm-lsp/.asm-lsp.toml"
[[ -d "$HOME/.local/bin" ]] && export PATH="$HOME/.local/bin:$PATH"


# Same script tmux copies with, so Alt+Shift+C, c and tmux's y all pick the
# clipboard the same way on macOS and Linux (incl. xclip over SSH -X).
copy_to_clipboard() { sh "$HOME/.tmux/scripts/clip-copy.sh"; }

paste_from_clipboard() {
  if command -v pbpaste >/dev/null 2>&1; then
    pbpaste
  elif command -v wl-paste >/dev/null 2>&1; then
    wl-paste
  elif command -v xclip >/dev/null 2>&1; then
    xclip -selection clipboard -o
  elif command -v xsel >/dev/null 2>&1; then
    xsel --clipboard --output
  else
    echo "No clipboard tool found (install pbpaste, wl-paste, xclip, or xsel)" >&2
    return 1
  fi
}

c() { copy_to_clipboard; }
v() { paste_from_clipboard; }


zle-copy-buffer-to-clipboard() {
  if [[ -n "$BUFFER" ]]; then
    print -rn -- "$BUFFER" | copy_to_clipboard
  fi
}
zle -N zle-copy-buffer-to-clipboard
bindkey "^[C" zle-copy-buffer-to-clipboard

if __cmd_exists atuin; then
  eval "$(atuin init zsh --disable-up-arrow)"
fi

[[ -f "$HOME/.zshrc.personal" ]] && source "$HOME/.zshrc.personal"
