"""Print text directly, falling back to a pager only when it wouldn't fit.

Deliberately doesn't rely on git's own pager invocation: that goes through
`core.pager`/`$LESS`/`$GIT_PAGER`, which a user's existing config can easily
leave in "always page, even for three lines" mode. This instead measures
against the real terminal height and only pages when the content actually
overflows it -- and never pages at all when stdout isn't a terminal (e.g.
piped or redirected), matching how well-behaved CLIs behave under `| cat`.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys


def _pager_command() -> list[str]:
    pager = os.environ.get("PAGER")
    if pager:
        return shlex.split(pager)
    return ["less", "-R"]  # -R: render the ANSI color codes we asked git for


def print_or_page(text: str) -> None:
    """Print `text` as-is, or through a pager if it's taller than the
    terminal and stdout is a real terminal.
    """
    if not text:
        return
    if not sys.stdout.isatty():
        sys.stdout.write(text)
        return

    height = shutil.get_terminal_size(fallback=(80, 24)).lines
    # -1: leave room for the shell prompt line that follows, so the last
    # line of output isn't immediately scrolled off.
    if text.count("\n") < height - 1:
        sys.stdout.write(text)
        return

    try:
        subprocess.run(_pager_command(), input=text, text=True)
    except (FileNotFoundError, OSError):
        sys.stdout.write(text)
