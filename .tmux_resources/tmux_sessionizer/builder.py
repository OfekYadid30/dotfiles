"""Turning a :class:`~tmux_sessionizer.spec.SessionSpec` into a live tmux session.

The build is *atomic*: the session is created detached, every window is built,
and only then is it handed to the client. If anything fails, the half-built
session is killed rather than left behind for the next attach to inherit.

Growing pane counts is the other subtlety. tmux refuses a split when a pane is
too small, so every split is preceded by a re-tile; without that, a ten-pane
layout fails around pane five with "no space for new pane".
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Callable

from . import layout as layout_mod
from .errors import TmuxError
from .spec import PaneSpec, SessionSpec, WindowSpec
from .tmux import FALLBACK_SIZE, Tmux


@dataclass(frozen=True)
class Outcome:
    """What :meth:`SessionBuilder.up` actually did."""

    session: str
    created: bool
    attached: bool
    windows: int = 0

    @property
    def summary(self) -> str:
        tail = "attached" if self.attached else "left detached"
        if not self.created:
            # Nothing was inspected, so do not claim to know its shape.
            return f"reused existing session '{self.session}', {tail}"
        return f"created session '{self.session}' ({self.windows} window(s)), {tail}"


class SessionBuilder:
    """Builds sessions. Stateless between calls; all state lives in tmux."""

    def __init__(
        self,
        tmux: Tmux,
        *,
        terminal_size: Callable[[], tuple[int, int]] | None = None,
    ) -> None:
        self.tmux = tmux
        self._terminal_size = terminal_size or _default_terminal_size

    # -- entry point ------------------------------------------------------

    def up(self, spec: SessionSpec, *, attach: bool = True, prune_scratch: bool = True) -> Outcome:
        """Ensure *spec*'s session exists, then optionally attach to it."""
        self.tmux.require_available()

        if self.tmux.has_session(spec.name):
            if attach:
                self.attach(spec.name, prune_scratch=prune_scratch)
            return Outcome(spec.name, created=False, attached=attach)

        self.create(spec)
        if attach:
            self.attach(spec.name, prune_scratch=prune_scratch)
        return Outcome(spec.name, created=True, attached=attach, windows=len(spec.windows))

    # -- creation ---------------------------------------------------------

    def create(self, spec: SessionSpec) -> None:
        """Build the session from scratch, cleaning up if any step fails."""
        if not spec.windows:
            raise TmuxError(f"session '{spec.name}' defines no windows.")

        width, height = self.session_size()
        # The first window is the one tmux creates with the session, so it must
        # be born in the first window's directory - it is never re-created.
        self.tmux.new_session(
            spec.name, str(spec.windows[0].path or spec.path), width, height
        )
        try:
            windows = self.tmux.list_windows(f"={spec.name}:")
            if not windows:
                raise TmuxError(f"session '{spec.name}' was created with no windows.")
            first_window_id = windows[0].id

            built: dict[int, str] = {}
            for position, window in enumerate(spec.windows):
                if position == 0:
                    window_id = first_window_id
                    self.tmux.rename_window(window_id, window.name)
                else:
                    window_id = self.tmux.new_window(
                        spec.name, window.name, str(window.path or spec.path)
                    )
                built[position] = window_id
                self._build_window(spec, window, window_id, size=(width, height))

            # By id, not by name: tmux allows duplicate window names.
            self.tmux.select_window(built[spec.focus_index])
        except BaseException:
            self.tmux.kill_session(spec.name)
            raise

    def session_size(self) -> tuple[int, int]:
        """The size to create the detached session at.

        Serialized layouts are recorded against a specific window size, so a
        session created at the client's real size reproduces them faithfully.
        Only a client of *this* session's server counts: asked from outside
        tmux, ``#{client_width}`` reports some unrelated terminal.
        """
        if self.tmux.inside_tmux:
            size = self.tmux.client_size()
            if size is not None:
                return size
        return self._terminal_size()

    # -- attaching --------------------------------------------------------

    def attach(self, name: str, *, prune_scratch: bool = True) -> None:
        """Switch the current client to *name*, or attach from outside tmux."""
        if not self.tmux.inside_tmux:
            # Blocks until the user detaches, so pruning afterwards is best effort.
            self.tmux.attach_session(name)
            if prune_scratch:
                self.prune_scratch_sessions(keep=name)
            return

        self.tmux.switch_client(name)
        if self.tmux.current_session() != name:
            raise TmuxError(
                f"switch to session '{name}' did not take effect; leaving other sessions alone."
            )
        if prune_scratch:
            self.prune_scratch_sessions(keep=name)

    def prune_scratch_sessions(self, *, keep: str) -> list[str]:
        """Kill sessions tmux auto-named (``0``, ``1``, ...); return what was killed.

        These accumulate whenever a bare ``tmux`` is run, and are never the
        session a config describes - a config name cannot be all digits without
        being confusable with them, so anything numeric is scratch.
        """
        killed = []
        for session in self.tmux.list_sessions():
            if session == keep or not session.isdigit():
                continue
            if self.tmux.kill_session(session):
                killed.append(session)
        return killed

    # -- windows ----------------------------------------------------------

    def _build_window(
        self, spec: SessionSpec, window: WindowSpec, window_id: str, *, size: tuple[int, int]
    ) -> None:
        path = str(window.path or spec.path)
        base = self.tmux.pane_base_index(window_id)
        required = window.required_panes(base)

        self._grow_panes(window, window_id, path, required=required, size=size)
        self._apply_layout(window, window_id, required=required)

        panes = {pane.index: pane.id for pane in self.tmux.list_panes(window_id)}
        wanted = window.resolve_panes(base)
        for index in sorted(wanted):
            if index not in panes:
                raise TmuxError(
                    f"window '{window.name}' drives pane {index - base + 1}, but only "
                    f"{len(panes)} pane(s) exist after the layout was applied."
                )

        # Setup runs everywhere, including panes the config never names.
        for index in sorted(panes):
            commands = list(spec.setup) + list(wanted.get(index, _EMPTY_PANE).commands)
            self._send(panes[index], commands)

        for index, pane in wanted.items():
            if pane.focus:
                self.tmux.select_pane(panes[index])

    def _grow_panes(
        self,
        window: WindowSpec,
        window_id: str,
        path: str,
        *,
        required: int,
        size: tuple[int, int],
    ) -> None:
        current = len(self.tmux.list_panes(window_id))
        while current < required:
            # Re-tile first: tmux splits the *active* pane, and an unbalanced
            # window runs out of room long before the pane count is reached.
            self.tmux.select_layout(window_id, "tiled")
            if not self.tmux.split_window(window_id, path):
                detail = ""
                natural = layout_mod.natural_size(window.layout) if window.layout else None
                if natural is not None:
                    detail = f" The layout was recorded at {natural[0]}x{natural[1]}."
                raise TmuxError(
                    f"no room for pane {current + 1} of {required} in window "
                    f"'{window.name}'. The session is {size[0]}x{size[1]}.{detail} "
                    f"Use a larger terminal or fewer panes."
                )
            current += 1

    def _apply_layout(self, window: WindowSpec, window_id: str, *, required: int) -> None:
        if window.layout:
            if not self.tmux.select_layout(window_id, window.layout):
                raise TmuxError(
                    f"tmux rejected the layout for window '{window.name}': {window.layout}"
                )
        elif required > 1:
            self.tmux.select_layout(window_id, "tiled")

    def _send(self, pane_id: str, commands: list[str]) -> None:
        if not commands:
            return
        self.tmux.wait_until_ready(pane_id)
        for command in commands:
            self.tmux.send_line(pane_id, command)

def _default_terminal_size() -> tuple[int, int]:
    size = shutil.get_terminal_size(fallback=FALLBACK_SIZE)
    width = size.columns if size.columns > 0 else FALLBACK_SIZE[0]
    height = size.lines if size.lines > 0 else FALLBACK_SIZE[1]
    return width, height



#: Stand-in for panes the config does not name; they still get the setup commands.
_EMPTY_PANE = PaneSpec()

__all__ = ["Outcome", "SessionBuilder"]
