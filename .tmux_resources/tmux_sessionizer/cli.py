"""Command line interface.

``main`` returns an exit code rather than calling ``sys.exit`` so tests can drive
every subcommand directly. Known failures (:class:`~tmux_sessionizer.errors.TmuxSessionizerError`)
print one clean line; anything else keeps its traceback, because it is a bug.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from .console import Console
from .proc import Runner

from . import __version__, config, discovery
from .builder import SessionBuilder
from .errors import TmuxSessionizerError
from .manager import LayoutManager
from .tmux import RunnerLike, Tmux

PROGRAM = "tmux_sessionizer"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Build tmux sessions from declarative TOML files.",
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM} {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="echo every tmux command")
    sub = parser.add_subparsers(dest="command", required=True)

    session = sub.add_parser(
        "session", help="create a session from a file, or attach if it exists"
    )
    session.add_argument(
        "session", help="path to a .tmux.toml file, or a session name on the search path"
    )
    session.add_argument(
        "--no-attach", action="store_true", help="build the session but stay where you are"
    )
    session.add_argument(
        "--keep-scratch",
        action="store_true",
        help="keep tmux's auto-named numeric sessions instead of pruning them",
    )

    check = sub.add_parser("check", help="validate session files without touching tmux")
    check.add_argument("session", nargs="*", help="defaults to every file on the search path")
    check.add_argument(
        "--no-path-check",
        action="store_true",
        help="skip the 'does this directory exist' check (useful off-host)",
    )

    listing = sub.add_parser("list", help="show the session files on the search path")
    listing.add_argument("--paths", action="store_true", help="print full paths only")

    layout = sub.add_parser("layout", help="apply a layout to a window, adding panes as needed")
    layout.add_argument("layout", help="a builtin name (tiled, main-vertical, ...) or a layout string")
    layout.add_argument("-n", "--panes", type=int, help="pane count; required for builtin layouts")
    layout.add_argument("-t", "--target", default="", help="window target (default: current)")
    layout.add_argument("-c", "--cwd", default=None, help="working directory for new panes")

    capture = sub.add_parser(
        "layout_capture", help="print a window's layout string for pasting into a session file"
    )
    capture.add_argument("-t", "--target", default="", help="window target (default: current)")

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    console: Console | None = None,
    runner: RunnerLike | None = None,
) -> int:
    """Run one command. *runner* overrides the subprocess seam, for tests."""
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if console is None:
        console = Console(verbose=args.verbose)
    elif args.verbose:
        console.verbose = True

    try:
        return _dispatch(args, console, runner)
    except TmuxSessionizerError as exc:
        console.error(str(exc))
        _report_to_status_line(str(exc), runner)
        return 1
    except KeyboardInterrupt:
        console.error("interrupted")
        return 130


def _dispatch(args: argparse.Namespace, console: Console, runner: RunnerLike | None) -> int:
    if args.command == "session":
        return _session(args, console, runner)
    if args.command == "check":
        return _check(args, console)
    if args.command == "list":
        return _list(args, console)
    if args.command == "layout":
        return _layout(args, console, runner)
    if args.command == "layout_capture":
        return _layout_capture(args, console, runner)
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover


def _session(args: argparse.Namespace, console: Console, runner: RunnerLike | None) -> int:
    path = discovery.resolve(args.session)
    spec = config.load(path)
    builder = SessionBuilder(Tmux(runner=_runner(console, runner)))
    outcome = builder.up(
        spec, attach=not args.no_attach, prune_scratch=not args.keep_scratch
    )
    console.ok(outcome.summary)
    return 0


def _check(args: argparse.Namespace, console: Console) -> int:
    paths = [discovery.resolve(name) for name in args.session] or discovery.available()
    if not paths:
        console.warn("no session files found")
        return 1

    failures = 0
    for path in paths:
        try:
            spec = config.load(path, require_path=not args.no_path_check)
        except TmuxSessionizerError as exc:
            console.error(str(exc))
            failures += 1
            continue
        panes = sum(window.required_panes(1) for window in spec.windows)
        console.ok(f"{path}: '{spec.name}' - {len(spec.windows)} window(s), {panes} pane(s)")
    return 1 if failures else 0


def _list(args: argparse.Namespace, console: Console) -> int:
    paths = discovery.available()
    if not paths:
        console.warn("no session files found on " + ", ".join(str(p) for p in discovery.search_path()))
        return 1
    for path in paths:
        if args.paths:
            print(path)
        else:
            name = path.name[: -len(config.SUFFIX)]
            print(f"{name:<16} {path}")
    return 0


def _layout(args: argparse.Namespace, console: Console, runner: RunnerLike | None) -> int:
    manager = LayoutManager(Tmux(runner=_runner(console, runner)))
    result = manager.apply(args.layout, target=args.target, panes=args.panes, cwd=args.cwd)
    console.ok(result.summary)
    return 0


def _layout_capture(args: argparse.Namespace, console: Console, runner: RunnerLike | None) -> int:
    manager = LayoutManager(Tmux(runner=_runner(console, runner)))
    print(manager.capture(args.target))
    return 0


def _runner(console: Console, override: RunnerLike | None = None) -> RunnerLike:
    return override if override is not None else Runner(console=console)


def _report_to_status_line(message: str, runner: RunnerLike | None) -> None:
    """Also show the error in tmux's status line when there is one.

    Key bindings run tmux_sessionizer through ``run-shell``, which discards stderr - so
    without this a failing ``prefix D`` gives the user no feedback at all.
    """
    tmux = Tmux(runner=_runner(Console(), runner))
    if tmux.inside_tmux:
        tmux.display_message(f"tmux_sessionizer: {message.splitlines()[0]}")


def run() -> None:  # pragma: no cover - console entry point
    sys.exit(main())
