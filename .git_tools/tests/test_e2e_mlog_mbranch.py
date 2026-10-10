"""Light end-to-end coverage for bin/git-mlog, bin/git-mlogf, and bin/git-mbranch."""

from __future__ import annotations

import re

from conftest import run_bin


def test_mlog_lists_commits_ahead_of_default_branch(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")

    proc = run_bin("git-mlog", [], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert "add a" in proc.stdout
    assert "add b" in proc.stdout
    assert "initial commit" not in proc.stdout


def test_mlog_hides_head_and_current_branch_but_keeps_other_refs(repo):
    repo.run("checkout", "-q", "-b", "feature")
    repo.commit("a.txt", "a\n", "add a")
    repo.run("push", "-q", "origin", "feature")
    repo.commit("b.txt", "b\n", "add b")

    proc = run_bin("git-mlog", [], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert "HEAD" not in proc.stdout
    tip = next(l for l in proc.stdout.splitlines() if "add b" in l)
    assert "feature" not in tip
    pushed = next(l for l in proc.stdout.splitlines() if "add a" in l)
    assert "[origin/feature]" in pushed


def test_mlog_stat_flag_includes_diffstat(repo):
    repo.commit("a.txt", "a\n", "add a")
    proc = run_bin("git-mlog", ["--stat"], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert "a.txt" in proc.stdout


def test_mlog_falls_back_to_local_master_without_origin_master(repo):
    # Real-world case: no remote configured at all, or origin/master just
    # hasn't been fetched -- mlog must still work against local master
    # instead of erroring with "'origin/master' does not exist".
    repo.run("update-ref", "-d", "refs/remotes/origin/master")
    repo.run("checkout", "-q", "-b", "feature")
    repo.commit("a.txt", "a\n", "add a")

    proc = run_bin("git-mlog", [], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert "add a" in proc.stdout


def test_mlog_does_not_page_when_output_is_piped(repo):
    # run_bin captures stdout (a pipe, not a tty) -- print_or_page must take
    # the direct-write path regardless of how many commits there are.
    for i in range(5):
        repo.commit(f"f{i}.txt", f"{i}\n", f"commit {i}")
    proc = run_bin("git-mlog", [], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.count("commit ") == 5


def test_mlogf_lists_changed_files_per_commit(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")

    proc = run_bin("git-mlogf", [], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert "add a" in proc.stdout
    assert "add b" in proc.stdout
    assert "a.txt" in proc.stdout
    assert "b.txt" in proc.stdout
    assert "file changed" not in proc.stdout


def test_mlogf_is_equivalent_to_mlog_stat(repo):
    repo.commit("a.txt", "a\n", "add a")
    mlogf = run_bin("git-mlogf", [], repo.path)
    mlog_stat = run_bin("git-mlog", ["--stat"], repo.path)
    assert mlogf.returncode == mlog_stat.returncode == 0
    # The two runs can straddle a second boundary ("1 second ago" vs
    # "2 seconds ago"), so compare with the relative date masked out.
    assert _mask_dates(mlogf.stdout) == _mask_dates(mlog_stat.stdout)


def _mask_dates(text):
    return re.sub(r"\d+ \w+ ago", "<date>", text)


def test_mbranch_lists_recent_branches_with_current_marker(repo):
    repo.run("checkout", "-q", "-b", "feature-a")
    repo.run("checkout", "-q", "master")

    proc = run_bin("git-mbranch", [], repo.path)
    assert proc.returncode == 0, proc.stderr
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    assert any(l.startswith("*") and "master" in l for l in lines)
    assert any("feature-a" in l for l in lines)


def test_mbranch_reports_empty_when_no_checkouts(repo):
    proc = run_bin("git-mbranch", [], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert "no branch checkouts found" in proc.stdout
