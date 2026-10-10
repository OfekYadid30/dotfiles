"""Session file parsing and validation."""

from __future__ import annotations

import pytest

from tmux_sessionizer import config
from tmux_sessionizer.errors import ConfigError

from .conftest import DEV_LAYOUT

MINIMAL = """
[session]
name = "Demo"
path = "{path}"

[[windows]]
name = "editor"
"""


def minimal(tmp_path, extra: str = "") -> str:
    return MINIMAL.format(path=tmp_path) + extra


def test_minimal_file_parses(tmp_path) -> None:
    spec = config.loads(minimal(tmp_path))
    assert spec.name == "Demo"
    assert spec.path == tmp_path
    assert [window.name for window in spec.windows] == ["editor"]
    assert spec.windows[0].panes == ()
    assert spec.setup == ()


def test_window_commands_become_a_single_pane(tmp_path) -> None:
    spec = config.loads(
        minimal(tmp_path).replace('name = "editor"', 'name = "editor"\ncommands = ["nvim .", "ls"]')
    )
    pane = spec.windows[0].panes[0]
    assert pane.commands == ("nvim .", "ls")
    assert pane.offset is None


def test_a_bare_string_is_accepted_as_one_command(tmp_path) -> None:
    spec = config.loads(
        minimal(tmp_path).replace('name = "editor"', 'name = "editor"\ncommands = "nvim"')
    )
    assert spec.windows[0].panes[0].commands == ("nvim",)


def test_blank_commands_are_dropped(tmp_path) -> None:
    # A blank entry would otherwise send a bare Enter into the pane.
    spec = config.loads(
        minimal(tmp_path).replace('name = "editor"', 'name = "editor"\ncommands = ["ls", "  ", ""]')
    )
    assert spec.windows[0].panes[0].commands == ("ls",)


def test_a_window_with_only_blank_commands_gets_no_panes(tmp_path) -> None:
    spec = config.loads(
        minimal(tmp_path).replace('name = "editor"', 'name = "editor"\ncommands = ["", " "]')
    )
    assert spec.windows[0].panes == ()


def test_setup_commands_are_kept_in_order(tmp_path) -> None:
    spec = config.loads(minimal(tmp_path).replace('path = "', 'setup = ["a", "b"]\npath = "', 1))
    assert spec.setup == ("a", "b")


def test_setup_accepts_a_bare_string(tmp_path) -> None:
    spec = config.loads(minimal(tmp_path).replace('path = "', 'setup = "clear"\npath = "', 1))
    assert spec.setup == ("clear",)


def test_positional_panes_keep_their_order(tmp_path) -> None:
    spec = config.loads(
        minimal(tmp_path)
        + """
  [[windows.panes]]
  commands = ["one"]
  [[windows.panes]]
  commands = ["two"]
"""
    )
    window = spec.windows[0]
    assert [pane.commands for pane in window.panes] == [("one",), ("two",)]
    assert window.resolve_panes(1) == {1: window.panes[0], 2: window.panes[1]}


def test_at_addresses_panes_independently_of_the_base_index(tmp_path) -> None:
    spec = config.loads(
        minimal(tmp_path)
        + """
  [[windows.panes]]
  at = 1
  commands = ["first"]
  [[windows.panes]]
  at = 4
  commands = ["fourth"]
"""
    )
    window = spec.windows[0]
    assert sorted(window.resolve_panes(1)) == [1, 4]
    assert sorted(window.resolve_panes(0)) == [0, 3]
    assert window.required_panes(1) == 4


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("[[windows]]\nname = 'x'", "missing [session]"),
        ("[session]\npath = '/tmp'\n[[windows]]\nname='x'", "[session].name"),
        ("[session]\nname = 'x'\n[[windows]]\nname='x'", "[session].path"),
        ("[session]\nname = 'a b'\npath = '/tmp'\n[[windows]]\nname='x'", "whitespace"),
        ("[session]\nname = 'a:b'\npath = '/tmp'\n[[windows]]\nname='x'", "whitespace"),
        ("[session]\nname = 'a.b'\npath = '/tmp'\n[[windows]]\nname='x'", "whitespace"),
        ("[session]\nname = 'x'\npath = '/tmp'", "at least one [[windows]]"),
        ("windows = []\n[session]\nname = 'x'\npath = '/tmp'", "at least one [[windows]]"),
        ("[session]\nname = 'x'\npath = '/tmp'\n[[windows]]", "windows[0].name: is required"),
        ("[session]\nname = 'x'\npath = '/tmp'\n[[windows]]\nname = ''", "must not be empty"),
        ("[session]\nname = 'x'\npath = '/tmp'\n[[windows]]\nname = 3", "must be a string"),
    ],
)
def test_structural_errors(body: str, message: str) -> None:
    with pytest.raises(ConfigError) as excinfo:
        config.loads(body, require_path=False)
    assert message in str(excinfo.value)


def test_unknown_keys_are_errors_not_silent_typos(tmp_path) -> None:
    with pytest.raises(ConfigError, match="unknown key.*'sertup'"):
        config.loads(minimal(tmp_path).replace("path =", "sertup = []\npath =", 1))

    with pytest.raises(ConfigError, match="unknown key.*'comands'"):
        config.loads(minimal(tmp_path).replace('name = "editor"', 'name = "editor"\ncomands = []'))

    with pytest.raises(ConfigError, match="unknown key.*'cmd'"):
        config.loads(minimal(tmp_path) + "\n  [[windows.panes]]\n  cmd = []\n")

    with pytest.raises(ConfigError, match="unknown key.*'sessions'"):
        config.loads("sessions = 1\n" + minimal(tmp_path))


def test_the_allowed_keys_are_listed_when_one_is_wrong(tmp_path) -> None:
    with pytest.raises(ConfigError, match="allowed: name, path, setup"):
        config.loads(minimal(tmp_path).replace("path =", "nmae = 'x'\npath =", 1))


def test_commands_and_panes_are_mutually_exclusive(tmp_path) -> None:
    with pytest.raises(ConfigError, match="not both"):
        config.loads(
            minimal(tmp_path)
            + """
commands = ["a"]
  [[windows.panes]]
  commands = ["b"]
"""
        )


def test_mixing_positional_and_addressed_panes_is_rejected(tmp_path) -> None:
    with pytest.raises(ConfigError, match="every pane sets 'at' or none"):
        config.loads(
            minimal(tmp_path)
            + """
  [[windows.panes]]
  commands = ["a"]
  [[windows.panes]]
  at = 3
  commands = ["b"]
"""
        )


def test_duplicate_pane_positions_are_rejected(tmp_path) -> None:
    with pytest.raises(ConfigError, match=r"duplicate pane position\(s\): \[2\]"):
        config.loads(
            minimal(tmp_path)
            + """
  [[windows.panes]]
  at = 2
  [[windows.panes]]
  at = 2
"""
        )


@pytest.mark.parametrize("value", [0, -1, "2", 1.5, True])
def test_at_must_be_a_positive_integer(tmp_path, value) -> None:
    rendered = "true" if value is True else repr(value)
    with pytest.raises(ConfigError, match="'at' must be an integer"):
        config.loads(minimal(tmp_path) + f"\n  [[windows.panes]]\n  at = {rendered}\n")


def test_panes_must_be_a_non_empty_list_of_tables(tmp_path) -> None:
    with pytest.raises(ConfigError, match="non-empty list"):
        config.loads(minimal(tmp_path).replace('name = "editor"', 'name = "editor"\npanes = []'))
    with pytest.raises(ConfigError, match="each pane must be a table"):
        config.loads(minimal(tmp_path).replace('name = "editor"', 'name = "editor"\npanes = ["ls"]'))


def test_commands_must_be_strings(tmp_path) -> None:
    with pytest.raises(ConfigError, match="must be a list of strings"):
        config.loads(minimal(tmp_path).replace('name = "editor"', 'name = "editor"\ncommands = [1]'))


def test_layout_must_be_a_real_layout(tmp_path) -> None:
    with pytest.raises(ConfigError, match="neither a builtin name"):
        config.loads(
            minimal(tmp_path).replace('name = "editor"', 'name = "editor"\nlayout = "grid"')
        )


def test_a_corrupted_layout_is_caught_at_parse_time(tmp_path) -> None:
    broken = DEV_LAYOUT.replace("224x53", "224x54", 1)
    with pytest.raises(ConfigError, match="checksum"):
        config.loads(minimal(tmp_path).replace('name = "editor"', f'name = "editor"\nlayout = "{broken}"'))


def test_config_cannot_drive_more_panes_than_the_layout_has(tmp_path) -> None:
    body = minimal(tmp_path).replace('name = "editor"', f'name = "editor"\nlayout = "{DEV_LAYOUT}"')
    with pytest.raises(ConfigError, match="defines 10 panes but the config drives 11"):
        config.loads(body + "\n  [[windows.panes]]\n  at = 11\n")


def test_layout_pane_count_is_a_ceiling_not_a_requirement(tmp_path) -> None:
    body = minimal(tmp_path).replace('name = "editor"', f'name = "editor"\nlayout = "{DEV_LAYOUT}"')
    spec = config.loads(body + "\n  [[windows.panes]]\n  at = 6\n  commands = ['ipython']\n")
    assert spec.windows[0].required_panes(1) == 10


def test_only_one_window_and_one_pane_may_take_focus(tmp_path) -> None:
    with pytest.raises(ConfigError, match="only one window"):
        config.loads(minimal(tmp_path) + "focus = true\n\n[[windows]]\nname='b'\nfocus = true\n")

    with pytest.raises(ConfigError, match="only one pane"):
        config.loads(
            minimal(tmp_path)
            + "\n  [[windows.panes]]\n  focus = true\n  [[windows.panes]]\n  focus = true\n"
        )


def test_focus_must_be_a_boolean(tmp_path) -> None:
    with pytest.raises(ConfigError, match="must be true or false"):
        config.loads(minimal(tmp_path) + "focus = 'yes'\n")


def test_focus_selects_the_window_position(tmp_path) -> None:
    spec = config.loads(minimal(tmp_path) + "\n[[windows]]\nname = 'second'\nfocus = true\n")
    assert spec.focus_index == 1
    assert config.loads(minimal(tmp_path)).focus_index == 0


def test_duplicate_window_names_are_allowed(tmp_path) -> None:
    # The real Home workspace has three windows called "generic".
    spec = config.loads(minimal(tmp_path) + "\n[[windows]]\nname = 'editor'\n")
    assert [window.name for window in spec.windows] == ["editor", "editor"]


def test_missing_session_path_is_reported(tmp_path) -> None:
    body = minimal(tmp_path).replace(str(tmp_path), str(tmp_path / "nope"))
    with pytest.raises(ConfigError, match="session path does not exist"):
        config.loads(body)
    # ...and can be skipped when validating a config for another machine.
    assert config.loads(body, require_path=False).name == "Demo"


def test_a_file_is_not_a_valid_session_path(tmp_path) -> None:
    target = tmp_path / "afile"
    target.write_text("")
    body = minimal(tmp_path).replace(str(tmp_path), str(target))
    with pytest.raises(ConfigError, match="session path does not exist"):
        config.loads(body)


def test_window_path_overrides_the_session_path(tmp_path) -> None:
    other = tmp_path / "sub"
    other.mkdir()
    spec = config.loads(
        minimal(tmp_path).replace('name = "editor"', f'name = "editor"\npath = "{other}"')
    )
    assert spec.windows[0].path == other


def test_a_missing_window_path_is_reported(tmp_path) -> None:
    with pytest.raises(ConfigError, match="window path does not exist"):
        config.loads(
            minimal(tmp_path).replace('name = "editor"', 'name = "editor"\npath = "/no/such/dir"')
        )


def test_paths_expand_home_and_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DEMO_ROOT", str(tmp_path))
    assert config.expand_path("$DEMO_ROOT/x") == tmp_path / "x"
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config.expand_path("~") == tmp_path


def test_invalid_toml_is_reported_as_a_config_error() -> None:
    with pytest.raises(ConfigError, match="invalid TOML"):
        config.loads("[session\nname = 1")


def test_errors_point_at_the_offending_window_line(tmp_path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        config.loads(
            minimal(tmp_path) + "\n[[windows]]\nname = 'broken'\nlayout = 'grid'\n",
            source="demo.tmux.toml",
        )
    # The second [[windows]] header; the exact line makes the message actionable.
    assert "demo.tmux.toml:9" in str(excinfo.value)


def test_load_rejects_the_wrong_suffix(tmp_path) -> None:
    path = tmp_path / "demo.toml"
    path.write_text(minimal(tmp_path))
    with pytest.raises(ConfigError, match="must end with .tmux.toml"):
        config.load(path)


def test_load_reports_a_missing_file(tmp_path) -> None:
    with pytest.raises(ConfigError, match="cannot read session file"):
        config.load(tmp_path / "gone.tmux.toml")


def test_load_reads_a_real_file(tmp_path) -> None:
    path = tmp_path / "demo.tmux.toml"
    path.write_text(minimal(tmp_path))
    spec = config.load(path)
    assert spec.source == path
