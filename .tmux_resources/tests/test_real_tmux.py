"""End-to-end against a real tmux server.

The rest of the suite runs against ``FakeTmux``, which is a model of tmux and
therefore agrees with the code by construction. These tests are the check on
that model: they drive a real tmux binary and assert on what it actually did.

Everything runs on its own server (``tmux -L tmux-sessionizer-test``) so the user's live
sessions are never touched, and the socket is killed afterwards.

    python3 -m pytest -m 'not slow'    # to skip them
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from tmux_sessionizer.proc import Runner

from tmux_sessionizer import config
from tmux_sessionizer.builder import SessionBuilder
from tmux_sessionizer.errors import TmuxError
from tmux_sessionizer.manager import LayoutManager
from tmux_sessionizer.tmux import ENV_SOCKET, Tmux

from .conftest import DEV_LAYOUT, TEMP_LAYOUT

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed"),
]

SOCKET = "tmux-sessionizer-test"


@pytest.fixture
def tmux() -> Tmux:
    client = Tmux(runner=Runner(), env={ENV_SOCKET: SOCKET})
    client._run("kill-server", check=False)
    yield client
    client._run("kill-server", check=False)


@pytest.fixture
def builder(tmux: Tmux) -> SessionBuilder:
    return SessionBuilder(tmux, terminal_size=lambda: (224, 60))


def session_file(tmp_path: Path, body: str) -> Path:
    # Not str.format: layout strings are full of braces.
    path = tmp_path / "demo.tmux.toml"
    path.write_text(body.replace("{path}", str(tmp_path)))
    return path


def panes(tmux: Tmux, target: str):
    return tmux.list_panes(target)


def geometry(layout: str) -> str:
    """A layout with its checksum and pane ids stripped.

    Pane ids are assigned by the server, so only the geometry can be compared
    between a recorded layout and the window built from it.
    """
    return re.sub(r"(\d+x\d+,\d+,\d+),\d+", r"\1", layout.split(",", 1)[1])


def test_a_ten_pane_layout_is_reproduced_exactly(builder, tmux, tmp_path) -> None:
    spec = config.load(
        session_file(
            tmp_path,
            f'''
[session]
name = "e2e"
path = "{{path}}"

[[windows]]
name = "research"
layout = "{DEV_LAYOUT}"

  [[windows.panes]]
  at = 6
  commands = ["true # pane-six"]
''',
        )
    )
    builder.up(spec, attach=False, prune_scratch=False)

    window = tmux.list_windows("=e2e:")[0]
    assert len(panes(tmux, window.id)) == 10
    # Geometry must match the recorded layout; only tmux's pane ids differ.
    assert geometry(tmux.window_layout(window.id)) == geometry(DEV_LAYOUT)


def test_at_addresses_the_pane_the_user_means(builder, tmux, tmp_path) -> None:
    # tmux renumbers panes by position when a layout is applied, so this only
    # holds because the builder re-reads the pane list after select-layout.
    spec = config.load(
        session_file(
            tmp_path,
            f'''
[session]
name = "e2e"
path = "{{path}}"

[[windows]]
name = "grid"
layout = "{TEMP_LAYOUT}"

  [[windows.panes]]
  at = 1
  commands = ["PANE=one"]
  [[windows.panes]]
  at = 4
  commands = ["PANE=four"]
''',
        )
    )
    builder.up(spec, attach=False, prune_scratch=False)
    window = tmux.list_windows("=e2e:")[0]

    seen = {pane.index: tmux.capture_pane(pane.id) for pane in panes(tmux, window.id)}
    assert "PANE=one" in seen[1]
    assert "PANE=four" in seen[4]
    assert "PANE=" not in seen[2] and "PANE=" not in seen[3]


def test_a_failed_build_leaves_nothing_behind(tmux, tmp_path) -> None:
    # A 20x8 window fits about five panes; the half-built session must not survive.
    builder = SessionBuilder(tmux, terminal_size=lambda: (20, 8))
    spec = config.load(
        session_file(
            tmp_path,
            f'''
[session]
name = "e2e"
path = "{{path}}"

[[windows]]
name = "research"
layout = "{DEV_LAYOUT}"
''',
        )
    )
    with pytest.raises(TmuxError, match="no room for pane"):
        builder.up(spec, attach=False, prune_scratch=False)
    assert tmux.has_session("e2e") is False


def test_an_existing_session_is_left_alone(builder, tmux, tmp_path) -> None:
    spec = config.load(
        session_file(
            tmp_path,
            '''
[session]
name = "e2e"
path = "{path}"

[[windows]]
name = "one"
''',
        )
    )
    builder.up(spec, attach=False, prune_scratch=False)
    tmux.rename_window(tmux.list_windows("=e2e:")[0].id, "touched-by-hand")

    builder.up(spec, attach=False, prune_scratch=False)
    assert [window.name for window in tmux.list_windows("=e2e:")] == ["touched-by-hand"]


def test_session_names_are_matched_exactly(builder, tmux, tmp_path) -> None:
    for name in ("work", "workshop"):
        spec = config.load(
            session_file(
                tmp_path,
                f'''
[session]
name = "{name}"
path = "{{path}}"

[[windows]]
name = "w"
''',
            )
        )
        builder.up(spec, attach=False, prune_scratch=False)

    # A bare "-t work" would prefix-match; tmux_sessionizer sends "=work".
    assert tmux.has_session("work") and tmux.has_session("workshop")
    assert sorted(tmux.list_sessions()) == ["work", "workshop"]


def test_the_layout_command_grows_and_applies(tmux) -> None:
    tmux.new_session("layouts", "/tmp", 224, 60)
    window = tmux.list_windows("=layouts:")[0]
    result = LayoutManager(tmux).apply(TEMP_LAYOUT, target=window.id)

    assert (result.panes_before, result.panes_after) == (1, 4)
    assert geometry(tmux.window_layout(window.id)) == geometry(TEMP_LAYOUT)


def test_the_layout_command_refuses_to_close_panes(tmux) -> None:
    tmux.new_session("layouts", "/tmp", 224, 60)
    window = tmux.list_windows("=layouts:")[0]
    manager = LayoutManager(tmux)
    manager.apply("tiled", panes=6, target=window.id)

    with pytest.raises(TmuxError, match="has 6 panes but the layout wants 4"):
        manager.apply(TEMP_LAYOUT, target=window.id)
    assert len(panes(tmux, window.id)) == 6


def test_capture_round_trips_through_a_session_file(builder, tmux, tmp_path) -> None:
    tmux.new_session("captured", "/tmp", 224, 60)
    window = tmux.list_windows("=captured:")[0]
    LayoutManager(tmux).apply("tiled", panes=5, target=window.id)
    captured = LayoutManager(tmux).capture(window.id)

    spec = config.load(
        session_file(
            tmp_path,
            f'''
[session]
name = "e2e"
path = "{{path}}"

[[windows]]
name = "restored"
layout = "{captured}"
''',
        )
    )
    builder.up(spec, attach=False, prune_scratch=False)
    restored = tmux.list_windows("=e2e:")[0]
    assert len(panes(tmux, restored.id)) == 5
    assert geometry(tmux.window_layout(restored.id)) == geometry(captured)


@pytest.mark.parametrize("base", ["0", "1"])
def test_panes_are_addressed_under_either_base_index(builder, tmux, tmp_path, base) -> None:
    # A tmux server only stays up while it has a session, so the option has to
    # be set on a live one; the builder's session then inherits it.
    tmux.new_session("holder", "/tmp", 80, 24)
    tmux._run("set-option", "-g", "pane-base-index", base)
    spec = config.load(
        session_file(
            tmp_path,
            '''
[session]
name = "e2e"
path = "{path}"

[[windows]]
name = "grid"
layout = "tiled"

  [[windows.panes]]
  at = 1
  commands = ["PANE=first"]
  [[windows.panes]]
  at = 3
  commands = ["PANE=third"]
''',
        )
    )
    builder.up(spec, attach=False, prune_scratch=False)
    window = tmux.list_windows("=e2e:")[0]

    found = sorted(panes(tmux, window.id), key=lambda pane: pane.index)
    assert len(found) == 3
    assert found[0].index == int(base)
    assert "PANE=first" in tmux.capture_pane(found[0].id)
    assert "PANE=third" in tmux.capture_pane(found[2].id)
    assert "PANE=" not in tmux.capture_pane(found[1].id)
