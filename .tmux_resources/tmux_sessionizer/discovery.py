"""Finding session files by name.

``tmux_sessionizer up development`` should work from anywhere, so a bare name is looked
up in a search path instead of being treated as a filename. Directories are
tried in order and the first hit wins.

Session files are personal configuration, so they live in the user's home
directory - not beside this package. Nothing here knows or cares where the code
is installed.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import SUFFIX
from .errors import ConfigError

#: Overrides the search path; ``:``-separated, like ``$PATH``.
ENV_VAR = "TMUX_SESSIONIZER_SESSIONS"

#: Where session files live when the environment says nothing.
DEFAULT_DIRS = (Path.home() / ".tmux_resources",)


def search_path(env: dict[str, str] | None = None) -> list[Path]:
    env = os.environ if env is None else env
    raw = env.get(ENV_VAR, "")
    if raw:
        return [Path(part).expanduser() for part in raw.split(os.pathsep) if part]
    return list(DEFAULT_DIRS)


def resolve(name: str, *, env: dict[str, str] | None = None) -> Path:
    """Turn a CLI argument into a session file path.

    Anything that looks like a path (contains a separator, ends in the session
    suffix, or names an existing *file*) is used as-is; a bare name is searched
    for. Directories deliberately do not count: ``tmux_sessionizer up development`` must
    keep working when run next to a ``development/`` directory.
    """
    candidate = Path(name).expanduser()
    if os.sep in name or name.endswith(SUFFIX) or candidate.is_file():
        if not candidate.is_file():
            raise ConfigError(f"session file not found: {candidate}")
        return candidate

    # Session names are capitalised ("Development") but filenames are not, so
    # the lookup is case-insensitive in both directions.
    tried = []
    wanted = f"{name.lower()}{SUFFIX}"
    for directory in search_path(env):
        path = directory / wanted
        if path.is_file():
            return path
        tried.append(str(path))
        if directory.is_dir():
            for candidate in sorted(directory.glob(f"*{SUFFIX}")):
                if candidate.name.lower() == wanted:
                    return candidate
    raise ConfigError(f"no session named {name!r}; looked in:\n  " + "\n  ".join(tried))


def available(env: dict[str, str] | None = None) -> list[Path]:
    """Every session file on the search path, first-wins by name."""
    seen: dict[str, Path] = {}
    for directory in search_path(env):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob(f"*{SUFFIX}")):
            seen.setdefault(path.name, path)
    return list(seen.values())
