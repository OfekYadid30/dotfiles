"""End-to-end tests for bin/git-msquash, run as real subprocesses."""

from __future__ import annotations

from conftest import run_bin


def test_msquash_noop_when_nothing_to_condense(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")
    repo.commit("b.txt", "b2\n", "fixup! add b")

    before = repo.run("rev-parse", "HEAD").stdout.strip()
    proc = run_bin("git-msquash", [], repo.path)
    after = repo.run("rev-parse", "HEAD").stdout.strip()

    assert proc.returncode == 0, proc.stderr
    assert "nothing to condense" in proc.stderr
    assert before == after


def test_msquash_condenses_multi_fixup_groups(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")
    repo.commit("a.txt", "a2\n", "fixup! add a")
    repo.commit("a.txt", "a3\n", "fixup! add a")

    proc = run_bin("git-msquash", [], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert "condensed 2 fixup! commits targeting: add a" in proc.stderr

    subjects = repo.run(
        "log", "--oneline", "--no-decorate", "--format=%s", "origin/master..HEAD"
    ).stdout.splitlines()
    assert subjects == ["fixup! add a", "add b", "add a"]
    assert subjects.count("fixup! add a") == 1


def test_msquash_respects_explicit_branch(repo):
    # Set up an "other" mainline ref so --branch has to actually be used
    # instead of the default ("master").
    repo.run("update-ref", "refs/remotes/origin/other-main", "refs/remotes/origin/master")
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("a.txt", "a2\n", "fixup! add a")
    repo.commit("a.txt", "a3\n", "fixup! add a")

    proc = run_bin("git-msquash", ["--branch", "other-main"], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert "condensed 2 fixup! commits targeting: add a" in proc.stderr
