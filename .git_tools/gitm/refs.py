"""Branch resolution and commit-range helpers shared by mlog/mfixup/mfixupa.

The one concept every m* command needs is: "what is the mainline branch, and
which commits on HEAD are ahead of it". That logic lives here, once.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cli import CliError
from .gitrun import GitError, capture_lines, try_capture

DEFAULT_BRANCH_FALLBACK = "master"


def current_branch() -> str:
    branch = try_capture(["symbolic-ref", "--short", "-q", "HEAD"])
    if not branch:
        raise CliError("HEAD is detached; check out a branch first")
    return branch


def default_branch(explicit: str | None = None, remote: str = "origin") -> str:
    """Resolve the mainline branch name.

    Resolution order:
      1. an explicit branch passed on the command line (--branch)
      2. `git config gitm.default-branch` (set this per-repo if it isn't "master")
      3. "master"

    Deliberately not auto-detected (e.g. via origin/HEAD): every command
    always means "master" unless told otherwise, which is simpler and more
    predictable than probing the remote.
    """
    if explicit:
        return explicit

    configured = try_capture(["config", "--get", "gitm.default-branch"])
    if configured:
        return configured

    return DEFAULT_BRANCH_FALLBACK


def upstream_ref(branch: str, remote: str = "origin") -> str:
    """The ref to compare HEAD against: `<remote>/<branch>` if it exists,
    else the local `<branch>` (e.g. no remote configured yet, working
    offline, or origin/<branch> just hasn't been fetched)."""
    remote_ref = f"{remote}/{branch}"
    if try_capture(["rev-parse", "--verify", "-q", remote_ref]):
        return remote_ref

    if try_capture(["rev-parse", "--verify", "-q", branch]):
        return branch

    raise CliError(
        f"neither '{remote_ref}' nor local '{branch}' exists "
        "(fetch it, or pass a different branch)"
    )


def has_merge_commits(branch: str, remote: str = "origin") -> bool:
    """True if HEAD has any merge commit ahead of origin/<branch>."""
    ref = upstream_ref(branch, remote)
    return bool(_git_log(["--merges", f"{ref}..HEAD"]))


def refuse_merge_commits(branch: str, remote: str = "origin") -> None:
    """Raise CliError if HEAD has any merge commit ahead of origin/<branch>.

    Plain `git rebase -i` linearizes history and silently drops merge
    commits (and any conflict-resolution content that lives only in them).
    Shared by autosquash_rebase (fixup.py) and condense_fixups (msquash.py)
    -- both do exactly this kind of rebase, so both refuse via this one
    check+message instead of two copies that could drift apart.
    """
    if has_merge_commits(branch, remote):
        raise CliError(
            f"there's a merge commit ahead of {remote}/{branch}; a plain interactive "
            "rebase would silently flatten it, so refusing rather than rewriting history wrong"
        )


_FIXUP_PREFIXES = ("fixup! ", "squash! ", "amend! ")


@dataclass
class Commit:
    sha: str
    subject: str

    @property
    def short(self) -> str:
        return self.sha[:9]

    @property
    def is_fixup(self) -> bool:
        """True for commits git itself treats as autosquash material
        (fixup!/squash!/amend!). These are never useful fixup *targets*."""
        return self.subject.startswith(_FIXUP_PREFIXES)

    def display(self) -> str:
        return f"{self.short} {self.subject}"


def _git_log(args: list[str]) -> list[str]:
    """`git log --oneline --no-decorate <args>`, with GitError turned into
    the CliError shape every command's error handling expects."""
    try:
        return capture_lines(["log", "--oneline", "--no-decorate", *args])
    except GitError as exc:
        raise CliError(str(exc)) from exc


def _parse_oneline(lines: list[str], exclude_fixups: bool) -> list[Commit]:
    commits = []
    for line in lines:
        sha, _, subject = line.partition(" ")
        commit = Commit(sha=sha, subject=subject)
        if exclude_fixups and commit.is_fixup:
            continue
        commits.append(commit)
    return commits


def _path_args(paths: list[str] | None) -> list[str]:
    if not paths:
        return []
    args = ["--follow"] if len(paths) == 1 else []
    return [*args, "--", *paths]


def commits_ahead(
    branch: str,
    remote: str = "origin",
    paths: list[str] | None = None,
    exclude_fixups: bool = True,
) -> list[Commit]:
    """Commits reachable from HEAD but not from origin/<branch>, newest first.

    If `paths` is given, only commits touching those paths are returned
    (rename-aware via --follow when a single path is given). Pending
    fixup!/squash!/amend! commits are excluded by default, since these
    functions exist to pick fixup *targets* and a fixup can't target another
    fixup.
    """
    ref = upstream_ref(branch, remote)
    lines = _git_log([f"{ref}..HEAD", *_path_args(paths)])
    return _parse_oneline(lines, exclude_fixups)


def all_commits(paths: list[str] | None = None, exclude_fixups: bool = True) -> list[Commit]:
    """Every commit reachable from HEAD, newest first (used as a fallback when
    a file predates the branch's divergence from the default branch)."""
    lines = _git_log(_path_args(paths))
    return _parse_oneline(lines, exclude_fixups)
