"""Small console/argparse helpers shared by all git-m* scripts."""

from __future__ import annotations

import argparse
import sys


class CliError(Exception):
    """Raised for expected, user-facing failures. main() turns these into
    a clean 'error: ...' message instead of a traceback."""


def err(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def info(message: str) -> None:
    print(f"-- {message}", file=sys.stderr)


def colorize(text: str, sgr: str) -> str:
    """Wrap `text` in an ANSI SGR code (e.g. "1;33" for bold yellow),
    resetting after. A no-op when stdout isn't a real terminal, so piped
    output and captured test output stay plain text.
    """
    if not sys.stdout.isatty():
        return text
    return f"\033[{sgr}m{text}\033[0m"


def fixing_up_header(paths: list[str]) -> str:
    """The 'fixing up: <files>' picker header shared by mfixup and
    mfixupa -- one file per line so it stays readable regardless of how
    many files are involved.
    """
    label = colorize("fixing up:", "1;33")   # bold yellow
    files = "\n".join(colorize(f"  {p}", "34") for p in paths)  # blue
    return f"{label}\n{files}"


def add_branch_args(parser: argparse.ArgumentParser) -> None:
    """--branch/--remote, identical across every command that resolves a
    default branch (see gitm.refs.default_branch)."""
    parser.add_argument("--branch", help="mainline branch (default: master, or `git config gitm.default-branch`)")
    parser.add_argument("--remote", default="origin", help="remote name (default: origin)")


def add_squash_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--squash",
        action="store_true",
        help="also autosquash-rebase immediately (old default behavior)",
    )


def run_main(main_func) -> None:
    """Call main_func() and translate CliError/KeyboardInterrupt into clean exits."""
    try:
        main_func()
    except CliError as exc:
        err(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        print(file=sys.stderr)
        sys.exit(130)
