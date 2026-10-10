"""Generic interactive picker: fzf when available, a numbered prompt otherwise.

Used by mfixup (pick a commit to fixup into) and mfixupa (same, per file),
and available to any future m* command that needs to let the user choose one
item from a list.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

from .cli import CliError, colorize

if TYPE_CHECKING:
    from .refs import Commit

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)

# Same palette the old .git-fixup.sh used, with sane fallbacks so the picker
# still looks reasonable if these env vars aren't set in the shell. fzf
# accepts one comma-separated --color value; the env vars just let a shell
# profile override individual colors without editing this file.
_FZF_COLOR_SPEC = (
    "fg:{FZF_COLOR_PALEGOLD_HEX},bg:{FZF_COLOR_BG_HEX},hl:{FZF_COLOR_CYAN_HEX},"
    "fg+:{FZF_COLOR_PALEGOLD_HEX},bg+:{FZF_COLOR_BG_ALT_HEX},hl+:{FZF_COLOR_CYAN_HEX},"
    "info:{FZF_COLOR_CYAN_HEX},prompt:{FZF_COLOR_CYAN_HEX},pointer:{FZF_COLOR_POINTER_HEX},"
    "marker:{FZF_COLOR_MARKER_HEX},spinner:{FZF_COLOR_SPINNER_HEX},header:{FZF_COLOR_HEADER_HEX}"
)
_FZF_DEFAULTS = {
    "FZF_COLOR_PALEGOLD_HEX": "#fdf1df",
    "FZF_COLOR_BG_HEX": "-1",
    "FZF_COLOR_BG_ALT_HEX": "-1",
    "FZF_COLOR_CYAN_HEX": "#8be9fd",
    "FZF_COLOR_POINTER_HEX": "#ff79c6",
    "FZF_COLOR_MARKER_HEX": "#50fa7b",
    "FZF_COLOR_SPINNER_HEX": "#f1fa8c",
    "FZF_COLOR_HEADER_HEX": "#6272a4",
}


def _fzf_color_arg() -> list[str]:
    env = {**_FZF_DEFAULTS, **os.environ}
    return ["--color", _FZF_COLOR_SPEC.format(**env)]


def has_fzf() -> bool:
    return shutil.which("fzf") is not None


def pick_one(items: list[str], header: str | None = None) -> str | None:
    """Show `items` (one per line) and return the chosen line, or None if the
    user aborted the picker. Falls back to a plain numbered prompt if fzf
    isn't installed.
    """
    if not items:
        raise CliError("nothing to choose from")

    if has_fzf():
        return _pick_with_fzf(items, header)
    return _pick_with_prompt(items, header)


def _pick_with_fzf(items: list[str], header: str | None) -> str | None:
    cmd = [
        "fzf",
        "--ansi",
        "--height=100%",
        "--no-reverse",
        "--border=rounded",
        "--info=hidden",
        "--prompt=❯ ",
        "--marker=▶",
    ]
    if header:
        cmd += ["--header", header]
    cmd += _fzf_color_arg()

    proc = subprocess.run(cmd, input="\n".join(items), text=True, capture_output=True)
    if proc.returncode != 0:
        return None  # user pressed Esc/Ctrl-C, or no match
    return proc.stdout.strip() or None


def _pick_with_prompt(items: list[str], header: str | None) -> str | None:
    if header:
        print(header)
    for i, item in enumerate(items, start=1):
        print(f"  {i}) {item}")
    try:
        choice = input(f"select 1-{len(items)} (empty to cancel): ").strip()
    except EOFError:
        return None
    if not choice:
        return None
    if not choice.isdigit() or not (1 <= int(choice) <= len(items)):
        raise CliError(f"invalid selection: {choice!r}")
    return items[int(choice) - 1]


def pick_commit(commits: list[Commit], header: str | None = None) -> Commit | None:
    """Like pick_one, but takes/returns refs.Commit objects. Each item shows
    the commit hash in green, distinct from the (default-colored) message.

    Looked up by the ANSI-stripped text rather than the raw colored string:
    fzf's --ansi only uses embedded color codes for display and hands back
    the plain (decolored) line on selection, while the numbered-prompt
    fallback hands back the original colored string untouched -- stripping
    on both sides makes the lookup work either way.
    """
    display_items = [f"{colorize(c.short, '32')} {c.subject}" for c in commits]
    by_plain = {_strip_ansi(item): commit for item, commit in zip(display_items, commits)}
    chosen = pick_one(display_items, header=header)
    return by_plain.get(_strip_ansi(chosen)) if chosen is not None else None
