"""An in-memory tmux server.

Implements the subset of tmux that tmux_sessionizer issues, faithfully enough that the
builder's real failure modes show up in tests: splits that run out of room, a
serialized layout whose pane count does not match the window, panes that are
still booting when keys arrive.

It plugs in wherever a ``tmux_sessionizer.proc.Runner`` does, so nothing in the package
knows it exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from tmux_sessionizer.proc import CommandError
from tmux_sessionizer.proc import Result
from tmux_sessionizer import layout as layout_mod


@dataclass
class FakePane:
    index: int
    id: str
    path: str
    keys: list[str] = field(default_factory=list)
    #: Variables passed with split-window -e.
    env: dict[str, str] = field(default_factory=dict)
    #: Captures remaining before the pane draws anything, as a booting shell.
    boot_captures: int = 0
    #: Captures after that which each show *different* text, as a prompt being
    #: drawn in stages. Keys sent during these get echoed twice by a real shell.
    redraw_captures: int = 0

    @property
    def commands(self) -> list[str]:
        """Commands typed into this pane, in order."""
        return [key for key in self.keys if key != "C-m"]


@dataclass
class FakeWindow:
    id: str
    name: str
    panes: list[FakePane]
    layout: str = ""
    #: Window options, e.g. {"@adb_serial": "emulator-5554"}.
    options: dict[str, str] = field(default_factory=dict)


@dataclass
class FakeSession:
    name: str
    path: str
    width: int
    height: int
    windows: list[FakeWindow] = field(default_factory=list)


class FakeTmux:
    """A tmux server that lives in a dict."""

    def __init__(
        self,
        *,
        pane_base_index: int = 1,
        max_panes: int = 16,
        boot_captures: int = 0,
        installed: bool = True,
    ) -> None:
        self.sessions: dict[str, FakeSession] = {}
        self.pane_base_index = pane_base_index
        self.max_panes = max_panes
        self.boot_captures = boot_captures
        self.redraw_captures = 0
        self.installed = installed
        self.current: str | None = None
        self.attached: list[str] = []
        self.switched: list[str] = []
        self.selected_windows: list[str] = []
        self.selected_panes: list[str] = []
        self.calls: list[list[str]] = []
        #: (argv, kwargs) for assertions about *how* a command was run.
        self.invocations: list[tuple[list[str], dict]] = []
        self.client_size: tuple[int, int] | None = (200, 50)
        #: Commands the server should refuse, e.g. {"split-window"}.
        self.fail: set[str] = set()
        #: Accept switch-client but do not honour it, as a wedged client would.
        self.ignore_switch = False
        self._next_id = 0

    # -- Runner interface -------------------------------------------------

    def which(self, program: str) -> str | None:
        return f"/usr/bin/{program}" if (program == "tmux" and self.installed) else None

    def run(self, argv: Sequence[str], *, check: bool = True, **kwargs: object) -> Result:
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        self.invocations.append((argv, dict(kwargs)))
        assert argv[0] == "tmux", f"only tmux is expected to run, got {argv[0]!r}"
        if argv[1] == "-L":  # a named server; irrelevant to the in-memory one
            argv = [argv[0], *argv[3:]]

        command = argv[1]
        handler = getattr(self, f"_cmd_{command.replace('-', '_')}", None)
        if handler is None:
            raise AssertionError(f"FakeTmux does not implement 'tmux {command}'")

        if command in self.fail:
            return self._fail(argv, check, f"{command}: refused by the test")
        try:
            stdout = handler(argv[2:]) or ""
        except _Refused as exc:
            return self._fail(argv, check, str(exc))
        return Result(tuple(argv), 0, stdout, "")

    def _fail(self, argv: list[str], check: bool, message: str) -> Result:
        if check:
            raise CommandError(argv, 1, message)
        return Result(tuple(argv), 1, "", message)

    # -- helpers ----------------------------------------------------------

    def _uid(self, sigil: str) -> str:
        self._next_id += 1
        return f"{sigil}{self._next_id}"

    @staticmethod
    def _flag(args: list[str], name: str, default: str = "") -> str:
        return args[args.index(name) + 1] if name in args else default

    #: tmux flags that take a value; everything else starting with "-" is a switch.
    VALUE_FLAGS = frozenset({"-t", "-c", "-s", "-n", "-x", "-y", "-F", "-S", "-e"})

    @classmethod
    def _positional(cls, args: list[str]) -> list[str]:
        """Arguments that are neither flags nor flag values."""
        out: list[str] = []
        skip = False
        for index, arg in enumerate(args):
            if skip:
                skip = False
                continue
            if arg == "--":
                out.extend(args[index + 1 :])
                break
            if arg in cls.VALUE_FLAGS:
                skip = True
                continue
            if arg.startswith("-") and arg != "-":
                continue
            out.append(arg)
        return out

    def _session(self, target: str) -> FakeSession:
        """Resolve a session target the way tmux does.

        Without a leading ``=`` tmux matches on *prefix*, so "work" can resolve
        to "workshop" - which is exactly why tmux_sessionizer always sends ``=name``.
        """
        exact = target.startswith("=")
        name = target.lstrip("=").split(":")[0]
        if name in self.sessions:
            return self.sessions[name]
        if not exact:
            matches = [key for key in self.sessions if key.startswith(name)]
            if len(matches) == 1:
                return self.sessions[matches[0]]
        raise _Refused(f"can't find session: {name}")

    def _window(self, target: str) -> FakeWindow:
        if not target:
            window = self._current_window()
            if window is None:
                raise _Refused("no current window")
            return window
        if target.startswith("@"):
            for session in self.sessions.values():
                for window in session.windows:
                    if window.id == target:
                        return window
            raise _Refused(f"can't find window: {target}")
        session = self._session(target)
        if not session.windows:
            raise _Refused(f"session has no windows: {target}")
        return session.windows[0]

    def _current_window(self) -> FakeWindow | None:
        if self.current and self.sessions[self.current].windows:
            return self.sessions[self.current].windows[0]
        return None

    def _pane(self, pane_id: str) -> FakePane:
        for session in self.sessions.values():
            for window in session.windows:
                for pane in window.panes:
                    if pane.id == pane_id:
                        return pane
        raise _Refused(f"can't find pane: {pane_id}")

    def _new_pane(self, path: str, index: int) -> FakePane:
        return FakePane(
            index,
            self._uid("%"),
            path,
            boot_captures=self.boot_captures,
            redraw_captures=self.redraw_captures,
        )

    def _new_window(self, name: str, path: str) -> FakeWindow:
        window = FakeWindow(self._uid("@"), name, [])
        window.panes.append(self._new_pane(path, self.pane_base_index))
        return window

    # -- commands ---------------------------------------------------------

    def _cmd_has_session(self, args: list[str]) -> str:
        self._session(self._flag(args, "-t"))
        return ""

    def _cmd_list_sessions(self, _: list[str]) -> str:
        return "".join(f"{name}\n" for name in self.sessions)

    def _cmd_new_session(self, args: list[str]) -> str:
        name = self._flag(args, "-s")
        if name in self.sessions:
            raise _Refused(f"duplicate session: {name}")
        session = FakeSession(
            name,
            self._flag(args, "-c"),
            int(self._flag(args, "-x", "80")),
            int(self._flag(args, "-y", "24")),
        )
        session.windows.append(self._new_window("bash", session.path))
        self.sessions[name] = session
        return ""

    def _cmd_kill_session(self, args: list[str]) -> str:
        session = self._session(self._flag(args, "-t"))
        del self.sessions[session.name]
        if self.current == session.name:
            self.current = None
        return ""

    def _cmd_switch_client(self, args: list[str]) -> str:
        session = self._session(self._flag(args, "-t"))
        self.switched.append(session.name)
        if not self.ignore_switch:
            self.current = session.name
        return ""

    def _cmd_attach_session(self, args: list[str]) -> str:
        session = self._session(self._flag(args, "-t"))
        self.current = session.name
        self.attached.append(session.name)
        return ""

    def _cmd_display_message(self, args: list[str]) -> str:
        fields = self._positional(args)
        if not fields:
            return ""
        field_ = fields[0]
        if field_ == "#S":
            return self.current or ""
        if field_ == "#{client_width}x#{client_height}":
            if self.client_size is None:
                # No client attached: tmux expands both fields to nothing.
                return "x"
            return f"{self.client_size[0]}x{self.client_size[1]}"
        if field_ == "#{window_layout}":
            return self._window(self._flag(args, "-t")).layout
        if field_ == "#{window_id}":
            return self._window(self._flag(args, "-t")).id
        return ""

    def _cmd_list_windows(self, args: list[str]) -> str:
        session = self._session(self._flag(args, "-t"))
        return "".join(f"{w.id}\t{w.name}\n" for w in session.windows)

    def _cmd_new_window(self, args: list[str]) -> str:
        session = self._session(self._flag(args, "-t"))
        window = self._new_window(self._flag(args, "-n"), self._flag(args, "-c"))
        session.windows.append(window)
        return window.id

    def _cmd_rename_window(self, args: list[str]) -> str:
        window = self._window(self._flag(args, "-t"))
        window.name = self._positional(args)[0]
        return ""

    def _cmd_select_window(self, args: list[str]) -> str:
        self.selected_windows.append(self._window(self._flag(args, "-t")).id)
        return ""

    def _cmd_list_panes(self, args: list[str]) -> str:
        window = self._window(self._flag(args, "-t"))
        return "".join(f"{p.index}\t{p.id}\n" for p in window.panes)

    def _cmd_split_window(self, args: list[str]) -> str:
        window = self._window(self._flag(args, "-t"))
        if len(window.panes) >= self.max_panes:
            raise _Refused("no space for new pane")
        pane = self._new_pane(self._flag(args, "-c"), max(p.index for p in window.panes) + 1)
        for index, arg in enumerate(args):
            if arg == "-e":
                key, _, value = args[index + 1].partition("=")
                pane.env[key] = value
        window.panes.append(pane)
        return ""

    def _cmd_show_options(self, args: list[str]) -> str:
        window = self._window(self._flag(args, "-t"))
        value = window.options.get(self._positional(args)[0])
        return "" if value is None else value + "\n"

    def _cmd_select_layout(self, args: list[str]) -> str:
        window = self._window(self._flag(args, "-t"))
        layout = self._positional(args)[0]
        if not layout_mod.is_builtin(layout):
            try:
                layout_mod.validate(layout)
            except Exception as exc:  # noqa: BLE001 - tmux says only "invalid layout"
                raise _Refused("invalid layout") from exc

        wanted = layout_mod.count_panes(layout)
        # Real tmux 3.5a is asymmetric here, and the difference hides bugs:
        # too many panes is an error, too few is accepted and does nothing.
        if wanted > len(window.panes):
            return ""
        if wanted and wanted < len(window.panes):
            raise _Refused(f"have {len(window.panes)} panes but need {wanted}: {layout}")
        window.layout = layout
        return ""

    def _cmd_select_pane(self, args: list[str]) -> str:
        self.selected_panes.append(self._pane(self._flag(args, "-t")).id)
        return ""

    def _cmd_capture_pane(self, args: list[str]) -> str:
        pane = self._pane(self._flag(args, "-t"))
        if pane.boot_captures > 0:
            pane.boot_captures -= 1
            return "\n"
        if pane.redraw_captures > 0:
            pane.redraw_captures -= 1
            return f"drawing {pane.redraw_captures}\n"
        return "$ \n"

    def _cmd_send_keys(self, args: list[str]) -> str:
        pane = self._pane(self._flag(args, "-t"))
        pane.keys.extend(self._positional(args))
        return ""


class _Refused(Exception):
    """The fake server rejected a command, the way tmux would."""
