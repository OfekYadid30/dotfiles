"""End-to-end tests for bin/git-mfixupa, run as real subprocesses."""

from __future__ import annotations

from conftest import no_fzf_path, run_bin, run_git


def test_mfixupa_refuses_when_something_staged(repo):
    repo.commit("a.txt", "a\n", "add a")
    (repo.path / "a.txt").write_text("a2\n")
    repo.run("add", "a.txt")

    proc = run_bin("git-mfixupa", [], repo.path)
    assert proc.returncode != 0
    assert "already staged" in proc.stderr


def test_mfixupa_refuses_when_nothing_unstaged(repo):
    proc = run_bin("git-mfixupa", [], repo.path)
    assert proc.returncode != 0
    assert "nothing to do" in proc.stderr


def test_mfixupa_auto_picks_unambiguous_targets_per_file(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")

    (repo.path / "a.txt").write_text("a2\n")
    (repo.path / "b.txt").write_text("b2\n")

    proc = run_bin("git-mfixupa", [], repo.path)
    assert proc.returncode == 0, proc.stderr

    subjects = repo.run(
        "log", "--oneline", "--no-decorate", "--format=%s", "origin/master..HEAD"
    ).stdout.splitlines()
    # Newest fixup first; each file's fixup targets its own commit.
    assert set(subjects) == {"fixup! add a", "fixup! add b", "add a", "add b"}
    assert repo.run("diff", "--cached", "--name-only").stdout.strip() == ""
    assert repo.run("diff", "--name-only").stdout.strip() == ""


def test_mfixupa_prompts_when_multiple_candidates_touch_a_file(repo, tmp_path):
    repo.commit("shared.txt", "v1\n", "add shared v1")
    repo.commit("shared.txt", "v2\n", "add shared v2")
    repo.commit("other.txt", "o\n", "add other")

    (repo.path / "shared.txt").write_text("v3\n")

    env = {"PATH": no_fzf_path(tmp_path)}
    # Candidates (newest first): "add shared v2", "add shared v1" -> pick "1"
    proc = run_bin("git-mfixupa", [], repo.path, input="1\n", env=env)
    assert proc.returncode == 0, proc.stderr

    subject = repo.run("log", "-1", "--format=%s").stdout.strip()
    assert subject == "fixup! add shared v2"


def test_mfixupa_ignores_untracked_files(repo):
    # An untracked ("added" but never `git add`ed -- i.e. brand new and not
    # part of git at all yet) file must be completely invisible to
    # mfixupa: it only ever looks at `git diff --name-only` (tracked,
    # unstaged modifications), never `git status`'s untracked list.
    repo.commit("a.txt", "a\n", "add a")
    (repo.path / "a.txt").write_text("a2\n")
    (repo.path / "brand_new.txt").write_text("never added\n")

    proc = run_bin("git-mfixupa", [], repo.path)
    assert proc.returncode == 0, proc.stderr
    assert "brand_new.txt" not in proc.stdout
    assert "brand_new.txt" not in proc.stderr

    subject = repo.run("log", "-1", "--format=%s").stdout.strip()
    assert subject == "fixup! add a"
    # Still sitting there, untouched, still untracked.
    assert (repo.path / "brand_new.txt").read_text() == "never added\n"
    assert "brand_new.txt" in repo.run("status", "--porcelain").stdout


def test_mfixupa_handles_mixed_batch_in_one_run(repo, tmp_path):
    # Realistic combined run: one file with an unambiguous target (auto),
    # one with multiple candidates (picker), one with no candidate ahead of
    # the branch (skipped), and one untracked file (ignored entirely) --
    # all unstaged at once, in a single mfixupa invocation.
    repo.commit("only_in_base.txt", "base\n", "add file before branch point")
    # Push it so it's genuinely already on origin/master, not just ahead of
    # it locally. origin here is a non-bare repo with master checked out, so
    # a plain push is refused by default -- allow it just for this push.
    run_git(repo.origin, "config", "receive.denyCurrentBranch", "ignore")
    repo.run("push", "-q", "origin", "master")
    repo.run("fetch", "-q", "origin")  # sync local origin/master tracking ref

    repo.run("checkout", "-q", "-b", "feature")
    repo.commit("alpha.txt", "a1\n", "add alpha")
    repo.commit("beta.txt", "b1\n", "add beta v1")
    repo.commit("beta.txt", "b2\n", "add beta v2")

    (repo.path / "alpha.txt").write_text("a2\n")          # 1 candidate -> auto
    (repo.path / "beta.txt").write_text("b3\n")            # 2 candidates -> picker
    (repo.path / "only_in_base.txt").write_text("base\nedited\n")  # 0 candidates -> skipped
    (repo.path / "brand_new.txt").write_text("never added\n")      # untracked -> ignored

    env = {"PATH": no_fzf_path(tmp_path)}
    # Candidates for beta.txt (newest first): "add beta v2", "add beta v1"
    proc = run_bin("git-mfixupa", [], repo.path, input="1\n", env=env)
    assert proc.returncode == 0, proc.stderr

    subjects = set(
        repo.run(
            "log", "--oneline", "--no-decorate", "--format=%s", "origin/master..HEAD"
        ).stdout.splitlines()
    )
    assert subjects == {
        "add alpha",
        "add beta v1",
        "add beta v2",
        "fixup! add alpha",
        "fixup! add beta v2",
    }
    assert "only_in_base.txt" in proc.stderr  # reported as skipped
    assert (repo.path / "only_in_base.txt").read_text() == "base\nedited\n"  # untouched
    assert "brand_new.txt" not in proc.stdout and "brand_new.txt" not in proc.stderr
    assert (repo.path / "brand_new.txt").read_text() == "never added\n"


def test_mfixupa_falls_back_to_local_master_without_origin_master(repo):
    repo.run("update-ref", "-d", "refs/remotes/origin/master")
    repo.run("checkout", "-q", "-b", "feature")
    repo.commit("a.txt", "a\n", "add a")
    (repo.path / "a.txt").write_text("a2\n")

    proc = run_bin("git-mfixupa", [], repo.path)
    assert proc.returncode == 0, proc.stderr

    subject = repo.run("log", "-1", "--format=%s").stdout.strip()
    assert subject == "fixup! add a"


def test_mfixupa_with_squash_folds_everything(repo):
    repo.commit("a.txt", "a\n", "add a")
    repo.commit("b.txt", "b\n", "add b")

    (repo.path / "a.txt").write_text("a2\n")
    (repo.path / "b.txt").write_text("b2\n")

    proc = run_bin("git-mfixupa", ["--squash"], repo.path)
    assert proc.returncode == 0, proc.stderr

    subjects = repo.run(
        "log", "--oneline", "--no-decorate", "--format=%s", "origin/master..HEAD"
    ).stdout.splitlines()
    assert subjects == ["add b", "add a"]
    assert (repo.path / "a.txt").read_text() == "a2\n"
    assert (repo.path / "b.txt").read_text() == "b2\n"
