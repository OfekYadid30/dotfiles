# .git_tools

Python replacements for a handful of `git` subcommands, wired up via `git`
aliases in `~/.gitconfig`. Everything shared between them lives in the
`gitm` library; each command in `bin/` is a thin CLI wrapper around it.

No install step, no dependencies beyond Python 3.10+ and `git` itself.
`fzf` is optional — every picker falls back to a plain numbered prompt if
it's not installed. Works on macOS and Linux (anything with a POSIX shell
and `git`); nothing here is OS-specific.

## Commands

All of these resolve "the default branch" the same way (see
[Default branch resolution](#default-branch-resolution) below), and all
accept `--branch <name>` / `--remote <name>` to override it.

### `git mlog [--branch] [--stat]`

Shows the commits in `origin/<branch>..HEAD` — i.e. exactly the commits
you'd be pushing or merging — one per line as `hash  date  subject  [refs]`,
with the date column aligned. The `HEAD -> <branch>` / current-branch
decoration is hidden (it always marks the tip, so it's noise); other refs
like `origin/<branch>` or tags are still shown. There's no graph column;
merge commits are tagged `merge` instead.

`--stat` lists each commit's changed files underneath it (blue, aligned,
with green `+N` / red `-N` line counts, or `binary`), with a blank line
between commits.

Prints directly to the terminal; only opens a pager if the output is
actually taller than your terminal window (measured against the real
terminal height, not your `git`/`less` config — see `gitm/pager.py`).
Respects `$PAGER` if set, otherwise uses `less -R`. Never pages at all when
stdout isn't a terminal (piped/redirected).

### `git mlogf [--branch]`

Exactly `git mlog --stat` — kept as its own command since that's what a lot
of muscle memory expects.

### `git mfixup [commit-sha] [--branch] [--all] [--squash]`

Fixup currently-staged changes into a chosen commit. Requires something to
already be staged (`git add` first).

- Without a `commit-sha`, opens a picker over the commits ahead of the
  default branch (existing `fixup!`/`squash!`/`amend!` commits are excluded
  as candidates — a fixup can't target another fixup). `--all` picks from
  the full history instead.
- Creates a `fixup!` commit on top of HEAD. **It stays as its own commit —
  nothing is rebased or squashed automatically.** Pass `--squash` to also
  autosquash-rebase it into place immediately.
- If a pre-commit hook fails but leaves working-tree changes behind (e.g. it
  reformatted a file), the affected files are re-staged and the commit is
  retried automatically, up to 3 times.

### `git mfixupa [--branch] [--squash]`

Same idea as `mfixup`, but for every tracked file that has unstaged changes
at once — handy after touching several files across a branch and wanting
each change folded into the commit that introduced it.

- Refuses to run if anything is already staged (to avoid mixing unrelated
  changes into the fixups it creates).
- For each unstaged file: finds the commit(s) ahead of the default branch
  that touched it — never something already on master. Exactly one
  candidate → fixup automatically. Several → opens the same picker as
  `mfixup`, labeled with the filename. None → the file is skipped.
- Same hook-retry behavior as `mfixup`.
- Like `mfixup`, stays as separate `fixup!` commits unless `--squash` is
  passed.

### `git msquash [--branch]`

Condenses multiple `fixup!` commits that target the *same* commit into a
single `fixup!` commit — e.g. if you ran `mfixup`/`mfixupa` against commit
`X` more than once and now have three separate `fixup! X` commits sitting on
top of it. Merges those three into one. **Does not touch `X` itself** and
does not autosquash anything into it — run `git mrebase` (or
`mfixup --squash`) afterwards when you're ready for that.

Targets with only one fixup commit are left alone. If nothing needs
condensing, no rebase runs at all. Refuses (rather than silently mangling
history) if there's a merge commit ahead of the default branch.

### `git mbranch [-n COUNT]`

Lists the most recently checked-out branches (newest first, deduplicated),
parsed from `HEAD`'s reflog. Defaults to the last 20; `*` marks the current
branch.

## Default branch resolution

Every command needs to know "what's the mainline branch". Resolution order:

1. `--branch <name>` on the command line
2. `git config gitm.default-branch` (set this per-repo if it isn't `master`)
3. `master`

Deliberately not auto-detected (e.g. via `origin/HEAD`) — every command
always means `master` unless told otherwise via one of the two overrides
above. No network access, no fetching: this is purely local ref comparison.

Once the branch name is resolved, comparisons are made against
`origin/<branch>` if that remote-tracking ref exists, otherwise the local
`<branch>` (e.g. no remote configured, working offline, or it just hasn't
been fetched yet). If neither exists, the command errors out clearly.

## Layout

```
gitm/            shared library — put anything more than one command needs here
  cli.py         CliError, run_main(), shared argparse helpers
  gitrun.py      subprocess wrapper around `git`
  refs.py        default-branch resolution, commits-ahead-of-branch, merge-commit detection
  picker.py      fzf picker with a numbered-prompt fallback
  pager.py       print directly, or page only if content overflows the terminal
  mlog.py        shared mlog/mlogf implementation
  fixup.py       staged-paths helpers, commit --fixup (with pre-commit-hook retry), autosquash rebase
  reflog.py      recently-visited-branch parsing (mbranch)
  msquash.py     condensing multiple fixup! commits per target into one

bin/             the actual executables, one per `git m*` subcommand
  git-mlog
  git-mlogf
  git-mfixup
  git-mfixupa
  git-mbranch
  git-msquash

tests/           pytest suite (see below)
```

Each `bin/git-*` script does its own `sys.path.insert` to find `gitm` next
to it, so they can be run directly (`~/.git_tools/bin/git-mlog`) without any
install step. `~/.gitconfig` aliases just point at these paths, e.g.:

```ini
[alias]
    mlog = "!~/.git_tools/bin/git-mlog"
    mlogf = "!~/.git_tools/bin/git-mlogf"
    mfixup = "!~/.git_tools/bin/git-mfixup"
    mfixupa = "!~/.git_tools/bin/git-mfixupa"
    msquash = "!~/.git_tools/bin/git-msquash"
    mbranch = "!~/.git_tools/bin/git-mbranch"
```

## Running the tests

```sh
cd ~/.git_tools
python3 -m pytest tests -v
```

(`pytest` needs to be installed — `pip install pytest` or `pip install -e
.[test]`-style if you add one; there's no dependency file here since this
project has no runtime dependencies of its own.)

The suite is entirely integration-style: every test builds a real,
throwaway git repo under pytest's `tmp_path` (an `origin` plus a clone) and
exercises the actual `gitm` functions and/or `bin/git-*` scripts against it
as subprocesses — nothing is mocked, and nothing ever touches your real
`~/.gitconfig` or home-directory git state (`tests/conftest.py` redirects
`HOME` and disables global/system git config for the duration of each test).

- `test_refs.py` — default-branch resolution, `commits_ahead`/`all_commits`
- `test_pager.py` — the pager-vs-direct-print decision (mocked terminal/tty,
  never drives a real pager)
- `test_reflog.py` — `mbranch`'s recent-branch parsing
- `test_fixup.py` — fixup commits, the pre-commit-hook retry path, the
  merge-commit refusal
- `test_msquash.py` — fixup grouping/condensing, the interleaving warning,
  the merge-commit refusal
- `test_e2e_*.py` — full subprocess runs of the `bin/git-*` scripts,
  including the picker's numbered-prompt fallback (fzf deliberately hidden
  from `PATH`) and the `--squash`/`--branch`/`--all` flags
