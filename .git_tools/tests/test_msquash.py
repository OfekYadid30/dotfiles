"""Tests for gitm.msquash: find_multi_fixup_groups and condense_fixups."""

from __future__ import annotations

import pytest

from gitm.cli import CliError
from gitm.msquash import condense_fixups, find_multi_fixup_groups
from gitm.refs import commits_ahead


def test_find_multi_fixup_groups_groups_by_target_subject(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")
    repo.commit("a.txt", "a2\n", "fixup! add a")
    repo.commit("a.txt", "a3\n", "fixup! add a")

    commits_oldest_first = list(reversed(commits_ahead("master", exclude_fixups=False)))
    groups = find_multi_fixup_groups(commits_oldest_first)

    assert len(groups) == 1
    assert groups[0].target_subject == "add a"
    assert [c.subject for c in groups[0].commits] == ["fixup! add a", "fixup! add a"]


def test_find_multi_fixup_groups_ignores_single_fixups(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")
    repo.commit("b.txt", "b2\n", "fixup! add b")  # only one fixup for "add b"

    commits_oldest_first = list(reversed(commits_ahead("master", exclude_fixups=False)))
    groups = find_multi_fixup_groups(commits_oldest_first)

    assert groups == []


def test_condense_fixups_noop_when_nothing_to_condense(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")
    repo.commit("b.txt", "b2\n", "fixup! add b")

    before = repo.run("rev-parse", "HEAD").stdout.strip()
    groups = condense_fixups("master")
    after = repo.run("rev-parse", "HEAD").stdout.strip()

    assert groups == []
    # No rebase should have run at all -- HEAD is untouched.
    assert before == after


def test_condense_fixups_collapses_multi_fixup_group(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")
    repo.commit("a.txt", "a2\n", "fixup! add a")
    repo.commit("a.txt", "a3\n", "fixup! add a")
    repo.commit("c.txt", "c\n", "add c")

    groups = condense_fixups("master")

    assert len(groups) == 1
    assert groups[0].target_subject == "add a"

    subjects = [c.subject for c in commits_ahead("master", exclude_fixups=False)]
    # Newest first: add c, condensed fixup, add b, add a
    assert subjects == ["add c", "fixup! add a", "add b", "add a"]

    # Only one fixup! commit remains for "add a" now (HEAD~1: HEAD is "add
    # c", HEAD~1 the condensed fixup, HEAD~2 "add b", HEAD~3 "add a"), and
    # its tree reflects both original fixups' changes applied in sequence.
    content = repo.run("show", "HEAD~1:a.txt").stdout
    assert content == "a3\n"


def test_condense_fixups_leaves_real_targets_and_other_commits_untouched(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")
    repo.commit("a.txt", "a2\n", "fixup! add a")
    repo.commit("a.txt", "a3\n", "fixup! add a")

    condense_fixups("master")

    subjects = [c.subject for c in commits_ahead("master", exclude_fixups=False)]
    assert "add a" in subjects
    assert "add b" in subjects
    assert subjects.count("fixup! add a") == 1


def test_condense_fixups_warns_about_interleaved_commits(repo, capsys):
    # Regression: condensing moves a group's members together, silently
    # reordering any unrelated commit that was sitting between them. There
    # must at least be a visible warning about it.
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("a.txt", "a2\n", "fixup! add a")
    repo.commit("c.txt", "c\n", "add c")  # interleaved between the two fixups
    repo.commit("a.txt", "a3\n", "fixup! add a")

    condense_fixups("master")

    stderr = capsys.readouterr().err
    assert "reorder" in stderr
    assert "add c" in stderr


def test_condense_fixups_noop_ignores_merge_commits(repo):
    # Nothing to condense -> no rebase attempted at all, so a merge commit
    # ahead of main must not block this no-op path.
    repo.run("checkout", "-q", "-b", "feature")
    repo.commit("a.txt", "a\n", "add a")
    repo.run("checkout", "-q", "-b", "side", "master")
    repo.commit("b.txt", "b\n", "add b")
    repo.run("checkout", "-q", "feature")
    repo.run("merge", "-q", "--no-edit", "side")

    assert condense_fixups("master") == []


def test_condense_fixups_refuses_merge_commits_when_condensing(repo):
    repo.run("checkout", "-q", "-b", "feature")
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("a.txt", "a2\n", "fixup! add a")
    repo.commit("a.txt", "a3\n", "fixup! add a")
    repo.run("checkout", "-q", "-b", "side", "master")
    repo.commit("b.txt", "b\n", "add b")
    repo.run("checkout", "-q", "feature")
    repo.run("merge", "-q", "--no-edit", "side")

    before = repo.run("rev-parse", "HEAD").stdout.strip()
    with pytest.raises(CliError, match="merge commit"):
        condense_fixups("master")
    after = repo.run("rev-parse", "HEAD").stdout.strip()
    assert before == after
