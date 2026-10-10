"""Thin subprocess wrapper around the `git` binary.

Every other module in this package should go through here instead of calling
subprocess directly, so error handling and output capture stay consistent.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


class GitError(Exception):
    """A `git` invocation exited non-zero."""

    def __init__(self, args: list[str], returncode: int, stderr: str):
        self.args = args
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"git {' '.join(args)} failed ({returncode}): {stderr.strip()}")


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run(
    args: list[str],
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> Result:
    """Run `git <args>`.

    capture=False streams stdout/stderr straight to the terminal (used for
    interactive commands like `git rebase -i` or `git commit`).
    `env` is merged on top of the current environment.
    """
    full_env = {**os.environ, **env} if env else None
    proc = subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env=full_env,
    )
    result = Result(proc.returncode, proc.stdout or "", proc.stderr or "")
    if check and not result.ok:
        raise GitError(args, result.returncode, result.stderr)
    return result


def capture(args: list[str]) -> str:
    """Run git and return stdout, stripped. Raises GitError on failure."""
    return run(args).stdout.strip()


def capture_lines(args: list[str]) -> list[str]:
    out = capture(args)
    return [line for line in out.splitlines() if line]


def try_capture(args: list[str], default: str = "") -> str:
    """Like capture(), but returns `default` instead of raising on failure."""
    result = run(args, check=False)
    return result.stdout.strip() if result.ok else default
