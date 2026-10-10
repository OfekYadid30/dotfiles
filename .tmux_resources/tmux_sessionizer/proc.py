"""Subprocess execution.

Everything that shells out funnels through :class:`Runner`, which is the single
seam the tests replace. Nothing else in the package imports :mod:`subprocess`.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Sequence, Tuple


class CommandError(Exception):
    """A subprocess exited non-zero."""

    def __init__(self, argv: Sequence[str], returncode: int, output: str = "") -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.output = output
        message = "command failed (exit {}): {}".format(returncode, " ".join(self.argv))
        if output.strip():
            message = "{}\n{}".format(message, output.rstrip())
        super().__init__(message)


@dataclass(frozen=True)
class Result:
    argv: Tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def out(self) -> str:
        """Stdout with surrounding whitespace trimmed - the common case."""
        return self.stdout.strip()


class Runner:
    """Runs commands. The real implementation."""

    def __init__(self, console=None) -> None:
        self.console = console

    def run(self, argv: Sequence[str], *, check: bool = True, capture: bool = True) -> Result:
        """Run *argv*.

        ``capture=False`` hands the child our stdio, which matters for exactly
        one command: a tmux client attaching has to own the terminal.
        """
        argv = [str(a) for a in argv]
        if self.console is not None:
            self.console.debug(" ".join(argv))

        proc = subprocess.run(argv, capture_output=capture, text=True)
        result = Result(
            tuple(argv),
            proc.returncode,
            proc.stdout or "" if capture else "",
            proc.stderr or "" if capture else "",
        )
        if check and not result.ok:
            raise CommandError(argv, result.returncode, result.stdout + result.stderr)
        return result

    @staticmethod
    def which(program: str) -> str:
        return shutil.which(program)
