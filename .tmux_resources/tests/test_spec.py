"""The session model: pane addressing arithmetic, with no tmux involved."""

from __future__ import annotations

import pytest

from tmux_sessionizer.spec import PaneSpec, SessionSpec, WindowSpec

from .conftest import DEV_LAYOUT


def test_positional_panes_start_at_the_base_index() -> None:
    window = WindowSpec("w", panes=(PaneSpec(("a",)), PaneSpec(("b",))))
    assert sorted(window.resolve_panes(1)) == [1, 2]
    assert sorted(window.resolve_panes(0)) == [0, 1]


def test_an_offset_is_relative_to_the_base_index() -> None:
    # `at = 4` in a config becomes offset 3, which is pane 4 on a server whose
    # panes start at 1 and pane 3 on one whose panes start at 0.
    window = WindowSpec("w", panes=(PaneSpec(("x",), offset=3),))
    assert list(window.resolve_panes(1)) == [4]
    assert list(window.resolve_panes(0)) == [3]


def test_required_panes_covers_the_highest_address() -> None:
    window = WindowSpec("w", panes=(PaneSpec(offset=0), PaneSpec(offset=5)))
    assert window.required_panes(1) == 6
    assert window.required_panes(0) == 6


def test_required_panes_is_never_below_one() -> None:
    assert WindowSpec("w").required_panes(1) == 1
    assert WindowSpec("w", panes=(PaneSpec(),)).required_panes(1) == 1


def test_a_layout_raises_the_pane_count_it_needs() -> None:
    window = WindowSpec("w", layout=DEV_LAYOUT, panes=(PaneSpec(offset=1),))
    assert window.layout_pane_count == 10
    assert window.required_panes(1) == 10


def test_a_builtin_layout_implies_no_pane_count() -> None:
    assert WindowSpec("w", layout="tiled").layout_pane_count == 0
    assert WindowSpec("w", layout="tiled").required_panes(1) == 1


def test_the_last_pane_wins_when_two_share_an_address() -> None:
    # config.py rejects this; the model must still be well defined.
    window = WindowSpec("w", panes=(PaneSpec(("a",), offset=0), PaneSpec(("b",), offset=0)))
    assert window.resolve_panes(1)[1].commands == ("b",)


def test_focus_index_defaults_to_the_first_window() -> None:
    spec = SessionSpec("s", "/tmp", windows=(WindowSpec("a"), WindowSpec("b")))
    assert spec.focus_index == 0


def test_focus_index_finds_the_marked_window() -> None:
    spec = SessionSpec("s", "/tmp", windows=(WindowSpec("a"), WindowSpec("b", focus=True)))
    assert spec.focus_index == 1


def test_specs_are_immutable() -> None:
    with pytest.raises(AttributeError):
        WindowSpec("w").name = "other"
