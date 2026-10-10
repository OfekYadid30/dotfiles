"""Fixup-commit + autosquash-rebase primitives shared by mfixup and mfixupa.

Two building blocks:
  - commit_fixup_with_retry(): `git commit --fixup <target>`, tolerant of a
    pre-commit hook that reformats the file and fails the first attempt.
  - autosquash_rebase(): one non-interactive `rebase -i --autosquash` onto
    the default branch, folding every pending `fixup!` commit into place.

mfixup uses both for a single commit; mfixupa creates several fixup
commits (one per file) and then calls autosquash_rebase() once at the end.
"""

from __future__ import annotations

from .cli import CliError, info
from .gitrun import capture_lines, run
from .refs import refuse_merge_commits, upstream_ref

MAX_HOOK_RETRIES = 3


def staged_paths() -> list[str]:
    """Currently staged file paths (empty list if nothing is staged)."""
    return capture_lines(["diff", "--cached", "--name-only"])


def require_staged_paths() -> list[str]:
    """staged_paths(), raising CliError if nothing is staged.

    Shared by `git mfixup` (which needs the list up front, to build its
    picker header, and to fail fast before even opening the picker) and
    commit_fixup_with_retry below (which needs it to scope hook retries) --
    one place owns the "nothing is staged" message so the two can't drift.
    """
    paths = staged_paths()
    if not paths:
        raise CliError("nothing is staged; `git add` your changes first")
    return paths


def commit_fixup_with_retry(target_sha: str, *, retries: int = MAX_HOOK_RETRIES) -> None:
    """Run `git commit --fixup <target_sha>` against whatever is currently
    staged.

    A pre-commit hook is allowed to fail the first attempt as long as it left
    behind working-tree changes to *the files that were already staged*
    (e.g. it reformatted one of them). When that happens we re-stage just
    those files and retry, up to `retries` times, since the second attempt is
    usually the one that passes.

    Re-staging is deliberately scoped to the originally-staged paths rather
    than `git add --update` over the whole working tree: a hook retry must
    never sweep in unrelated changes that happened to be sitting unstaged
    elsewhere in the repo (e.g. mfixupa's next file, not yet processed).
    """
    paths = require_staged_paths()

    for attempt in range(1, retries + 1):
        result = run(["commit", "--fixup", target_sha], check=False, capture=False)
        if result.ok:
            return

        changed = capture_lines(["diff", "--name-only", "--", *paths])
        if not changed:
            raise CliError(
                f"`git commit --fixup {target_sha}` failed and left no working-tree "
                "changes to retry with; see the hook output above"
            )

        info(
            f"commit hook failed but modified {', '.join(changed)} "
            f"(attempt {attempt}/{retries}) — re-staging and retrying"
        )
        run(["add", "--update", "--", *paths])

    raise CliError(
        f"`git commit --fixup {target_sha}` kept failing after {retries} attempts "
        "even with hook-modified changes re-staged; fix the hook failure manually"
    )


def autosquash_rebase(branch: str, remote: str = "origin") -> None:
    """Non-interactively rebase HEAD onto origin/<branch>, autosquashing any
    pending `fixup!`/`squash!` commits into their targets.

    Rebasing directly onto the upstream ref (instead of counting commits with
    HEAD~N) means only commits already ahead of the default branch ever move,
    and it stays correct no matter how many fixups were queued up.
    """
    refuse_merge_commits(branch, remote)

    ref = upstream_ref(branch, remote)
    result = run(
        ["rebase", "--interactive", "--autosquash", "--autostash", ref],
        check=False,
        capture=False,
        env={"GIT_SEQUENCE_EDITOR": ":"},
    )
    if not result.ok:
        raise CliError(
            "autosquash rebase failed or hit a conflict; resolve it and run "
            "`git rebase --continue` (or `--abort` to back out)"
        )
