"""The tmux client seam: argument shapes, output parsing, error translation."""

from __future__ import annotations

import pytest
from tmux_sessionizer.errors import TmuxError
from tmux_sessionizer.tmux import (
    PANE_READY_POLL,
    PANE_READY_TIMEOUT,
    PANE_SETTLE,
    Pane,
    Tmux,
    Window,
)

from .faketmux import FakeTmux


@pytest.fixture
def populated(server: FakeTmux) -> FakeTmux:
    server.run(["tmux", "new-session", "-d", "-s", "work", "-c", "/work", "-x", "200", "-y", "50"])
    server.current = "work"
    return server


def test_sessions_are_matched_exactly_not_by_prefix(populated, tmux) -> None:
    # tmux prefix-matches a bare target, so without "=" a session called "work"
    # would be found by the name "wo" - and later switched to by mistake.
    assert tmux.has_session("work") is True
    assert tmux.has_session("wo") is False
    assert tmux.has_session("workshop") is False


def test_a_missing_session_is_false_not_an_error(tmux) -> None:
    assert tmux.has_session("ghost") is False


def test_windows_and_panes_are_parsed_into_records(populated, tmux) -> None:
    window = tmux.list_windows("=work:")[0]
    assert isinstance(window, Window) and window.name == "bash"

    pane = tmux.list_panes(window.id)[0]
    assert isinstance(pane, Pane) and pane.index == 1


def test_the_pane_base_index_is_read_from_the_window(populated, tmux) -> None:
    assert tmux.pane_base_index(tmux.list_windows("=work:")[0].id) == 1
    populated.pane_base_index = 0
    populated.run(["tmux", "new-session", "-d", "-s", "zero", "-c", "/", "-x", "80", "-y", "24"])
    assert tmux.pane_base_index(tmux.list_windows("=zero:")[0].id) == 0


def test_a_window_without_panes_is_an_error_not_a_crash(populated, tmux) -> None:
    window = tmux.list_windows("=work:")[0]
    populated.sessions["work"].windows[0].panes.clear()
    with pytest.raises(TmuxError, match="reports no panes"):
        tmux.pane_base_index(window.id)


def test_client_size_is_parsed_and_missing_clients_report_none(populated, tmux) -> None:
    populated.client_size = (300, 90)
    assert tmux.client_size() == (300, 90)
    populated.client_size = None
    assert tmux.client_size() is None


@pytest.mark.parametrize("size", [(0, 0), (200, 0)])
def test_a_nonsense_client_size_is_treated_as_no_client(populated, tmux, size) -> None:
    populated.client_size = size
    assert tmux.client_size() is None


def test_attaching_lets_the_client_own_the_terminal(populated, tmux) -> None:
    # With stdout on a pipe, a real tmux client either hangs showing nothing or
    # exits with "open terminal failed: not a terminal".
    tmux.attach_session("work")
    call, kwargs = populated.invocations[-1]
    assert call[1] == "attach-session"
    assert kwargs.get("capture") is False


def test_every_other_command_is_captured(populated, tmux) -> None:
    tmux.list_panes(tmux.list_windows("=work:")[0].id)
    assert populated.invocations[-1][1].get("capture") is not False


def test_a_named_server_is_addressed_with_dash_L(server, clock) -> None:
    tmux = Tmux(runner=server, sleep=clock.sleep, monotonic=clock.monotonic,
                env={"TMUX_SESSIONIZER_SOCKET": "scratch"})
    tmux.has_session("nope")
    assert server.calls[-1][:3] == ["tmux", "-L", "scratch"]


def test_send_line_types_literally_then_presses_enter(populated, tmux) -> None:
    pane = tmux.list_panes(tmux.list_windows("=work:")[0].id)[0]
    tmux.send_line(pane.id, "echo C-c")

    sends = [call for call in populated.calls if call[1] == "send-keys"]
    # -l -- keeps "C-c" as text rather than a key name.
    assert sends[0][-3:] == ["-l", "--", "echo C-c"]
    assert sends[1][-1] == "C-m"


def test_wait_until_ready_waits_out_a_booting_shell(populated, tmux, clock) -> None:
    populated.sessions["work"].windows[0].panes[0].boot_captures = 2
    pane = tmux.list_panes(tmux.list_windows("=work:")[0].id)[0]

    assert tmux.wait_until_ready(pane.id) is True
    # Two empty polls, then a full settle window of unchanged output.
    assert clock.now >= 2 * PANE_READY_POLL + PANE_SETTLE


def test_wait_until_ready_keeps_waiting_while_the_prompt_is_still_drawing(
    populated, tmux, clock
) -> None:
    # Non-empty is not enough: a shell that draws its prompt in stages will
    # echo keys twice if they land mid-draw.
    populated.sessions["work"].windows[0].panes[0].redraw_captures = 3
    pane = tmux.list_panes(tmux.list_windows("=work:")[0].id)[0]

    assert tmux.wait_until_ready(pane.id) is True
    # The settle window restarts on every change, so all three redraws are waited out.
    assert clock.now >= 3 * PANE_READY_POLL + PANE_SETTLE


def test_wait_until_ready_settles_immediately_on_a_quiet_pane(populated, tmux, clock) -> None:
    pane = tmux.list_panes(tmux.list_windows("=work:")[0].id)[0]
    assert tmux.wait_until_ready(pane.id) is True
    assert clock.now == pytest.approx(PANE_SETTLE)


def test_wait_until_ready_gives_up_rather_than_hanging(populated, tmux, clock) -> None:
    populated.sessions["work"].windows[0].panes[0].boot_captures = 10**6
    pane = tmux.list_panes(tmux.list_windows("=work:")[0].id)[0]

    assert tmux.wait_until_ready(pane.id) is False
    assert clock.now >= PANE_READY_TIMEOUT


def test_a_failing_tmux_command_becomes_a_tmux_error(populated, tmux) -> None:
    populated.fail.add("rename-window")
    window = tmux.list_windows("=work:")[0]
    with pytest.raises(TmuxError):
        tmux.rename_window(window.id, "nope")


def test_commands_whose_failure_is_meaningful_return_false(populated, tmux) -> None:
    populated.fail.add("select-layout")
    assert tmux.select_layout(tmux.list_windows("=work:")[0].id, "tiled") is False


def test_inside_tmux_reads_the_environment(server) -> None:
    assert Tmux(runner=server, env={}).inside_tmux is False
    assert Tmux(runner=server, env={"TMUX": "/tmp/sock,1,0"}).inside_tmux is True


def test_require_available_checks_the_binary(server) -> None:
    Tmux(runner=server, env={}).require_available()
    server.installed = False
    with pytest.raises(TmuxError, match="not installed"):
        Tmux(runner=server, env={}).require_available()
