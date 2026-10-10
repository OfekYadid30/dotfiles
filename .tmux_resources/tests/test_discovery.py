"""Turning a CLI argument into a session file."""

from __future__ import annotations

import os

import pytest

from tmux_sessionizer import discovery
from tmux_sessionizer.errors import ConfigError


@pytest.fixture
def sessions(tmp_path):
    directory = tmp_path / "sessions"
    directory.mkdir()
    for name in ("home", "development"):
        (directory / f"{name}.tmux.toml").write_text("")
    return directory


def env_for(*directories) -> dict[str, str]:
    return {discovery.ENV_VAR: os.pathsep.join(str(d) for d in directories)}


def test_a_bare_name_is_looked_up_on_the_search_path(sessions) -> None:
    assert discovery.resolve("home", env=env_for(sessions)) == sessions / "home.tmux.toml"


def test_lookup_is_case_insensitive_like_the_session_names(sessions) -> None:
    # Session names are capitalised ("Development"); filenames are not.
    assert discovery.resolve("Development", env=env_for(sessions)).name == "development.tmux.toml"


def test_earlier_directories_shadow_later_ones(tmp_path, sessions) -> None:
    override = tmp_path / "local"
    override.mkdir()
    (override / "home.tmux.toml").write_text("")
    assert discovery.resolve("home", env=env_for(override, sessions)).parent == override


def test_an_explicit_path_is_used_verbatim(tmp_path, sessions) -> None:
    path = sessions / "home.tmux.toml"
    assert discovery.resolve(str(path), env={}) == path


def test_a_path_that_does_not_exist_is_reported(tmp_path) -> None:
    with pytest.raises(ConfigError, match="session file not found"):
        discovery.resolve(str(tmp_path / "missing.tmux.toml"), env={})


def test_an_unknown_name_lists_where_it_looked(sessions) -> None:
    with pytest.raises(ConfigError) as excinfo:
        discovery.resolve("nope", env=env_for(sessions))
    assert "no session named 'nope'" in str(excinfo.value)
    assert str(sessions / "nope.tmux.toml") in str(excinfo.value)


def test_available_lists_every_file_once(tmp_path, sessions) -> None:
    override = tmp_path / "local"
    override.mkdir()
    (override / "home.tmux.toml").write_text("")
    found = discovery.available(env_for(override, sessions))
    assert [path.name for path in found] == ["home.tmux.toml", "development.tmux.toml"]
    # The shadowed copy is not listed twice.
    assert found[0].parent == override


def test_available_skips_directories_that_do_not_exist(tmp_path, sessions) -> None:
    found = discovery.available(env_for(tmp_path / "gone", sessions))
    assert sorted(path.name for path in found) == ["development.tmux.toml", "home.tmux.toml"]


def test_a_capitalised_filename_is_still_found(tmp_path) -> None:
    # Session names are capitalised; the lookup lowercases. On a case-sensitive
    # filesystem that would miss a file named after the session itself.
    directory = tmp_path / "s"
    directory.mkdir()
    actual = directory / "Development.tmux.toml"
    actual.write_text("")
    found = discovery.resolve("Development", env=env_for(directory))
    assert found.is_file() and os.path.samefile(found, actual)


def test_the_default_search_path_is_used_when_unset() -> None:
    assert discovery.search_path({}) == list(discovery.DEFAULT_DIRS)


def test_a_directory_of_the_same_name_does_not_shadow_the_lookup(tmp_path, sessions, monkeypatch) -> None:
    # `tmux_sessionizer up development` next to a ./development/ directory must still
    # find the session file rather than trying to read the directory.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "development").mkdir()
    assert discovery.resolve("development", env=env_for(sessions)).name == "development.tmux.toml"
