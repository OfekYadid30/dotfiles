"""Error types for tmux_sessionizer.

Anything derived from :class:`TmuxSessionizerError` is an *expected* failure and is
printed by the CLI as a one-line message; anything else escapes with a
traceback, because it is a bug in this package.
"""

from __future__ import annotations

from pathlib import Path


class TmuxSessionizerError(Exception):
    """Base class for expected, user-facing failures."""


class TmuxError(TmuxSessionizerError):
    """A tmux invocation failed, or tmux is unusable."""


class LayoutError(TmuxSessionizerError):
    """A layout descriptor is malformed or does not fit the window."""


class ConfigError(TmuxSessionizerError):
    """A session file is invalid.

    Carries enough location for the message to point at the offending line the
    way a compiler would: ``sessions/dev.toml:12: windows[1]: ...``.
    """

    def __init__(
        self,
        message: str,
        *,
        source: Path | str | None = None,
        line: int | None = None,
        where: str | None = None,
        got: object | None = None,
    ) -> None:
        self.message = message
        self.source = Path(source) if source is not None else None
        self.line = line
        self.where = where
        self.got = got
        super().__init__(self.render())

    def render(self) -> str:
        # No source means the error is not about a file's contents (a lookup
        # that found nothing, say), so a "<config>:" prefix would be noise.
        parts = []
        if self.source is not None:
            location = str(self.source)
            if self.line is not None:
                location = f"{location}:{self.line}"
            parts.append(location)
        if self.where:
            parts.append(self.where)
        text = ": ".join(parts + [self.message])
        if self.got is not None:
            text = f"{text} (got: {self.got!r})"
        return text
