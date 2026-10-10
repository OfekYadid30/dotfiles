"""Tests for gitm.refs: default_branch resolution and commits_ahead/all_commits."""

from __future__ import annotations

import pytest

from gitm.cli import CliError
from gitm.refs import all_commits, commits_ahead, current_branch, default_branch, upstream_ref


def test_default_branch_explicit_wins(repo):
    assert default_branch("whatever-branch") == "whatever-branch"


def test_default_branch_from_config(repo):
    repo.run("config", "gitm.default-branch", "custom-branch")
    assert default_branch() == "custom-branch"


def test_default_branch_config_beats_master_fallback(repo):
    repo.run("config", "gitm.default-branch", "custom-branch")
    assert default_branch() == "custom-branch"


def test_default_branch_defaults_to_master(repo):
    # No --branch, no gitm.default-branch config -> always "master",
    # regardless of what origin/HEAD or anything else on the remote is.
    assert default_branch() == "master"


def test_default_branch_ignores_origin_head_symref(repo):
    # Even if origin/HEAD points somewhere else, the hardcoded "master"
    # fallback wins -- resolution is no longer auto-detected from the remote.
    repo.run("branch", "some-other-branch")
    repo.run("update-ref", "refs/remotes/origin/some-other-branch", "refs/remotes/origin/master")
    repo.run("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/some-other-branch")
    assert default_branch() == "master"


def test_default_branch_never_raises(repo):
    # Always resolves to "master" now; only upstream_ref() (used downstream
    # by callers like commits_ahead) can fail, if origin/master doesn't
    # actually exist.
    repo.run("update-ref", "-d", "refs/remotes/origin/master")
    assert default_branch() == "master"


def test_upstream_ref_prefers_remote_tracking_ref(repo):
    assert upstream_ref("master") == "origin/master"


def test_upstream_ref_falls_back_to_local_branch(repo):
    # origin/master missing (no remote configured, working offline, or it
    # just hasn't been fetched) but a local "master" branch exists -> use
    # that instead of erroring.
    repo.run("update-ref", "-d", "refs/remotes/origin/master")
    assert upstream_ref("master") == "master"


def test_upstream_ref_raises_when_neither_remote_nor_local_exists(repo):
    with pytest.raises(CliError, match="neither"):
        upstream_ref("nonexistent-branch")


def test_commits_ahead_works_via_local_branch_fallback(repo):
    # The real-world scenario: no remote at all (or origin/master not
    # fetched), so commits_ahead must still resolve against local master.
    repo.run("update-ref", "-d", "refs/remotes/origin/master")
    repo.run("checkout", "-q", "-b", "feature")
    repo.commit("a.txt", "a\n", "add a")
    subjects = [c.subject for c in commits_ahead("master")]
    assert subjects == ["add a"]


def test_current_branch_detached_head_raises(repo):
    sha = repo.run("rev-parse", "HEAD").stdout.strip()
    repo.run("checkout", "-q", sha)
    with pytest.raises(CliError):
        current_branch()


def test_commits_ahead_lists_local_only_commits_newest_first(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")

    commits = commits_ahead("master")
    subjects = [c.subject for c in commits]
    assert subjects == ["add b", "add a"]


def test_commits_ahead_excludes_fixups_by_default(repo):
    repo.commit("a.txt", "a\n", "add a")
    target = repo.run("rev-parse", "HEAD").stdout.strip()
    repo.commit("a.txt", "a2\n", f"fixup! add a")
    assert target  # sanity

    commits = commits_ahead("master")
    subjects = [c.subject for c in commits]
    assert subjects == ["add a"]


def test_commits_ahead_can_include_fixups(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("a.txt", "a2\n", "fixup! add a")

    commits = commits_ahead("master", exclude_fixups=False)
    subjects = [c.subject for c in commits]
    assert subjects == ["fixup! add a", "add a"]


def test_commits_ahead_excludes_squash_and_amend_prefixes(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "squash! add a")
    repo.commit("c.txt", "c\n", "amend! add a")

    commits = commits_ahead("master")
    subjects = [c.subject for c in commits]
    assert subjects == ["add a"]


def test_commits_ahead_filters_by_path(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")
    repo.commit("a.txt", "a2\n", "touch a again")

    commits = commits_ahead("master", paths=["a.txt"])
    subjects = [c.subject for c in commits]
    assert subjects == ["touch a again", "add a"]


def test_commits_ahead_empty_when_nothing_ahead(repo):
    assert commits_ahead("master") == []


def test_all_commits_includes_commits_before_divergence(repo):
    # "initial commit" from origin plus one more local commit; both should
    # show up in all_commits() even though only the local one is "ahead".
    repo.commit("a.txt", "a\n", "add a")
    subjects = [c.subject for c in all_commits()]
    assert subjects == ["add a", "initial commit"]


def test_all_commits_excludes_fixups_by_default(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("a.txt", "a2\n", "fixup! add a")
    subjects = [c.subject for c in all_commits()]
    assert subjects == ["add a", "initial commit"]
