"""The session files installed on this machine must stay valid.

A regression guard over the real workspaces: a broken one is otherwise only
discovered when a key binding does nothing. They live in the user's home
directory rather than in this repo, so the whole file skips when there are none
- on a fresh checkout, or in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tmux_sessionizer import config, discovery

INSTALLED = discovery.available({})

pytestmark = pytest.mark.skipif(
    not INSTALLED, reason=f"no session files in {discovery.DEFAULT_DIRS[0]}"
)


@pytest.mark.parametrize("path", INSTALLED, ids=lambda path: path.name)
def test_each_installed_session_file_is_valid(path: Path) -> None:
    # Paths inside point at real directories; only the structure is asserted
    # here so the test does not fail just because a project was moved.
    spec = config.load(path, require_path=False)
    assert spec.name
    assert spec.windows
    for window in spec.windows:
        if window.layout_pane_count:
            assert window.required_panes(1) <= window.layout_pane_count


@pytest.mark.parametrize("path", INSTALLED, ids=lambda path: path.name)
def test_the_filename_matches_the_session_name(path: Path) -> None:
    # `tmux_sessionizer up <name>` lowercases the name to find the file, so a mismatch
    # makes a session unreachable by name.
    spec = config.load(path, require_path=False)
    assert path.name == f"{spec.name.lower()}{config.SUFFIX}"


@pytest.mark.parametrize("path", INSTALLED, ids=lambda path: path.name)
def test_each_session_is_reachable_by_its_own_name(path: Path) -> None:
    spec = config.load(path, require_path=False)
    assert discovery.resolve(spec.name, env={}) == path
