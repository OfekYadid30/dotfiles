"""The session model.

Frozen dataclasses with no I/O and no tmux, so a test can build any session
shape in two lines. :mod:`tmux_sessionizer.config` produces these from TOML;
:mod:`tmux_sessionizer.builder` consumes them.

Pane numbering is deliberately *relative* here. A spec says "the second pane",
not "pane 2", because the absolute index depends on the server's
``pane-base-index``. :meth:`WindowSpec.resolve_panes` does that mapping once the
base is known.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import layout as layout_mod


@dataclass(frozen=True)
class PaneSpec:
    """Commands for one pane.

    ``offset`` is the pane's position within the window counting from the
    server's base index: 0 is the first pane. It is ``None`` for panes that are
    simply listed in order, in which case position in the list decides.
    """

    commands: tuple[str, ...] = ()
    offset: int | None = None
    focus: bool = False


@dataclass(frozen=True)
class WindowSpec:
    name: str
    layout: str | None = None
    panes: tuple[PaneSpec, ...] = ()
    path: Path | None = None
    focus: bool = False

    @property
    def layout_pane_count(self) -> int:
        """Panes the layout demands, or 0 when it is a builtin or absent."""
        return layout_mod.count_panes(self.layout) if self.layout else 0

    def resolve_panes(self, base_index: int) -> dict[int, PaneSpec]:
        """Map absolute tmux pane index -> spec for a server whose panes start at *base_index*."""
        resolved: dict[int, PaneSpec] = {}
        for position, pane in enumerate(self.panes):
            offset = position if pane.offset is None else pane.offset
            resolved[base_index + offset] = pane
        return resolved

    def required_panes(self, base_index: int) -> int:
        """How many panes the window must have before commands can be sent."""
        resolved = self.resolve_panes(base_index)
        highest = max(resolved, default=base_index - 1) - base_index + 1
        return max(1, self.layout_pane_count, highest)


@dataclass(frozen=True)
class SessionSpec:
    """A whole session, ready to build."""

    name: str
    path: Path
    windows: tuple[WindowSpec, ...] = ()
    setup: tuple[str, ...] = ()
    source: Path | None = None

    @property
    def focus_index(self) -> int:
        """Position of the window to select on attach; the first unless one opts in.

        A position rather than a name, because tmux allows duplicate window names.
        """
        for position, window in enumerate(self.windows):
            if window.focus:
                return position
        return 0
