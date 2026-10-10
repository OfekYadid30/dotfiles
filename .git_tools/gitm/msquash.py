"""Condense multiple `fixup!` commits aimed at the same target into one.

Used by mfixupa/mfixup consumers who ended up with several separate
`fixup! X` commits for the same target commit `X` (e.g. after running
`mfixup` more than once against the same commit) and want to collapse those
down to a single `fixup! X` commit -- without touching `X` itself.

This is deliberately not "autosquash": autosquash folds fixups into their
real target. Here we only fold fixups into each other, and leave the result
as its own `fixup!` commit, ready for a later `git mrebase`/autosquash pass.
"""

from __future__ import annotations

import os
import shlex
import tempfile
from dataclasses import dataclass

from .cli import CliError, info
from .gitrun import run
from .refs import Commit, commits_ahead, refuse_merge_commits, upstream_ref

FIXUP_PREFIX = "fixup! "


@dataclass
class FixupGroup:
    target_subject: str
    commits: list[Commit]  # oldest first


def find_multi_fixup_groups(commits_oldest_first: list[Commit]) -> list[FixupGroup]:
    """Group fixup! commits by the subject they target; keep only groups with
    more than one member (a single fixup has nothing to condense)."""
    order: list[str] = []
    groups: dict[str, list[Commit]] = {}
    for commit in commits_oldest_first:
        if not commit.subject.startswith(FIXUP_PREFIX):
            continue
        target_subject = commit.subject[len(FIXUP_PREFIX) :]
        if target_subject not in groups:
            groups[target_subject] = []
            order.append(target_subject)
        groups[target_subject].append(commit)
    return [
        FixupGroup(target_subject=subject, commits=groups[subject])
        for subject in order
        if len(groups[subject]) > 1
    ]


def _build_condensed_todo(commits_oldest_first: list[Commit]) -> list[str]:
    """Rebuild the full oldest-first commit list as a rebase todo, merging
    every extra member of a multi-fixup group into the first ('pick') member
    via a `fixup` line. Every other commit passes through unchanged.
    """
    multi_targets = {
        group.target_subject for group in find_multi_fixup_groups(commits_oldest_first)
    }

    order: list[tuple[str, str]] = []
    blocks: dict[tuple[str, str], list[str]] = {}

    for commit in commits_oldest_first:
        is_group_fixup = commit.subject.startswith(FIXUP_PREFIX) and (
            commit.subject[len(FIXUP_PREFIX) :] in multi_targets
        )
        if is_group_fixup:
            key = ("group", commit.subject[len(FIXUP_PREFIX) :])
            if key in blocks:
                blocks[key].append(f"fixup {commit.sha} {commit.subject}")
                continue
            blocks[key] = [f"pick {commit.sha} {commit.subject}"]
            order.append(key)
        else:
            key = ("single", commit.sha)
            blocks[key] = [f"pick {commit.sha} {commit.subject}"]
            order.append(key)

    return [line for key in order for line in blocks[key]]


def _warn_about_interleaving(commits_oldest_first: list[Commit], groups: list[FixupGroup]) -> None:
    """Condensing a group moves its members next to each other, which
    reorders any unrelated commit that was sitting between them. That's
    usually harmless but can produce a different merge result or a conflict
    that wouldn't otherwise exist, so tell the user which commits move.
    """
    position = {commit.sha: i for i, commit in enumerate(commits_oldest_first)}
    for group in groups:
        indices = sorted(position[c.sha] for c in group.commits)
        span = commits_oldest_first[indices[0] : indices[-1] + 1]
        between = [c for c in span if c.sha not in {m.sha for m in group.commits}]
        if between:
            others = ", ".join(f"{c.short} {c.subject}" for c in between)
            info(
                f"condensing fixups for '{group.target_subject}' will reorder "
                f"{len(between)} commit(s) that sat between them: {others}"
            )


def condense_fixups(branch: str, remote: str = "origin") -> list[FixupGroup]:
    """Collapse every multi-member fixup group ahead of origin/<branch> into
    a single fixup commit each. Returns the groups that were condensed (empty
    if there was nothing to do, in which case no rebase is run at all).
    """
    commits_oldest_first = list(reversed(commits_ahead(branch, remote, exclude_fixups=False)))
    groups = find_multi_fixup_groups(commits_oldest_first)
    if not groups:
        return groups

    refuse_merge_commits(branch, remote)

    _warn_about_interleaving(commits_oldest_first, groups)

    todo_lines = _build_condensed_todo(commits_oldest_first)
    ref = upstream_ref(branch, remote)

    with tempfile.TemporaryDirectory(prefix="gitm-msquash-") as work_dir:
        todo_path = os.path.join(work_dir, "todo")
        with open(todo_path, "w") as f:
            f.write("\n".join(todo_lines) + "\n")

        # `git` invokes GIT_SEQUENCE_EDITOR as `<value> <todo-path>` through
        # the shell, so this just needs to be a shell command that copies our
        # precomputed todo over whatever path git passes it as $1.
        result = run(
            ["rebase", "--interactive", "--autostash", ref],
            check=False,
            capture=False,
            env={"GIT_SEQUENCE_EDITOR": f"cp {shlex.quote(todo_path)}"},
        )

    if not result.ok:
        raise CliError(
            "rebase failed or hit a conflict while condensing fixups; resolve it and run "
            "`git rebase --continue` (or `--abort` to back out)"
        )
    return groups
