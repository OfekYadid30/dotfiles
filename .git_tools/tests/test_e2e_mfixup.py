"""End-to-end tests for bin/git-mfixup, run as real subprocesses."""

from __future__ import annotations

from conftest import no_fzf_path, run_bin


def test_mfixup_requires_staged_changes(repo):
    proc = run_bin("git-mfixup", [], repo.path)
    assert proc.returncode != 0
    assert "nothing is staged" in proc.stderr


def test_mfixup_with_explicit_sha_creates_fixup_commit_without_rebasing(repo):
    repo.commit("a.txt", "a\n", "add a")
    target = repo.run("rev-parse", "HEAD").stdout.strip()
    repo.commit("b.txt", "b\n", "add b")

    (repo.path / "a.txt").write_text("a2\n")
    repo.run("add", "a.txt")

    proc = run_bin("git-mfixup", [target], repo.path)
    assert proc.returncode == 0, proc.stderr

    subjects = repo.run("log", "--oneline", "--no-decorate", "-3", "--format=%s").stdout.splitlines()
    assert subjects == ["fixup! add a", "add b", "add a"]


def test_mfixup_with_squash_folds_into_target_immediately(repo):
    repo.commit("a.txt", "a\n", "add a")
    target = repo.run("rev-parse", "HEAD").stdout.strip()
    repo.commit("b.txt", "b\n", "add b")

    (repo.path / "a.txt").write_text("a2\n")
    repo.run("add", "a.txt")

    proc = run_bin("git-mfixup", [target, "--squash"], repo.path)
    assert proc.returncode == 0, proc.stderr

    subjects = repo.run("log", "--oneline", "--no-decorate", "--format=%s", "origin/master..HEAD").stdout.splitlines()
    assert subjects == ["add b", "add a"]
    assert (repo.path / "a.txt").read_text() == "a2\n"


def test_mfixup_errors_when_nothing_ahead_of_default_branch(repo):
    (repo.path / "README.md").write_text("changed\n")
    repo.run("add", "README.md")

    proc = run_bin("git-mfixup", [], repo.path)
    assert proc.returncode != 0
    assert "no commits found ahead" in proc.stderr


def test_mfixup_all_flag_falls_back_to_full_history_with_picker(repo, tmp_path):
    # Nothing local ahead of master, so the default candidate set is empty;
    # --all should fall back to full history (just "initial commit" here)
    # and prompt via the numbered picker since there's exactly one item but
    # multiple candidates matters only for mfixupa's auto-pick -- mfixup
    # always shows the picker when no sha is given.
    (repo.path / "README.md").write_text("changed\n")
    repo.run("add", "README.md")

    env = {"PATH": no_fzf_path(tmp_path)}
    proc = run_bin("git-mfixup", ["--all"], repo.path, input="1\n", env=env)
    assert proc.returncode == 0, proc.stderr

    subject = repo.run("log", "-1", "--format=%s").stdout.strip()
    assert subject == "fixup! initial commit"
