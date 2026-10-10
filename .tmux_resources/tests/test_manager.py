"""The standalone layout command."""

from __future__ import annotations

import pytest

from tmux_sessionizer.errors import LayoutError, TmuxError
from tmux_sessionizer.manager import LayoutManager

from .conftest import TEMP_LAYOUT


@pytest.fixture
def manager(tmux_inside, server):
    server.run(["tmux", "new-session", "-d", "-s", "work", "-c", "/work", "-x", "200", "-y", "50"])
    server.current = "work"
    return LayoutManager(tmux_inside)


def window(server):
    return server.sessions["work"].windows[0]


def test_a_serialized_layout_supplies_its_own_pane_count(manager, server) -> None:
    result = manager.apply(TEMP_LAYOUT)
    assert (result.panes_before, result.panes_after) == (1, 4)
    assert window(server).layout == TEMP_LAYOUT
    assert "+3 pane(s)" in result.summary


def test_a_window_that_already_fits_is_only_relaid_out(manager, server) -> None:
    manager.apply(TEMP_LAYOUT)
    calls_before = len(server.calls)
    result = manager.apply(TEMP_LAYOUT)
    assert (result.panes_before, result.panes_after) == (4, 4)
    assert "split-window" not in [call[1] for call in server.calls[calls_before:]]


def test_a_builtin_layout_needs_an_explicit_pane_count(manager) -> None:
    with pytest.raises(LayoutError, match="does not imply a pane count"):
        manager.apply("tiled")


def test_a_builtin_layout_with_a_count_grows_the_window(manager, server) -> None:
    result = manager.apply("tiled", panes=3)
    assert result.panes_after == 3
    assert window(server).layout == "tiled"


def test_a_pane_count_that_contradicts_the_layout_is_refused(manager, server) -> None:
    # The layout wants 4. tmux would accept 2 panes and silently do nothing,
    # so the contradiction has to be caught here.
    with pytest.raises(LayoutError, match="describes 4 panes, but 2 were requested"):
        manager.apply(TEMP_LAYOUT, panes=2)
    assert len(window(server).panes) == 1


def test_a_matching_pane_count_is_accepted(manager, server) -> None:
    manager.apply(TEMP_LAYOUT, panes=4)
    assert len(window(server).panes) == 4


def test_too_many_panes_is_refused_rather_than_guessed(manager, server) -> None:
    manager.apply("tiled", panes=6)
    with pytest.raises(TmuxError, match="has 6 panes but the layout wants 4"):
        manager.apply(TEMP_LAYOUT)
    # Nothing was destroyed.
    assert len(window(server).panes) == 6


def test_a_window_with_no_room_reports_which_pane_failed(manager, server) -> None:
    server.max_panes = 2
    with pytest.raises(TmuxError, match="no room for pane 3 of 4"):
        manager.apply(TEMP_LAYOUT)


def test_an_invalid_layout_is_rejected_before_tmux_is_touched(manager, server) -> None:
    calls_before = len(server.calls)
    with pytest.raises(LayoutError):
        manager.apply("grid")
    assert [call[1] for call in server.calls[calls_before:]] == []


def test_an_explicit_target_is_used_instead_of_the_current_window(manager, server) -> None:
    server.run(["tmux", "new-window", "-d", "-P", "-F", "#{window_id}",
                "-t", "=work:", "-n", "other", "-c", "/work"])
    other = server.sessions["work"].windows[1]
    manager.apply("tiled", panes=2, target=other.id)
    assert len(other.panes) == 2
    assert len(window(server).panes) == 1


def test_new_panes_open_in_the_requested_directory(manager, server) -> None:
    manager.apply("tiled", panes=2, cwd="/elsewhere")
    assert window(server).panes[1].path == "/elsewhere"


def test_without_a_cwd_tmux_chooses_the_directory(manager, server) -> None:
    # Passing -c "." would pin new panes to tmux_sessionizer's own cwd forever.
    manager.apply("tiled", panes=2)
    splits = [call for call in server.calls if call[1] == "split-window"]
    assert all("-c" not in call for call in splits)


def test_new_panes_in_an_adb_window_inherit_its_serial(manager, server) -> None:
    window(server).options["@adb_serial"] = "emulator-5554"
    manager.apply(TEMP_LAYOUT)
    assert all(p.env == {"ANDROID_SERIAL": "emulator-5554"} for p in window(server).panes[1:])


def test_new_panes_outside_an_adb_window_get_no_serial(manager, server) -> None:
    manager.apply(TEMP_LAYOUT)
    splits = [call for call in server.calls if call[1] == "split-window"]
    assert splits and all("-e" not in call for call in splits)


def test_capture_returns_the_layout_for_pasting_into_a_config(manager, server) -> None:
    manager.apply(TEMP_LAYOUT)
    assert manager.capture() == TEMP_LAYOUT


def test_capture_without_a_window_is_an_error(manager, server) -> None:
    server.current = None
    with pytest.raises(TmuxError, match="could not identify the current window"):
        manager.capture()


def test_running_outside_tmux_refuses_to_guess_a_window(tmux, server) -> None:
    # #{window_id} answers with someone else's window when a server is running,
    # so applying a layout without --target would rearrange it at random.
    manager = LayoutManager(tmux)
    with pytest.raises(TmuxError, match="not running inside tmux"):
        manager.apply("tiled", panes=2)
    with pytest.raises(TmuxError, match="not running inside tmux"):
        manager.capture()
