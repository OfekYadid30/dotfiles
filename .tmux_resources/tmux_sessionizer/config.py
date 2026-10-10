"""Session files: TOML text in, validated :class:`~tmux_sessionizer.spec.SessionSpec` out.

TOML rather than YAML because it needs no third-party parser: ``tomllib`` is in
the standard library from Python 3.11, and :mod:`tmux_sessionizer._toml` covers the
subset session files use on older Pythons. Either way there is nothing to
install.

The format, in full::

    [session]
    name = "Development"          # required, tmux session name
    path = "~/Development"        # required, default cwd for every window
    setup = ["source .venv/bin/activate"]   # optional, run in *every* pane

    [[windows]]
    name = "editor"               # required
    commands = ["nvim ."]         # optional shorthand for a single-pane window

    [[windows]]
    name = "research"
    layout = "3fcb,224x53,0,0[...]"   # optional: builtin name or #{window_layout}
    path = "~/research"           # optional, overrides session.path
    focus = true                  # optional, window selected on attach

      [[windows.panes]]           # optional; mutually exclusive with commands
      commands = ["ipython"]
      [[windows.panes]]
      at = 6                      # optional, 1-based pane position in the window
      commands = ["btop"]
      focus = true                # optional, pane selected within the window

Panes are positional by default: the first block is the first pane. A window
with sparse interesting panes can use ``at`` instead - either every pane block
carries it or none do. ``at`` counts from 1 regardless of the server's
``pane-base-index``, so a config is portable between machines.

Validation is strict on purpose: unknown keys are errors, because a silently
ignored typo in a dotfile is a bad afternoon.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on old Pythons
    from . import _toml as tomllib

from . import layout as layout_mod
from .errors import ConfigError, LayoutError
from .spec import PaneSpec, SessionSpec, WindowSpec

#: The file suffix session files must use, so a stray TOML is never built.
SUFFIX = ".tmux.toml"

_SESSION_KEYS = {"name", "path", "setup"}
_WINDOW_KEYS = {"name", "layout", "path", "commands", "panes", "focus"}
_PANE_KEYS = {"at", "commands", "focus"}
_TOP_KEYS = {"session", "windows"}

#: tmux uses ``:`` and ``.`` as target separators, so they cannot appear in a name.
_BAD_NAME = re.compile(r"[:.\s]")

_WINDOW_HEADER = re.compile(r"^\s*\[\[\s*windows\s*\]\]")


def expand_path(raw: str) -> Path:
    """``~`` and ``$VAR`` expansion, kept in one place so every path behaves alike."""
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def load(path: Path | str, *, require_path: bool = True) -> SessionSpec:
    """Read and validate a session file."""
    source = Path(path)
    if source.suffix and not source.name.endswith(SUFFIX):
        raise ConfigError(f"session files must end with {SUFFIX}", source=source)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read session file: {exc.strerror or exc}", source=source) from exc
    return loads(text, source=source, require_path=require_path)


def loads(text: str, *, source: Path | str | None = None, require_path: bool = True) -> SessionSpec:
    """Validate session file *text*. Split out from :func:`load` so tests need no files."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML: {exc}", source=source) from exc
    if not isinstance(data, dict):  # pragma: no cover - both readers return a table
        raise ConfigError("session file must be a table", source=source)
    return _build_spec(data, text=text, source=source, require_path=require_path)


def _build_spec(
    data: dict[str, Any],
    *,
    text: str = "",
    source: Path | str | None,
    require_path: bool,
) -> SessionSpec:
    _reject_unknown(data, _TOP_KEYS, where="top level", source=source)

    session = data.get("session")
    if not isinstance(session, dict):
        raise ConfigError("missing [session] table", source=source)
    _reject_unknown(session, _SESSION_KEYS, where="[session]", source=source)

    name = _string(session.get("name"), where="[session].name", source=source, required=True)
    if _BAD_NAME.search(name):
        raise ConfigError(
            "session name cannot contain whitespace, '.' or ':'",
            source=source,
            where="[session].name",
            got=name,
        )

    raw_path = _string(session.get("path"), where="[session].path", source=source, required=True)
    path = expand_path(raw_path)
    if require_path and not path.is_dir():
        raise ConfigError(
            f"session path does not exist: {path}", source=source, where="[session].path"
        )

    setup = _commands(session.get("setup"), where="[session].setup", source=source)

    raw_windows = data.get("windows")
    if not isinstance(raw_windows, list) or not raw_windows:
        raise ConfigError("at least one [[windows]] table is required", source=source)

    lines = _window_header_lines(text, len(raw_windows))
    windows = tuple(
        _window(entry, index=index, source=source, line=lines[index], require_path=require_path)
        for index, entry in enumerate(raw_windows)
    )

    # Duplicate window names are deliberately allowed: tmux permits them, and
    # several windows called "shell" is a reasonable thing to want.
    if sum(1 for window in windows if window.focus) > 1:
        raise ConfigError("only one window may set focus = true", source=source)

    return SessionSpec(
        name=name,
        path=path,
        windows=windows,
        setup=setup,
        source=Path(source) if source is not None else None,
    )


def _window(
    entry: Any,
    *,
    index: int,
    source: Path | str | None,
    line: int | None,
    require_path: bool,
) -> WindowSpec:
    where = f"windows[{index}]"
    if not isinstance(entry, dict):
        raise ConfigError("each window must be a table", source=source, where=where, got=entry)
    _reject_unknown(entry, _WINDOW_KEYS, where=where, source=source, line=line)

    name = _string(entry.get("name"), where=f"{where}.name", source=source, required=True, line=line)
    where = f"windows[{index}] ({name})"

    raw_layout = entry.get("layout")
    layout: str | None = None
    if raw_layout is not None:
        candidate = _string(raw_layout, where=f"{where}.layout", source=source, line=line)
        try:
            layout = layout_mod.validate(candidate)
        except LayoutError as exc:
            raise ConfigError(str(exc), source=source, where=f"{where}.layout", line=line) from exc

    path: Path | None = None
    if entry.get("path") is not None:
        raw = _string(entry["path"], where=f"{where}.path", source=source, line=line)
        path = expand_path(raw)
        if require_path and not path.is_dir():
            raise ConfigError(
                f"window path does not exist: {path}",
                source=source,
                where=f"{where}.path",
                line=line,
            )

    if "commands" in entry and "panes" in entry:
        raise ConfigError(
            "use either 'commands' (single pane) or [[windows.panes]], not both",
            source=source,
            where=where,
            line=line,
        )

    if "panes" in entry:
        panes = _panes(entry["panes"], where=where, source=source, line=line)
    elif "commands" in entry:
        commands = _commands(entry["commands"], where=f"{where}.commands", source=source, line=line)
        panes = (PaneSpec(commands=commands),) if commands else ()
    else:
        panes = ()

    window = WindowSpec(
        name=name,
        layout=layout,
        panes=panes,
        path=path,
        focus=_flag(entry.get("focus"), where=f"{where}.focus", source=source, line=line),
    )

    if window.layout_pane_count:
        highest = window.required_panes(1)
        if highest > window.layout_pane_count:
            raise ConfigError(
                f"layout defines {window.layout_pane_count} panes but the config drives {highest}",
                source=source,
                where=where,
                line=line,
            )
    return window


def _panes(
    raw: Any, *, where: str, source: Path | str | None, line: int | None
) -> tuple[PaneSpec, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError(
            "panes must be a non-empty list of [[windows.panes]] tables",
            source=source,
            where=where,
            line=line,
        )

    panes: list[PaneSpec] = []
    positions: list[int | None] = []
    for position, entry in enumerate(raw):
        pane_where = f"{where}.panes[{position}]"
        if not isinstance(entry, dict):
            raise ConfigError("each pane must be a table", source=source, where=pane_where, got=entry)
        _reject_unknown(entry, _PANE_KEYS, where=pane_where, source=source, line=line)

        at = entry.get("at")
        if at is not None:
            if not isinstance(at, int) or isinstance(at, bool) or at < 1:
                raise ConfigError(
                    "'at' must be an integer >= 1 (1 is the window's first pane)",
                    source=source,
                    where=f"{pane_where}.at",
                    line=line,
                    got=at,
                )
        positions.append(at)
        panes.append(
            PaneSpec(
                commands=_commands(
                    entry.get("commands"), where=f"{pane_where}.commands", source=source, line=line
                ),
                offset=None if at is None else at - 1,
                focus=_flag(entry.get("focus"), where=f"{pane_where}.focus", source=source, line=line),
            )
        )

    explicit = [value for value in positions if value is not None]
    if explicit and len(explicit) != len(positions):
        raise ConfigError(
            "either every pane sets 'at' or none do; mixing positional and explicit "
            "panes makes the order ambiguous",
            source=source,
            where=where,
            line=line,
        )
    if len(set(explicit)) != len(explicit):
        duplicate = sorted({value for value in explicit if explicit.count(value) > 1})
        raise ConfigError(
            f"duplicate pane position(s): {duplicate}", source=source, where=where, line=line
        )
    if sum(1 for pane in panes if pane.focus) > 1:
        raise ConfigError(
            "only one pane per window may set focus = true", source=source, where=where, line=line
        )
    return tuple(panes)


def _string(
    value: Any,
    *,
    where: str,
    source: Path | str | None,
    required: bool = False,
    line: int | None = None,
) -> str:
    if value is None:
        if required:
            raise ConfigError("is required", source=source, where=where, line=line)
        return ""
    if not isinstance(value, str):
        raise ConfigError("must be a string", source=source, where=where, line=line, got=value)
    text = value.strip()
    if required and not text:
        raise ConfigError("must not be empty", source=source, where=where, line=line)
    return text


def _commands(
    value: Any, *, where: str, source: Path | str | None, line: int | None = None
) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError("must be a list of strings", source=source, where=where, line=line, got=value)
    # Blank entries would send a bare Enter to the pane; drop them quietly.
    return tuple(item for item in (line_.strip() for line_ in value) if item)


def _flag(value: Any, *, where: str, source: Path | str | None, line: int | None = None) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ConfigError("must be true or false", source=source, where=where, line=line, got=value)
    return value


def _reject_unknown(
    table: dict[str, Any],
    allowed: set[str],
    *,
    where: str,
    source: Path | str | None,
    line: int | None = None,
) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(
            f"unknown key(s) {', '.join(repr(key) for key in unknown)}; "
            f"allowed: {', '.join(sorted(allowed))}",
            source=source,
            where=where,
            line=line,
        )


def _window_header_lines(text: str, count: int) -> list[int | None]:
    """Best-effort line number for each ``[[windows]]`` header.

    tomllib discards positions, so errors would otherwise point only at the file.
    Falls back to ``None`` whenever the count does not line up (inline arrays,
    unusual formatting), and no message depends on it being present.
    """
    found = [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if _WINDOW_HEADER.match(line)
    ]
    if len(found) != count:
        return [None] * count
    return list(found)
