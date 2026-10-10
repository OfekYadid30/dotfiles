"""Tests for gitm.reflog.recent_branches (backs mbranch)."""

from __future__ import annotations

from gitm.reflog import recent_branches


def _checkout_dance(repo):
    """master -> feature-a -> master -> feature-b -> feature-a

    Reflog (newest first) checkout entries once this finishes:
      feature-b -> feature-a
      master    -> feature-b
      feature-a -> master
      master    -> feature-a
    So recent_branches() should report, deduplicated newest-first:
      feature-a, feature-b, master
    """
    repo.run("checkout", "-q", "-b", "feature-a")
    repo.run("checkout", "-q", "master")
    repo.run("checkout", "-q", "-b", "feature-b")
    repo.run("checkout", "-q", "feature-a")


def test_recent_branches_orders_newest_first_and_dedupes(repo):
    _checkout_dance(repo)

    visits = recent_branches()
    branches = [v.branch for v in visits]
    assert branches == ["feature-a", "feature-b", "master"]


def test_recent_branches_respects_limit(repo):
    _checkout_dance(repo)

    visits = recent_branches(limit=2)
    assert [v.branch for v in visits] == ["feature-a", "feature-b"]


def test_recent_branches_has_relative_when_field(repo):
    _checkout_dance(repo)
    visits = recent_branches()
    for v in visits:
        assert v.when  # non-empty relative-date string, e.g. "0 seconds ago"


def test_recent_branches_skips_detached_head_shas(repo):
    repo.run("checkout", "-q", "-b", "feature-a")
    sha = repo.run("rev-parse", "HEAD").stdout.strip()
    repo.run("checkout", "-q", sha)  # detached HEAD, recorded as moving to a bare sha
    repo.run("checkout", "-q", "master")

    visits = recent_branches()
    branches = [v.branch for v in visits]
    assert sha not in branches
    assert branches == ["master", "feature-a"]


def test_recent_branches_includes_hex_named_branches(repo):
    # Regression: branches used to be filtered out via a "looks like a bare
    # hex SHA" regex, which also matched real branch names like "deadbeef".
    repo.run("checkout", "-q", "-b", "deadbeef")
    repo.run("checkout", "-q", "master")

    visits = recent_branches()
    assert [v.branch for v in visits] == ["master", "deadbeef"]


def test_recent_branches_empty_when_no_checkouts(repo):
    # A fresh clone still has a reflog entry for the clone itself, but no
    # "checkout: moving from X to Y" entries yet.
    visits = recent_branches()
    assert visits == []
