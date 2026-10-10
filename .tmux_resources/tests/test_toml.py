"""The fallback TOML reader, checked against the standard library.

:mod:`tmux_sessionizer._toml` only runs on Pythons without ``tomllib`` — which is not
the Python this suite runs on. So the tests are *differential*: every input is
parsed by both readers and the results must be identical. That is what stops
the version you develop on and the version in the offline bundle from drifting
apart.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from tmux_sessionizer import _toml, config, discovery

#: The real session files on this machine, if any. They live in the user's home
#: directory, so a fresh checkout simply has none to compare.
SESSIONS = discovery.available({})

VALID = [
    pytest.param("", id="empty"),
    pytest.param("# just a comment\n", id="comment-only"),
    pytest.param("\n\n\n", id="blank-lines"),
    pytest.param('a = "b"', id="no-trailing-newline"),
    pytest.param('[t]\nkey = "value"\n', id="table"),
    pytest.param("[a.b.c]\nx = 1\n", id="nested-table"),
    pytest.param("[[w]]\nn = 1\n[[w]]\nn = 2\n", id="array-of-tables"),
    pytest.param("[[w]]\nn = 1\n  [[w.p]]\n  m = 1\n  [[w.p]]\n  m = 2\n", id="nested-aot"),
    pytest.param("x = []\n", id="empty-array"),
    pytest.param('x = ["a", "b"]\n', id="string-array"),
    pytest.param('x = [\n  "a",\n  "b",\n]\n', id="multiline-array-trailing-comma"),
    pytest.param('x = [ # why\n  "a", # first\n]\n', id="array-with-comments"),
    pytest.param("x = [[1, 2], [3]]\n", id="nested-arrays"),
    pytest.param("x = true\ny = false\n", id="booleans"),
    pytest.param("x = 0\ny = -3\nz = +42\n", id="integers"),
    pytest.param("x = 1_000_000\n", id="integer-underscores"),
    pytest.param("x = 0xdead\ny = 0o17\nz = 0b1011\n", id="integer-bases"),
    pytest.param("x = 1.5\ny = -0.25\nz = 1e3\n", id="floats"),
    pytest.param(r'x = "a\tb\nc\\d\"e"' + "\n", id="escapes"),
    pytest.param(r'x = "é\U0001F600"' + "\n", id="unicode-escapes"),
    pytest.param("x = 'raw \\n not an escape'\n", id="literal-string"),
    pytest.param('x = """\nline one\nline two\n"""\n', id="multiline-basic"),
    pytest.param('x = """a\\\n    b"""\n', id="multiline-line-continuation"),
    pytest.param("x = '''\nraw \\n stays\n'''\n", id="multiline-literal"),
    pytest.param('"quoted key" = 1\n', id="quoted-key"),
    pytest.param("x=1\ny  =  2\n", id="spacing"),
    pytest.param('x = "héllo → 🎉"\n', id="unicode-content"),
    pytest.param('x = "a#b" # trailing\n', id="hash-inside-string"),
    pytest.param('x = "[not a table]"\n', id="bracket-inside-string"),
    pytest.param("[a]\n[a.b]\nx = 1\n", id="parent-then-child"),
]

INVALID = [
    pytest.param("[unclosed\n", id="unclosed-header"),
    pytest.param("x =\n", id="missing-value"),
    pytest.param("= 1\n", id="missing-key"),
    pytest.param('x = "unterminated\n', id="unterminated-string"),
    pytest.param('x = ["a",\n', id="unterminated-array"),
    pytest.param("x = 1\nx = 2\n", id="duplicate-key"),
    pytest.param("[a]\nx = 1\n[a]\ny = 2\n", id="duplicate-table"),
    pytest.param('x = "a" "b"\n', id="trailing-junk"),
    pytest.param("x = nope\n", id="bare-word-value"),
    pytest.param(r'x = "\q"' + "\n", id="bad-escape"),
    pytest.param("[[a]]\n[a]\nx = 1\n", id="array-then-table"),
]


@pytest.mark.parametrize("text", VALID)
def test_the_fallback_agrees_with_tomllib(text: str) -> None:
    assert _toml.loads(text) == tomllib.loads(text)


@pytest.mark.parametrize("text", INVALID)
def test_the_fallback_rejects_what_tomllib_rejects(text: str) -> None:
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(text)
    with pytest.raises(_toml.TOMLDecodeError):
        _toml.loads(text)


@pytest.mark.skipif(not SESSIONS, reason="no session files installed")
@pytest.mark.parametrize("path", SESSIONS or [None], ids=lambda path: getattr(path, "name", "none"))
def test_every_installed_session_file_parses_identically(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert _toml.loads(text) == tomllib.loads(text)


def test_errors_carry_a_line_number() -> None:
    with pytest.raises(_toml.TOMLDecodeError, match="line 3"):
        _toml.loads('a = 1\nb = 2\nc = "unterminated\n')


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("x = {a = 1}\n", "inline tables are not supported"),
        ("a.b = 1\n", "dotted keys are not supported"),
        ("x = 1979-05-27\n", "not a supported value"),
    ],
)
def test_unsupported_toml_is_refused_not_guessed(text: str, message: str) -> None:
    # These are valid TOML the fallback deliberately does not cover. Refusing
    # loudly is safe; parsing them wrongly would not be.
    tomllib.loads(text)
    with pytest.raises(_toml.TOMLDecodeError, match=message):
        _toml.loads(text)


def test_a_byte_order_mark_is_ignored() -> None:
    assert _toml.loads('﻿ x = 1\n') == {"x": 1}


def test_config_reads_through_the_fallback(tmp_path, monkeypatch) -> None:
    """The whole config layer must work when tomllib is not importable."""
    monkeypatch.setattr(config, "tomllib", _toml)
    spec = config.loads(
        f'''
[session]
name = "Fallback"
path = "{tmp_path}"
setup = ["clear"]

[[windows]]
name = "grid"
layout = "tiled"

  [[windows.panes]]
  at = 2
  commands = ["ls"]
  focus = true
'''
    )
    assert spec.name == "Fallback"
    assert spec.setup == ("clear",)
    assert spec.windows[0].panes[0].offset == 1
    assert spec.windows[0].panes[0].focus is True


def test_a_broken_file_through_the_fallback_is_a_config_error(monkeypatch) -> None:
    from tmux_sessionizer.errors import ConfigError

    monkeypatch.setattr(config, "tomllib", _toml)
    with pytest.raises(ConfigError, match="invalid TOML"):
        config.loads("[session\n")
