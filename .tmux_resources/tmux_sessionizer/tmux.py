"""The only module that speaks to a tmux server.

Every tmux invocation in the package goes through :class:`Tmux`, which holds a
``Runner`` (see :mod:`tmux_sessionizer.proc`). Tests swap in a fake server, so the builder,
the layout manager and the CLI are all exercised without a real tmux.

Methods are thin and named after the tmux command they run. The one piece of
real logic here is :meth:`wait_until_ready`, which exists because a freshly
split pane is still running shell init: keys sent too early are swallowed or
echoed as a stray ``%``.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

from .proc import CommandError
from .proc import Result, Runner

from .errors import TmuxError

#: How long :meth:`Tmux.wait_until_ready` waits for a pane to settle.
PANE_READY_TIMEOUT = 6.0
PANE_READY_POLL = 0.05
#: How long a pane's output must stop changing before it counts as settled.
#: An interactive shell draws a bare prompt, sources its rc file, then redraws;
#: under load (ten panes booting at once) the bare prompt can sit still for
#: ~100ms, so a single quiet poll is not enough.
PANE_SETTLE = 0.2

#: Size used when neither a tmux client nor a terminal can tell us one. Matches
#: the old shell script so layouts recorded against it still fit.
FALLBACK_SIZE = (224, 60)

#: Names a tmux server other than the default one (``tmux -L <name>``). Mainly
#: so tests can drive a real tmux without touching the user's live sessions.
ENV_SOCKET = "TMUX_SESSIONIZER_SOCKET"


class RunnerLike(Protocol):
    def run(self, argv: Sequence[str], *, check: bool = True, **kwargs) -> Result: ...

    def which(self, program: str) -> str | None: ...


@dataclass(frozen=True)
class Pane:
    index: int
    id: str


@dataclass(frozen=True)
class Window:
    id: str
    name: str


class Tmux:
    """A tmux server, addressed by command."""

    def __init__(
        self,
        runner: RunnerLike | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        env: dict[str, str] | None = None,
    ) -> None:
        self.runner = runner or Runner()
        self.sleep = sleep
        self.monotonic = monotonic
        self.env = os.environ if env is None else env
        socket = self.env.get(ENV_SOCKET)
        self._argv0 = ["tmux", "-L", socket] if socket else ["tmux"]

    # -- plumbing ---------------------------------------------------------

    def _run(self, *args: str, check: bool = True, capture: bool = True) -> Result:
        try:
            return self.runner.run([*self._argv0, *args], check=check, capture=capture)
        except CommandError as exc:
            raise TmuxError(str(exc)) from exc

    def _try(self, *args: str) -> bool:
        """Run a command whose failure is expected and meaningful."""
        return self._run(*args, check=False).ok

    def _lines(self, *args: str) -> list[str]:
        result = self._run(*args, check=False)
        if not result.ok:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]

    # -- server -----------------------------------------------------------

    def require_available(self) -> None:
        if self.runner.which("tmux") is None:
            raise TmuxError("tmux is not installed or not in PATH.")

    @property
    def inside_tmux(self) -> bool:
        return bool(self.env.get("TMUX"))

    def has_session(self, name: str) -> bool:
        return self._run("has-session", "-t", f"={name}", check=False).ok

    def list_sessions(self) -> list[str]:
        return self._lines("list-sessions", "-F", "#{session_name}")

    def current_session(self) -> str:
        return self._run("display-message", "-p", "#S", check=False).out

    def client_size(self) -> tuple[int, int] | None:
        """The attached client's size, or ``None`` when there is no client."""
        result = self._run("display-message", "-p", "#{client_width}x#{client_height}", check=False)
        if not result.ok:
            return None
        width, _, height = result.out.partition("x")
        if not width.isdigit() or not height.isdigit():
            return None
        size = (int(width), int(height))
        return size if size[0] > 0 and size[1] > 0 else None

    def new_session(self, name: str, path: str, width: int, height: int) -> None:
        self._run(
            "new-session", "-d", "-s", name, "-c", path, "-x", str(width), "-y", str(height)
        )

    def kill_session(self, name: str) -> bool:
        return self._try("kill-session", "-t", f"={name}")

    def switch_client(self, name: str) -> None:
        self._run("switch-client", "-t", f"={name}")

    def attach_session(self, name: str) -> None:
        """Attach this terminal to *name*; blocks until the user detaches.

        ``capture=False`` is not a detail: the tmux client has to own the
        terminal. With stdout on a pipe it either hangs showing nothing or
        exits with "open terminal failed: not a terminal".
        """
        self._run("attach-session", "-t", f"={name}", capture=False)

    def display_message(self, text: str) -> None:
        """Show a message in the status line.

        The only way an error reaches a user who triggered tmux_sessionizer from a key
        binding: ``run-shell`` discards stderr.
        """
        self._run("display-message", "--", text, check=False)

    # -- windows ----------------------------------------------------------

    def list_windows(self, target: str) -> list[Window]:
        windows = []
        for line in self._lines("list-windows", "-t", target, "-F", "#{window_id}\t#{window_name}"):
            window_id, _, name = line.partition("\t")
            windows.append(Window(window_id, name))
        return windows

    def new_window(self, session: str, name: str, path: str) -> str:
        return self._run(
            "new-window", "-d", "-P", "-F", "#{window_id}",
            "-t", f"={session}:", "-n", name, "-c", path,
        ).out

    def rename_window(self, target: str, name: str) -> None:
        self._run("rename-window", "-t", target, name)

    def select_window(self, target: str) -> bool:
        return self._try("select-window", "-t", target)

    def window_id(self, target: str = "") -> str:
        """The id of the current window, or of *target*."""
        args = ["display-message", "-p"]
        if target:
            args += ["-t", target]
        return self._run(*args, "#{window_id}", check=False).out

    def window_layout(self, target: str = "") -> str:
        args = ["display-message", "-p"]
        if target:
            args += ["-t", target]
        return self._run(*args, "#{window_layout}", check=False).out

    # -- panes ------------------------------------------------------------

    def list_panes(self, target: str) -> list[Pane]:
        panes = []
        for line in self._lines("list-panes", "-t", target, "-F", "#{pane_index}\t#{pane_id}"):
            index, _, pane_id = line.partition("\t")
            if index.isdigit():
                panes.append(Pane(int(index), pane_id))
        return panes

    def pane_base_index(self, target: str) -> int:
        """The window's lowest pane index; tmux servers may set ``pane-base-index``."""
        panes = self.list_panes(target)
        if not panes:
            raise TmuxError(f"window {target!r} reports no panes.")
        return min(pane.index for pane in panes)

    def window_option(self, target: str, name: str) -> str:
        """A window option's value (e.g. ``@adb_serial``), or "" when unset."""
        return self._run("show-options", "-wqv", "-t", target, name, check=False).out

    def split_window(
        self, target: str, path: str | None = None, env: dict[str, str] | None = None
    ) -> bool:
        """Add one pane. Returns False when the window has no room left.

        With no *path*, tmux picks the cwd itself, which is what a user
        splitting a window by hand would get. *env* is set in the new pane only.
        """
        args = ["split-window", "-d", "-t", target]
        if path is not None:
            args += ["-c", path]
        for key, value in (env or {}).items():
            args += ["-e", f"{key}={value}"]
        return self._try(*args)

    def select_layout(self, target: str, layout: str) -> bool:
        return self._try("select-layout", "-t", target, layout)

    def select_pane(self, pane_id: str) -> bool:
        return self._try("select-pane", "-t", pane_id)

    def capture_pane(self, pane_id: str) -> str:
        return self._run("capture-pane", "-t", pane_id, "-p", "-S", "-1", check=False).stdout

    def send_line(self, pane_id: str, text: str) -> None:
        """Type *text* into a pane and press Enter.

        ``-l`` sends the text literally, so a command containing something like
        ``C-c`` is not interpreted as a key name.
        """
        self._run("send-keys", "-t", pane_id, "-l", "--", text)
        self._run("send-keys", "-t", pane_id, "C-m")

    def wait_until_ready(
        self,
        pane_id: str,
        *,
        timeout: float = PANE_READY_TIMEOUT,
        settle: float = PANE_SETTLE,
    ) -> bool:
        """Block until *pane_id* has settled at a prompt, or *timeout* elapses.

        "Settled" means the pane has drawn something *and* that something has
        stopped changing for *settle* seconds. Waiting only for non-empty output
        is not enough: an interactive shell shows a bare prompt, sources its rc
        file, then redraws, and keys that land mid-draw are echoed a second time
        by the redraw.

        Returns whether the pane settled. Callers proceed either way, because a
        pane that never settles must not block the whole build.
        """
        deadline = self.monotonic() + timeout
        previous: str | None = None
        unchanged_since = self.monotonic()
        while True:
            now = self.monotonic()
            current = self.capture_pane(pane_id).strip()
            if current != previous:
                previous = current
                unchanged_since = now
            elif current and now - unchanged_since >= settle:
                return True
            if now >= deadline:
                return False
            self.sleep(PANE_READY_POLL)
