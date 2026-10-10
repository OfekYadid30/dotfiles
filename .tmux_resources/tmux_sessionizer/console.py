"""Terminal output.

Deliberately tiny and injectable: the CLI takes a :class:`Console` so tests can
capture output instead of writing to a real terminal. Everything goes to stderr
so command output proper (a captured layout, a session listing) stays on stdout
and stays pipeable.
"""

from __future__ import annotations

import sys
from typing import IO, Optional

_ANSI = {
    "reset": "\033[0m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "dim": "\033[2m",
}


class Console:
    def __init__(
        self,
        stream: Optional[IO[str]] = None,
        *,
        color: Optional[bool] = None,
        verbose: bool = False,
    ) -> None:
        self.stream = stream if stream is not None else sys.stderr
        self.verbose = verbose
        if color is None:
            color = bool(getattr(self.stream, "isatty", lambda: False)())
        self.color = color

    def _write(self, text: str, style: str = "") -> None:
        if self.color and style:
            text = "{}{}{}".format(_ANSI[style], text, _ANSI["reset"])
        self.stream.write(text + "\n")
        self.stream.flush()

    def info(self, text: str) -> None:
        self._write("    " + text)

    def ok(self, text: str) -> None:
        self._write("  + " + text, "green")

    def warn(self, text: str) -> None:
        self._write("  ! " + text, "yellow")

    def error(self, text: str) -> None:
        self._write("  x " + text, "red")

    def debug(self, text: str) -> None:
        if self.verbose:
            self._write("    $ " + text, "dim")
