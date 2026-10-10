"""End-to-end through the command line, with a fake tmux underneath."""

from __future__ import annotations

import io

import pytest
from tmux_sessionizer.console import Console

from tmux_sessionizer import cli, discovery

from .conftest import TEMP_LAYOUT
from .faketmux import FakeTmux


@pytest.fixture
def out():
    return Console(io.StringIO(), color=False)


@pytest.fixture(autouse=True)
def outside_tmux(monkeypatch):
    """The CLI reads $TMUX to decide switch-vs-attach; tests must not inherit it."""
    monkeypatch.delenv("TMUX", raising=False)


@pytest.fixture
def inside_tmux(monkeypatch):
    monkeypatch.setenv("TMUX", "/private/tmp/tmux-501/default,3626,1")


@pytest.fixture
def sessions(tmp_path, monkeypatch):
    directory = tmp_path / "sessions"
    directory.mkdir()
    (directory / "demo.tmux.toml").write_text(
        f"""
[session]
name = "Demo"
path = "{tmp_path}"
setup = ["clear"]

[[windows]]
name = "editor"
commands = ["nvim ."]

[[windows]]
name = "grid"
layout = "{TEMP_LAYOUT}"

  [[windows.panes]]
  at = 4
  commands = ["btop"]
"""
    )
    monkeypatch.setenv(discovery.ENV_VAR, str(directory))
    return directory


def text(out: Console) -> str:
    return out.stream.getvalue()


def test_check_validates_every_file_on_the_search_path(sessions, out) -> None:
    assert cli.main(["check"], console=out) == 0
    assert "'Demo' - 2 window(s)" in text(out)


def test_check_reports_a_broken_file_and_fails(sessions, out) -> None:
    (sessions / "broken.tmux.toml").write_text("[session]\nname = 'x'\n")
    assert cli.main(["check"], console=out) == 1
    assert "[session].path" in text(out)


def test_check_can_skip_the_path_check(sessions, out, tmp_path) -> None:
    (sessions / "elsewhere.tmux.toml").write_text(
        "[session]\nname='Elsewhere'\npath='/nowhere/at/all'\n[[windows]]\nname='w'\n"
    )
    assert cli.main(["check"], console=out) == 1
    assert cli.main(["check", "--no-path-check"], console=out) == 0


def test_check_accepts_named_sessions(sessions, out) -> None:
    assert cli.main(["check", "demo"], console=out) == 0
    assert cli.main(["check", "nope"], console=out) == 1
    assert "no session named 'nope'" in text(out)


def test_list_prints_names_and_paths(sessions, out, capsys) -> None:
    assert cli.main(["list"], console=out) == 0
    assert "demo" in capsys.readouterr().out


def test_list_without_any_files_fails(monkeypatch, tmp_path, out) -> None:
    monkeypatch.setenv(discovery.ENV_VAR, str(tmp_path / "empty"))
    assert cli.main(["list"], console=out) == 1


def test_session_builds_the_session(sessions, out) -> None:
    server = FakeTmux()
    assert cli.main(["session", "demo", "--no-attach"], console=out, runner=server) == 0

    session = server.sessions["Demo"]
    assert [window.name for window in session.windows] == ["editor", "grid"]
    assert session.windows[0].panes[0].commands == ["clear", "nvim ."]
    assert len(session.windows[1].panes) == 4
    assert session.windows[1].panes[3].commands == ["clear", "btop"]
    assert "created session 'Demo'" in text(out)


def test_session_attaches_an_existing_session_without_rebuilding(sessions, out) -> None:
    server = FakeTmux()
    cli.main(["session", "demo", "--no-attach"], console=out, runner=server)
    server.sessions["Demo"].windows[0].name = "renamed-by-hand"

    assert cli.main(["session", "demo"], console=out, runner=server) == 0
    assert server.attached == ["Demo"]
    assert server.sessions["Demo"].windows[0].name == "renamed-by-hand"


def test_session_prunes_scratch_sessions_unless_told_not_to(sessions, out) -> None:
    server = FakeTmux()
    server.run(["tmux", "new-session", "-d", "-s", "0", "-c", "/", "-x", "80", "-y", "24"])
    cli.main(["session", "demo"], console=out, runner=server)
    assert sorted(server.sessions) == ["Demo"]

    server.run(["tmux", "new-session", "-d", "-s", "1", "-c", "/", "-x", "80", "-y", "24"])
    cli.main(["session", "demo", "--keep-scratch"], console=out, runner=server)
    assert sorted(server.sessions) == ["1", "Demo"]


def test_session_reports_an_unknown_session_without_a_traceback(sessions, out) -> None:
    assert cli.main(["session", "ghost"], console=out, runner=FakeTmux()) == 1
    assert "no session named 'ghost'" in text(out)


def test_layout_applies_to_the_current_window(out, inside_tmux) -> None:
    server = FakeTmux()
    server.run(["tmux", "new-session", "-d", "-s", "w", "-c", "/", "-x", "200", "-y", "50"])
    server.current = "w"

    assert cli.main(["layout", TEMP_LAYOUT], console=out, runner=server) == 0
    assert len(server.sessions["w"].windows[0].panes) == 4


def test_layout_reports_a_bad_layout_as_a_clean_failure(out) -> None:
    assert cli.main(["layout", "grid"], console=out, runner=FakeTmux()) == 1
    assert "neither a builtin name" in text(out)


def test_layout_outside_tmux_refuses_rather_than_picking_a_window(out) -> None:
    assert cli.main(["layout", "tiled", "-n", "2"], console=out, runner=FakeTmux()) == 1
    assert "not running inside tmux" in text(out)


def test_layout_capture_prints_the_current_layout(out, capsys, inside_tmux) -> None:
    server = FakeTmux()
    server.run(["tmux", "new-session", "-d", "-s", "w", "-c", "/", "-x", "200", "-y", "50"])
    server.current = "w"
    cli.main(["layout", TEMP_LAYOUT], console=out, runner=server)
    capsys.readouterr()

    assert cli.main(["layout_capture"], console=out, runner=server) == 0
    assert capsys.readouterr().out.strip() == TEMP_LAYOUT


def test_a_missing_tmux_is_a_clean_failure(sessions, out) -> None:
    assert cli.main(["session", "demo"], console=out, runner=FakeTmux(installed=False)) == 1
    assert "not installed" in text(out)


def test_version_is_reported(capsys) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert "tmux_sessionizer" in capsys.readouterr().out
