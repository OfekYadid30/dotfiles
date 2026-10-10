"""Tests for gitm.fixup.commit_fixup_with_retry (the pre-commit-hook-retry path)."""

from __future__ import annotations

import pytest

from gitm.cli import CliError
from gitm.fixup import autosquash_rebase, commit_fixup_with_retry

from conftest import install_hook

_RETRY_ONCE_HOOK = """\
#!/usr/bin/env python3
import pathlib, sys

marker = pathlib.Path(".git/hook-attempt")
target = pathlib.Path("staged.txt")
if marker.exists():
    marker.unlink()
    sys.exit(0)
marker.touch()
target.write_text(target.read_text() + "reformatted-by-hook\\n")
sys.exit(1)
"""

_ALWAYS_FAIL_BUT_MODIFIES_HOOK = """\
#!/usr/bin/env python3
import pathlib, sys

target = pathlib.Path("staged.txt")
target.write_text(target.read_text() + "reformatted-by-hook\\n")
sys.exit(1)
"""

_FAIL_NO_MODIFY_HOOK = """\
#!/usr/bin/env python3
import sys
print("nope", file=sys.stderr)
sys.exit(1)
"""


def _target_sha(repo):
    repo.commit("base.txt", "base\n", "add base")
    return repo.run("rev-parse", "HEAD").stdout.strip()


def test_commit_fixup_with_retry_simple_success(repo):
    target = _target_sha(repo)

    repo.commit("other.txt", "other\n", "add other")  # unrelated, just advances history
    (repo.path / "staged.txt").write_text("v1\n")
    repo.run("add", "staged.txt")

    commit_fixup_with_retry(target)

    subject = repo.run("log", "-1", "--format=%s").stdout.strip()
    assert subject == "fixup! add base"
    content = (repo.path / "staged.txt").read_text()
    assert content == "v1\n"


def test_commit_fixup_with_retry_retries_after_hook_reformats(repo):
    target = _target_sha(repo)
    install_hook(repo.path, "pre-commit", _RETRY_ONCE_HOOK)

    (repo.path / "staged.txt").write_text("v1\n")
    repo.run("add", "staged.txt")

    commit_fixup_with_retry(target)

    subject = repo.run("log", "-1", "--format=%s").stdout.strip()
    assert subject == "fixup! add base"
    # The hook's reformat should have made it into the final commit.
    content = (repo.path / "staged.txt").read_text()
    assert content == "v1\nreformatted-by-hook\n"
    # No leftover unstaged changes.
    assert repo.run("status", "--porcelain").stdout.strip() == ""


def test_commit_fixup_with_retry_gives_up_after_max_retries(repo):
    target = _target_sha(repo)
    install_hook(repo.path, "pre-commit", _ALWAYS_FAIL_BUT_MODIFIES_HOOK)

    (repo.path / "staged.txt").write_text("v1\n")
    repo.run("add", "staged.txt")

    with pytest.raises(CliError, match="kept failing"):
        commit_fixup_with_retry(target, retries=2)

    # No commit should have been created.
    subject = repo.run("log", "-1", "--format=%s").stdout.strip()
    assert subject == "add base"


def test_autosquash_rebase_refuses_merge_commits(repo):
    # Regression: a plain `rebase -i` silently flattens/drops merge commits;
    # autosquash_rebase must refuse instead of quietly rewriting history wrong.
    repo.run("checkout", "-q", "-b", "feature")
    repo.commit("a.txt", "a\n", "add a")
    repo.run("checkout", "-q", "-b", "side", "master")
    repo.commit("b.txt", "b\n", "add b")
    repo.run("checkout", "-q", "feature")
    repo.run("merge", "-q", "--no-edit", "side")

    before = repo.run("rev-parse", "HEAD").stdout.strip()
    with pytest.raises(CliError, match="merge commit"):
        autosquash_rebase("master")
    after = repo.run("rev-parse", "HEAD").stdout.strip()
    assert before == after


def test_commit_fixup_with_retry_does_not_sweep_in_unrelated_unstaged_changes(repo):
    # Regression: the retry used to `git add --update` the whole working
    # tree, which could fold an unrelated file's pre-existing unstaged edit
    # into this fixup commit.
    target = _target_sha(repo)
    repo.commit("unrelated.txt", "orig\n", "add unrelated")

    install_hook(repo.path, "pre-commit", _RETRY_ONCE_HOOK)

    (repo.path / "staged.txt").write_text("v1\n")
    repo.run("add", "staged.txt")
    (repo.path / "unrelated.txt").write_text("orig\nunstaged-edit\n")

    commit_fixup_with_retry(target)

    committed_files = repo.run("show", "--name-only", "--format=").stdout.split()
    assert committed_files == ["staged.txt"]
    assert (repo.path / "unrelated.txt").read_text() == "orig\nunstaged-edit\n"


def test_commit_fixup_with_retry_raises_immediately_without_working_tree_changes(repo):
    target = _target_sha(repo)
    install_hook(repo.path, "pre-commit", _FAIL_NO_MODIFY_HOOK)

    (repo.path / "staged.txt").write_text("v1\n")
    repo.run("add", "staged.txt")

    with pytest.raises(CliError, match="no working-tree"):
        commit_fixup_with_retry(target)

    subject = repo.run("log", "-1", "--format=%s").stdout.strip()
    assert subject == "add base"
