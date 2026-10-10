"""Standalone layout application: the ``~/.tmux_layout_manager`` replacement.

Ensures a window has exactly the panes a layout needs, then applies it. Shares
the growth logic with :mod:`tmux_sessionizer.builder` through :class:`~tmux_sessionizer.tmux.Tmux`
so a layout behaves identically whether it arrives from a session file or from
the command line.

The one deliberate difference from the old script: it refuses to *destroy*
panes. Having too many panes is an ambiguous state - tmux cannot know which one
you meant to keep - so it reports and stops rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import layout as layout_mod
from .errors import LayoutError, TmuxError
from .tmux import Tmux


@dataclass(frozen=True)
class LayoutResult:
    target: str
    layout: str
    panes_before: int
    panes_after: int

    @property
    def summary(self) -> str:
        if self.panes_after == self.panes_before:
            return f"applied layout to {self.target} ({self.panes_after} panes)"
        added = self.panes_after - self.panes_before
        return f"applied layout to {self.target} (+{added} pane(s), {self.panes_after} total)"


class LayoutManager:
    def __init__(self, tmux: Tmux) -> None:
        self.tmux = tmux

    def apply(
        self,
        layout: str,
        *,
        target: str = "",
        panes: int | None = None,
        cwd: str | None = None,
    ) -> LayoutResult:
        """Grow *target* to the layout's pane count, then apply the layout.

        *panes* overrides the count, which is the only way to size a builtin
        layout like ``tiled``. *target* defaults to the current window.
        """
        self.tmux.require_available()
        layout = layout_mod.validate(layout)

        window = target or self._current_window()

        declared = layout_mod.count_panes(layout)
        if panes is not None and declared and panes != declared:
            # tmux would accept this silently: select-layout with *fewer* panes
            # than the layout describes returns 0 and does nothing at all.
            raise LayoutError(
                f"the layout describes {declared} panes, but {panes} were requested; "
                f"drop the pane count or pass {declared}."
            )

        required = panes if panes is not None else declared
        if required <= 0:
            raise LayoutError(
                f"'{layout}' does not imply a pane count; pass an explicit number of panes."
            )

        existing = self.tmux.list_panes(window)
        if not existing:
            raise TmuxError(f"no such window: {window}")
        before = len(existing)

        if before > required:
            raise TmuxError(
                f"{window} has {before} panes but the layout wants {required}; "
                f"close {before - required} pane(s) first."
            )

        # An adb window (prefix + a in ~/.tmux.conf) scopes ANDROID_SERIAL to its
        # panes; new panes must get it too, as a hand-made split would.
        serial = self.tmux.window_option(window, "@adb_serial")
        env = {"ANDROID_SERIAL": serial} if serial else None

        current = before
        while current < required:
            self.tmux.select_layout(window, "tiled")
            if not self.tmux.split_window(window, cwd, env):
                raise TmuxError(
                    f"no room for pane {current + 1} of {required} in {window}; "
                    f"use a larger terminal or fewer panes."
                )
            current += 1

        if not self.tmux.select_layout(window, layout):
            raise TmuxError(f"tmux rejected the layout: {layout}")

        return LayoutResult(window, layout, before, current)

    def capture(self, target: str = "") -> str:
        """The current window's layout string, ready to paste into a session file."""
        self.tmux.require_available()
        layout = self.tmux.window_layout(target or self._current_window())
        if not layout:
            raise TmuxError("could not read the window layout; is a tmux server running?")
        return layout

    def _current_window(self) -> str:
        """The window this command was run from.

        Refuses to guess from outside tmux: with a server running,
        ``#{window_id}`` happily answers with *someone else's* window, and
        applying a layout to it would rearrange a session at random.
        """
        if not self.tmux.inside_tmux:
            raise TmuxError("not running inside tmux; name a window with --target.")
        window = self.tmux.window_id()
        if not window:
            raise TmuxError("could not identify the current window; pass --target.")
        return window
