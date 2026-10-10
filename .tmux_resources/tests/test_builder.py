"""Building sessions, against an in-memory tmux server."""

from __future__ import annotations

import pytest

from tmux_sessionizer.builder import SessionBuilder
from tmux_sessionizer.errors import TmuxError
from tmux_sessionizer.spec import PaneSpec, SessionSpec, WindowSpec
from tmux_sessionizer.tmux import PANE_READY_TIMEOUT, Tmux

from .conftest import DEV_LAYOUT, TEMP_LAYOUT
from .faketmux import FakeTmux


def spec(*windows: WindowSpec, name: str = "Demo", setup: tuple[str, ...] = ()) -> SessionSpec:
    return SessionSpec(name=name, path="/work", windows=windows, setup=setup)


def attached_builder(
    server: FakeTmux, *, inside: bool, terminal: tuple[int, int] = (120, 40)
) -> SessionBuilder:
    env = {"TMUX": "/tmp/tmux-501/default,1,0"} if inside else {}
    return SessionBuilder(
        Tmux(runner=server, sleep=lambda _: None, env=env), terminal_size=lambda: terminal
    )


def window_named(server: FakeTmux, name: str):
    return next(w for w in server.sessions["Demo"].windows if w.name == name)


# -- creation -------------------------------------------------------------


def test_first_window_is_renamed_rather_than_added(builder, server) -> None:
    builder.up(spec(WindowSpec("editor")), attach=False)
    windows = server.sessions["Demo"].windows
    assert [w.name for w in windows] == ["editor"]


def test_each_window_paragraph_becomes_a_window(builder, server) -> None:
    builder.up(spec(WindowSpec("a"), WindowSpec("b"), WindowSpec("c")), attach=False)
    assert [w.name for w in server.sessions["Demo"].windows] == ["a", "b", "c"]


def test_duplicate_window_names_are_allowed(builder, server) -> None:
    # The real Home session has three windows called "generic".
    builder.up(spec(WindowSpec("generic"), WindowSpec("generic")), attach=False)
    assert [w.name for w in server.sessions["Demo"].windows] == ["generic", "generic"]


def test_commands_are_typed_into_their_pane_and_submitted(builder, server) -> None:
    builder.up(spec(WindowSpec("editor", panes=(PaneSpec(("nvim .",)),))), attach=False)
    pane = window_named(server, "editor").panes[0]
    assert pane.keys == ["nvim .", "C-m"]


def test_setup_commands_run_in_every_pane_before_pane_commands(builder, server) -> None:
    builder.up(
        spec(
            WindowSpec("grid", layout="tiled", panes=(PaneSpec(("first",)), PaneSpec())),
            setup=("cd /work", "clear"),
        ),
        attach=False,
    )
    panes = window_named(server, "grid").panes
    assert panes[0].commands == ["cd /work", "clear", "first"]
    # A pane the config never names still gets the setup.
    assert panes[1].commands == ["cd /work", "clear"]


def test_a_window_grows_to_the_pane_count_its_layout_needs(builder, server) -> None:
    builder.up(spec(WindowSpec("research", layout=DEV_LAYOUT)), attach=False)
    window = window_named(server, "research")
    assert len(window.panes) == 10
    assert window.layout == DEV_LAYOUT


def test_growing_retiles_between_splits(builder, server) -> None:
    # Without the re-tile, tmux runs out of room part way through a big layout.
    builder.up(spec(WindowSpec("research", layout=DEV_LAYOUT)), attach=False)
    order = [call[1] for call in server.calls if call[1] in ("split-window", "select-layout")]
    assert order[:4] == ["select-layout", "split-window", "select-layout", "split-window"]


def test_addressed_panes_reach_the_right_pane(builder, server) -> None:
    builder.up(
        spec(
            WindowSpec(
                "ori",
                layout=TEMP_LAYOUT,
                panes=(
                    PaneSpec(("nvim",), offset=0),
                    PaneSpec(("ipython",), offset=1),
                    PaneSpec(("ls",), offset=3),
                ),
            )
        ),
        attach=False,
    )
    panes = window_named(server, "ori").panes
    assert [pane.commands for pane in panes] == [["nvim"], ["ipython"], [], ["ls"]]


def test_pane_addresses_follow_the_servers_base_index(tmux, server) -> None:
    server.pane_base_index = 0
    builder = SessionBuilder(tmux, terminal_size=lambda: (120, 40))
    builder.up(
        spec(WindowSpec("w", layout="tiled", panes=(PaneSpec(("third",), offset=2),))),
        attach=False,
    )
    panes = window_named(server, "w").panes
    assert [pane.index for pane in panes] == [0, 1, 2]
    assert panes[2].commands == ["third"]


def test_a_multi_pane_window_without_a_layout_is_tiled(builder, server) -> None:
    builder.up(spec(WindowSpec("w", panes=(PaneSpec(), PaneSpec(), PaneSpec()))), attach=False)
    assert window_named(server, "w").layout == "tiled"


def test_a_single_pane_window_is_left_alone(builder, server) -> None:
    builder.up(spec(WindowSpec("w", panes=(PaneSpec(("ls",)),))), attach=False)
    assert window_named(server, "w").layout == ""
    assert "select-layout" not in [call[1] for call in server.calls]


def test_window_path_overrides_the_session_path(builder, server) -> None:
    builder.up(spec(WindowSpec("a"), WindowSpec("b", path="/elsewhere")), attach=False)
    assert window_named(server, "b").panes[0].path == "/elsewhere"


def test_window_path_applies_to_the_first_window_too(builder, server) -> None:
    # The first window is the one tmux makes with the session, so its directory
    # is fixed at creation time and cannot be set later.
    builder.up(spec(WindowSpec("a", path="/window-one", panes=(PaneSpec(), PaneSpec()))),
               attach=False)
    assert [pane.path for pane in window_named(server, "a").panes] == ["/window-one"] * 2


def test_all_panes_of_a_window_share_its_directory(builder, server) -> None:
    builder.up(spec(WindowSpec("a"), WindowSpec("b", path="/elsewhere",
                                                panes=(PaneSpec(), PaneSpec()))), attach=False)
    assert [pane.path for pane in window_named(server, "b").panes] == ["/elsewhere"] * 2


def test_the_session_is_created_at_the_clients_size(server) -> None:
    server.client_size = (300, 90)
    attached_builder(server, inside=True).up(spec(WindowSpec("a")), attach=False)
    session = server.sessions["Demo"]
    assert (session.width, session.height) == (300, 90)


def test_the_terminal_size_is_used_when_no_client_is_attached(server) -> None:
    server.client_size = None
    attached_builder(server, inside=True, terminal=(111, 41)).up(
        spec(WindowSpec("a")), attach=False
    )
    session = server.sessions["Demo"]
    assert (session.width, session.height) == (111, 41)


def test_the_clients_size_is_ignored_from_outside_tmux(server) -> None:
    # #{client_width} then describes some unrelated terminal, not ours.
    server.client_size = (300, 90)
    attached_builder(server, inside=False, terminal=(111, 41)).up(
        spec(WindowSpec("a")), attach=False
    )
    session = server.sessions["Demo"]
    assert (session.width, session.height) == (111, 41)


# -- focus ----------------------------------------------------------------


def test_the_first_window_is_selected_by_default(builder, server) -> None:
    builder.up(spec(WindowSpec("a"), WindowSpec("b")), attach=False)
    assert server.selected_windows == [server.sessions["Demo"].windows[0].id]


def test_focus_selects_the_marked_window_even_with_duplicate_names(builder, server) -> None:
    builder.up(spec(WindowSpec("dup"), WindowSpec("dup", focus=True)), attach=False)
    assert server.selected_windows == [server.sessions["Demo"].windows[1].id]


def test_focus_selects_the_marked_pane(builder, server) -> None:
    builder.up(
        spec(WindowSpec("w", layout="tiled", panes=(PaneSpec(), PaneSpec(focus=True)))),
        attach=False,
    )
    assert server.selected_panes == [window_named(server, "w").panes[1].id]


# -- readiness ------------------------------------------------------------


def test_commands_wait_for_a_pane_that_is_still_booting(tmux, server, clock) -> None:
    server.boot_captures = 3
    SessionBuilder(tmux, terminal_size=lambda: (120, 40)).up(
        spec(WindowSpec("w", panes=(PaneSpec(("ls",)),))), attach=False
    )
    # The pane was polled while it booted, and the command landed afterwards.
    assert [call for call in server.calls if call[1] == "capture-pane"]
    assert clock.now > 0
    assert window_named(server, "w").panes[0].commands == ["ls"]


def test_a_pane_that_never_draws_does_not_block_the_build(tmux, server, clock) -> None:
    server.boot_captures = 10**6
    builder = SessionBuilder(tmux, terminal_size=lambda: (120, 40))
    builder.up(spec(WindowSpec("w", panes=(PaneSpec(("ls",)),))), attach=False)
    assert clock.now >= PANE_READY_TIMEOUT
    assert window_named(server, "w").panes[0].commands == ["ls"]


def test_a_pane_with_no_commands_is_never_polled(builder, server) -> None:
    builder.up(spec(WindowSpec("w")), attach=False)
    assert [call for call in server.calls if call[1] == "capture-pane"] == []


# -- failure --------------------------------------------------------------


def test_a_failed_build_leaves_no_half_built_session(tmux, server) -> None:
    server.max_panes = 4
    builder = SessionBuilder(tmux, terminal_size=lambda: (120, 40))
    with pytest.raises(TmuxError, match="no room for pane 5"):
        builder.up(spec(WindowSpec("research", layout=DEV_LAYOUT)), attach=False)
    assert server.sessions == {}


def test_a_rejected_layout_is_reported_with_the_window_name(tmux, server) -> None:
    builder = SessionBuilder(tmux, terminal_size=lambda: (120, 40))
    server.fail.add("select-layout")
    with pytest.raises(TmuxError, match="rejected the layout for window 'w'"):
        builder.up(spec(WindowSpec("w", layout="main-vertical", panes=(PaneSpec(),))), attach=False)


def test_a_missing_tmux_is_reported_before_anything_is_created(tmux, server) -> None:
    server.installed = False
    builder = SessionBuilder(tmux, terminal_size=lambda: (120, 40))
    with pytest.raises(TmuxError, match="not installed"):
        builder.up(spec(WindowSpec("a")), attach=False)
    assert server.sessions == {}


# -- existing sessions ----------------------------------------------------


def test_an_existing_session_is_reused_not_rebuilt(builder, server) -> None:
    builder.up(spec(WindowSpec("a"), WindowSpec("b")), attach=False)
    server.sessions["Demo"].windows[0].name = "renamed-by-hand"
    server.sessions["Demo"].windows.pop()

    outcome = builder.up(spec(WindowSpec("a"), WindowSpec("b")), attach=False)
    assert not outcome.created
    # The live session is left exactly as the user left it.
    assert [window.name for window in server.sessions["Demo"].windows] == ["renamed-by-hand"]


def test_outcome_reports_what_happened(builder) -> None:
    outcome = builder.up(spec(WindowSpec("a")), attach=False)
    assert outcome.created and not outcome.attached
    assert "created session 'Demo'" in outcome.summary
    assert "left detached" in outcome.summary


# -- attaching ------------------------------------------------------------


def test_inside_tmux_the_client_is_switched(server) -> None:
    builder = attached_builder(server, inside=True)
    builder.up(spec(WindowSpec("a")))
    assert server.switched == ["Demo"]
    assert server.attached == []


def test_outside_tmux_the_session_is_attached(server) -> None:
    builder = attached_builder(server, inside=False)
    builder.up(spec(WindowSpec("a")))
    assert server.attached == ["Demo"]
    assert server.switched == []


def test_a_switch_that_does_not_take_effect_is_an_error(server) -> None:
    builder = attached_builder(server, inside=True)
    builder.up(spec(WindowSpec("a")), attach=False)
    server.ignore_switch = True
    with pytest.raises(TmuxError, match="did not take effect"):
        builder.attach("Demo")


def test_scratch_sessions_are_pruned_but_named_ones_survive(server) -> None:
    builder = attached_builder(server, inside=True)
    builder.up(spec(WindowSpec("a")), attach=False)
    server.run(["tmux", "new-session", "-d", "-s", "0", "-c", "/", "-x", "80", "-y", "24"])
    server.run(["tmux", "new-session", "-d", "-s", "keepme", "-c", "/", "-x", "80", "-y", "24"])

    builder.attach("Demo")
    assert sorted(server.sessions) == ["Demo", "keepme"]


def test_pruning_can_be_switched_off(server) -> None:
    builder = attached_builder(server, inside=True)
    builder.up(spec(WindowSpec("a")), attach=False)
    server.run(["tmux", "new-session", "-d", "-s", "0", "-c", "/", "-x", "80", "-y", "24"])

    builder.up(spec(WindowSpec("a")), prune_scratch=False)
    assert sorted(server.sessions) == ["0", "Demo"]
