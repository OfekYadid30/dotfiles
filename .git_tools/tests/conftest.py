"""Shared fixtures for the gitm test suite.

Every test in this package runs against real, throwaway git repositories
created under pytest's `tmp_path`. Nothing here ever touches the real
`~/.gitconfig` or any repo outside of `tmp_path`: HOME is redirected to a
fake per-test directory and git's global/system config files are disabled
outright (see `isolated_git_env` below), and every repo gets its own local
`user.name`/`user.email` so commits work without any of that.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Same pattern the bin/git-* scripts use: make the repo root (the parent of
# this tests/ directory) importable so `import gitm...` works regardless of
# where pytest is invoked from.
REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def isolated_git_env(tmp_path, monkeypatch):
    """Isolate every git invocation from the real user's environment.

    Applies to both in-process gitm.* calls (which shell out via
    subprocess.run(env=os.environ) unless told otherwise) and out-of-process
    bin/git-* subprocess runs that inherit os.environ.
    """
    fake_home = tmp_path / "_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in (
        "GIT_AUTHOR_NAME",
        "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME",
        "GIT_COMMITTER_EMAIL",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_CEILING_DIRECTORIES",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


def run_git(cwd, *args, check=True, input=None, env=None):
    full_env = {**os.environ, **(env or {})}
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        input=input,
        env=full_env,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} (cwd={cwd}) failed [{proc.returncode}]:\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    return proc


def configure_repo(path):
    run_git(path, "config", "user.name", "Test User")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "commit.gpgsign", "false")
    run_git(path, "config", "tag.gpgsign", "false")


def write_and_commit(path, name, content, message):
    (Path(path) / name).write_text(content)
    run_git(path, "add", "--", name)
    run_git(path, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A cloned repo (`work`) pointing at a real `origin` remote.

    origin has a single "master" branch with one commit -- "master" because
    that's gitm's hardcoded default (see gitm.refs.default_branch), so tests
    that don't pass --branch/an explicit branch exercise the real default
    path instead of an override. `work` is a clone of it, so `origin/master`
    is already set up exactly the way a real checkout would have it. The
    test's cwd is chdir'd into `work`, since gitm.* functions operate on the
    current-directory repo.

    Returns a SimpleNamespace with:
      - origin: Path to the bare-ish origin repo
      - path:   Path to the clone (also the cwd during the test)
      - run:    run_git bound to `path`
      - commit: write_and_commit bound to `path`
    """
    origin = tmp_path / "origin.git"
    origin.mkdir()
    run_git(origin, "init", "-q", "-b", "master")
    configure_repo(origin)
    write_and_commit(origin, "README.md", "hello\n", "initial commit")

    work = tmp_path / "work"
    run_git(tmp_path, "clone", "-q", str(origin), str(work))
    configure_repo(work)

    monkeypatch.chdir(work)

    return SimpleNamespace(
        origin=origin,
        path=work,
        run=lambda *a, **kw: run_git(work, *a, **kw),
        commit=lambda name, content, message: write_and_commit(work, name, content, message),
    )


def install_hook(repo_path, name, script_body):
    """Write an executable hook script (e.g. name='pre-commit') into a repo."""
    hooks_dir = Path(repo_path) / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    hook_path = hooks_dir / name
    hook_path.write_text(script_body)
    hook_path.chmod(0o755)
    return hook_path


def no_fzf_path(tmp_path):
    """A PATH value with `git`/`python3` reachable but `fzf` deliberately not.

    Used to force gitm.picker's fallback numbered-stdin prompt in e2e tests,
    since the machine running this suite may have fzf installed and its
    interactive TUI can't be driven from a plain subprocess test.
    """
    import shutil

    fake_bin = tmp_path / "_fakebin"
    fake_bin.mkdir(exist_ok=True)
    for tool in ("git", "python3"):
        found = shutil.which(tool)
        if found:
            link = fake_bin / tool
            if not link.exists():
                os.symlink(found, link)
    return str(fake_bin)


def run_bin(name, args, cwd, check=False, input=None, env=None):
    """Run one of the bin/git-* scripts as a subprocess against `cwd`."""
    full_env = {**os.environ, **(env or {})}
    proc = subprocess.run(
        [sys.executable, str(BIN_DIR / name), *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        input=input,
        env=full_env,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"{name} {' '.join(args)} (cwd={cwd}) failed [{proc.returncode}]:\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
    return proc
