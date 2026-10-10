#!/usr/bin/env bash
# Build a throwaway git repo set up to exercise every .git_tools command
# AND every edge case its test suite covers (hook-retry success/failure
# modes, the various refusal guards, the merge-commit guard, branch names
# with slashes, hex-looking branch names, ...), then print a manual
# checklist so you can watch each one happen with your own eyes.
#
# Each edge case (Part B) gets its own `git worktree` -- a separate working
# directory on its own branch, sharing the same repo/hooks/history. That
# way every scenario's dirty/staged state can coexist permanently instead
# of clobbering each other via `git checkout`.
#
# Doesn't touch anything outside the directory it creates.
#
# Usage: demo/playground.sh [destination-dir]
#   destination-dir defaults to a fresh timestamped dir under /tmp so
#   re-running never clobbers a previous playground.

set -euo pipefail

# The setup below creates commits on branches whose names the pre-commit
# hook (installed further down) dispatches on. Without this, several of
# those setup commits would trip the very failure modes they're building a
# scenario to demonstrate later. The hook exits 0 immediately whenever this
# is set; it's never set in the user's own interactive shell afterward.
export GITM_DEMO_SETUP=1

DEST="${1:-/tmp/gitm-playground-$(date +%Y%m%d-%H%M%S)}"
ORIGIN="$DEST/origin"
WORK="$DEST/work"
SCEN="$DEST/scenarios"
SLASH_ORIGIN="$DEST/slash-branch-origin"
SLASH_WORK="$DEST/slash-branch-work"
NO_REMOTE_REPO="$DEST/no-remote-repo"

if [ -e "$DEST" ]; then
    echo "error: $DEST already exists; pass a different/empty directory" >&2
    exit 1
fi

git_id() {
    git -C "$1" config user.name "Playground"
    git -C "$1" config user.email "playground@example.com"
}

# new_scenario <name> -- creates a worktree at $SCEN/<name> on a fresh
# branch "scenario/<name>" starting from master, and cds into it.
new_scenario() {
    local dir="$SCEN/$1"
    git -C "$WORK" worktree add -q "$dir" -b "scenario/$1" master
    cd "$dir"
}

# ============================================================================
# Main repo: origin (master) + work clone. "master" because that's gitm's
# hardcoded default (git config gitm.default-branch overrides it; nothing
# here is auto-detected from origin/HEAD or any other remote probing).
# ============================================================================

mkdir -p "$ORIGIN"
git -C "$ORIGIN" init -q -b master
git_id "$ORIGIN"
echo "# demo repo" > "$ORIGIN/README.md"
git -C "$ORIGIN" add -A
git -C "$ORIGIN" commit -q -m "initial commit"
# Baked into master's own history (not added on any branch off it), so
# scenario/skip-file-not-ahead-of-branch can edit this file without it ever
# being "ahead of origin/master" -- see that scenario below.
echo "base content" > "$ORIGIN/only_in_base.txt"
git -C "$ORIGIN" add -A
git -C "$ORIGIN" commit -q -m "add file only touched before the branch point"

git clone -q "$ORIGIN" "$WORK"
git_id "$WORK"
cd "$WORK"

# --- a couple of clean (non-dirty) branch visits, purely so `git mbranch`
#     and the "hex-named branch" edge case have real reflog history ---
git checkout -q -b scratch/notes master
echo "wip" > notes.txt
git add notes.txt
git commit -q -m "scratch notes (not on feature/demo)"
git checkout -q -b deadbeef master   # a branch literally named like a hex SHA
git checkout -q master

# ----------------------------------------------------------------------------
# PART A: feature/demo -- the "everything working normally" walkthrough.
# Built and left checked out (dirty) in $WORK itself; every Part B scenario
# below instead gets its own `git worktree`, so it never has to switch $WORK
# away from feature/demo's uncommitted changes.
# ----------------------------------------------------------------------------
git checkout -q -b feature/demo master

cat > greeting.py <<'EOF'
def greet(name):
    return f"hello {name}"
EOF
git add greeting.py
git commit -q -m "add greeting"

cat > mathutils.py <<'EOF'
def add(a, b):
    return a + b
EOF
git add mathutils.py
git commit -q -m "add math utils"

cat > config.yaml <<'EOF'
env: dev
EOF
git add config.yaml
git commit -q -m "add config"

echo "def sub(a, b): return a - b" >> mathutils.py
git add mathutils.py
git commit -q -m "fixup! add math utils"

# ----------------------------------------------------------------------------
# The shared pre-commit hook. Lives in $WORK/.git/hooks, so it applies to
# every worktree of this repo (worktrees share hooks). It dispatches on the
# current branch name so each Part B scenario can exercise a different
# hook-failure mode from the same hook file. Branches not listed pass
# straight through (exit 0) regardless of what's staged.
# ----------------------------------------------------------------------------
mkdir -p .git/hooks
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
set -e
[ -n "${GITM_DEMO_SETUP:-}" ] && exit 0
branch="$(git symbolic-ref --short HEAD 2>/dev/null || echo "")"
py_files="$(git diff --cached --name-only -- '*.py')"
[ -z "$py_files" ] && exit 0

case "$branch" in
    feature/demo|scenario/hook-retry-succeeds|scenario/unrelated-not-swept)
        # Formatter simulation: fails once, reformats, succeeds on retry.
        marker="$(git rev-parse --git-dir)/hook-fired-once-${branch//\//_}"
        if [ ! -e "$marker" ]; then
            touch "$marker"
            for f in $py_files; do
                echo "# reformatted-by-hook" >> "$f"
            done
            echo "pre-commit [$branch]: reformatted staged .py file(s), failing this attempt" >&2
            exit 1
        fi
        rm -f "$marker"
        exit 0
        ;;
    scenario/hook-fails-no-modify)
        # A hook that rejects the commit and changes nothing on disk.
        echo "pre-commit [$branch]: rejecting commit outright, no files touched" >&2
        exit 1
        ;;
    scenario/hook-always-fails-modifies)
        # A hook that "fixes" something every single time but never accepts
        # the result -- simulates a formatter that never converges.
        for f in $py_files; do
            echo "# reformatted-attempt-$$-$RANDOM" >> "$f"
        done
        echo "pre-commit [$branch]: reformatted again, still rejecting (never converges)" >&2
        exit 1
        ;;
    *)
        exit 0
        ;;
esac
HOOK
chmod +x .git/hooks/pre-commit

# Unstaged changes on two files, for mfixupa to sort out on feature/demo:
#   greeting.py  -> touched by exactly 1 real commit ahead of master
#   mathutils.py -> touched by "add math utils" AND the fixup! above, but
#                   fixups are excluded as candidates, so still 1 real
#                   candidate too -- both auto-picked, no picker needed.
# This is the LAST thing done in $WORK -- nothing below switches $WORK away
# from feature/demo, so this dirty state survives for the user to find.
cat >> greeting.py <<'EOF'

def greet_loudly(name):
    return greet(name).upper()
EOF
cat >> mathutils.py <<'EOF'

def mul(a, b):
    return a * b
EOF

# ----------------------------------------------------------------------------
# PART B: one isolated worktree per edge case.
# ----------------------------------------------------------------------------
mkdir -p "$SCEN"

# --- hook rejects once, then succeeds on retry (mfixup, isolated from
#     everything else, a clean single-command demo of the retry path) ---
new_scenario hook-retry-succeeds
cat > widget.py <<'EOF'
def make():
    return "widget"
EOF
git add widget.py
git commit -q -m "add widget"
echo "def make_deluxe(): return make() + ' deluxe'" >> widget.py
git add widget.py

# --- hook always rejects and never modifies anything -> must fail
#     immediately, no pointless retries ---
new_scenario hook-fails-no-modify
cat > util.py <<'EOF'
def helper():
    return 1
EOF
git add util.py
git commit -q -m "add util"
echo "def helper2(): return 2" >> util.py
git add util.py

# --- hook always rejects but DOES modify every time -> retries must give
#     up after the retry budget, not loop forever ---
new_scenario hook-always-fails-modifies
cat > broken.py <<'EOF'
def helper():
    return 1
EOF
git add broken.py
git commit -q -m "add broken helper"
echo "def helper2(): return 2" >> broken.py
git add broken.py

# --- a hook-triggered retry must not sweep an unrelated file's pre-existing
#     unstaged edit into the fixup commit ---
new_scenario unrelated-not-swept
cat > target.py <<'EOF'
def target():
    return "v1"
EOF
git add target.py
git commit -q -m "add target"
cat > other.py <<'EOF'
def other():
    return "v1"
EOF
git add other.py
git commit -q -m "add other"
echo "def target2(): return 'v2'" >> target.py
git add target.py                                                 # what we're fixing up
echo "# an unrelated, pre-existing, NOT-staged edit" >> other.py   # must survive untouched

# --- mfixup refuses when nothing is staged ---
new_scenario mfixup-requires-staged
cat > readme_note.txt <<'EOF'
nothing staged here
EOF
git add readme_note.txt
git commit -q -m "add note"

# --- mfixupa refuses when something is already staged ---
new_scenario mfixupa-requires-clean-stage
cat > a.txt <<'EOF'
a
EOF
git add a.txt
git commit -q -m "add a"
echo "unstaged change" >> a.txt
cat > staged-already.txt <<'EOF'
this is staged before mfixupa runs
EOF
git add staged-already.txt   # deliberately pre-staged, unrelated to a.txt

# --- a file only touched by a commit that predates the branch point ->
#     mfixupa must SKIP it, never reach back to a commit that's already
#     on master. only_in_base.txt already exists on master itself (see origin
#     setup above) -- this scenario just advances history with an
#     unrelated commit, then edits that pre-existing file. ---
new_scenario skip-file-not-ahead-of-branch
cat > unrelated_commit.txt <<'EOF'
just advances history so only_in_base.txt isn't the branch's own tip
EOF
git add unrelated_commit.txt
git commit -q -m "advance history"
echo "edited but was never touched by any commit ahead of master" >> only_in_base.txt

# --- a file with unstaged changes that TWO different commits ahead of the
#     default branch both touched -> mfixupa itself must open a picker
#     (not just mfixup) ---
new_scenario mfixupa-multi-candidate
cat > shared.txt <<'EOF'
v1
EOF
git add shared.txt
git commit -q -m "add shared v1"
echo v2 >> shared.txt
git add shared.txt
git commit -q -m "add shared v2"
echo v3 >> shared.txt   # unstaged; both commits above touched shared.txt

# --- a realistic combined mfixupa run: one file with an unambiguous
#     target (auto), one with multiple candidates (picker), one with no
#     candidate ahead of the branch (skipped -- only_in_base.txt is baked
#     into master's own history, see origin setup above), and one
#     untracked file that must be completely ignored -- all at once ---
new_scenario mfixupa-mixed-batch
cat > alpha.txt <<'EOF'
a1
EOF
git add alpha.txt
git commit -q -m "add alpha"
cat > beta.txt <<'EOF'
b1
EOF
git add beta.txt
git commit -q -m "add beta v1"
echo b2 >> beta.txt
git add beta.txt
git commit -q -m "add beta v2"
echo a2 >> alpha.txt                       # 1 candidate -> auto-fixup
echo b3 >> beta.txt                        # 2 candidates -> picker
echo edited >> only_in_base.txt            # 0 candidates -> skipped
echo "never added to git" > brand_new.txt  # untracked -> ignored entirely

# --- msquash must refuse (not silently flatten) when a merge commit sits
#     ahead of the default branch ---
new_scenario merge-commit-guard
cat > x.txt <<'EOF'
x
EOF
git add x.txt
git commit -q -m "add x"
echo "fix1" >> x.txt
git add x.txt
git commit -q -m "fixup! add x"
echo "fix2" >> x.txt
git add x.txt
git commit -q -m "fixup! add x"
git checkout -q -b scenario/merge-commit-guard-side master
echo "y" > y.txt
git add y.txt
git commit -q -m "add y (side branch)"
git checkout -q scenario/merge-commit-guard
git merge -q --no-edit scenario/merge-commit-guard-side

unset GITM_DEMO_SETUP  # from here on, the hook behaves for real

cd "$WORK"
echo
echo "Playground ready at: $WORK"
echo

# ============================================================================
# Separate repo: mainline branch is "release/main" (not "master"), a name
# containing a slash. Since default_branch() no longer auto-detects
# anything from origin/HEAD, the ONLY way to target this is `git config
# gitm.default-branch release/main` (or --branch release/main every time) --
# this confirms that config value flows through unmangled.
# ============================================================================

mkdir -p "$SLASH_ORIGIN"
git -C "$SLASH_ORIGIN" init -q -b release/main
git_id "$SLASH_ORIGIN"
echo "hello" > "$SLASH_ORIGIN/f.txt"
git -C "$SLASH_ORIGIN" add -A
git -C "$SLASH_ORIGIN" commit -q -m "initial commit"

git clone -q "$SLASH_ORIGIN" "$SLASH_WORK"
git_id "$SLASH_WORK"
git -C "$SLASH_WORK" config gitm.default-branch release/main
git -C "$SLASH_WORK" checkout -q -b feature/x
echo "world" >> "$SLASH_WORK/f.txt"
git -C "$SLASH_WORK" add -A
git -C "$SLASH_WORK" commit -q -m "touch f"

echo "Slash-branch playground ready at: $SLASH_WORK"
echo

# ============================================================================
# A repo with NO remote at all -- no `git clone`, no `origin`. The most
# common real-world reason upstream_ref()'s local-branch fallback matters:
# plenty of local/offline repos never had a remote configured.
# ============================================================================

mkdir -p "$NO_REMOTE_REPO"
git -C "$NO_REMOTE_REPO" init -q -b master
git_id "$NO_REMOTE_REPO"
echo "hello" > "$NO_REMOTE_REPO/f.txt"
git -C "$NO_REMOTE_REPO" add -A
git -C "$NO_REMOTE_REPO" commit -q -m "initial commit"
git -C "$NO_REMOTE_REPO" checkout -q -b feature
echo "world" >> "$NO_REMOTE_REPO/f.txt"
git -C "$NO_REMOTE_REPO" add -A
git -C "$NO_REMOTE_REPO" commit -q -m "touch f"
echo "second file" > "$NO_REMOTE_REPO/g.txt"
git -C "$NO_REMOTE_REPO" add -A
git -C "$NO_REMOTE_REPO" commit -q -m "touch g"
echo "unstaged for mfixupa" >> "$NO_REMOTE_REPO/g.txt"

echo "No-remote playground ready at: $NO_REMOTE_REPO"
echo
echo "=================================================================="
echo " MANUAL CHECKLIST -- eyeball each step, this is the whole point"
echo "=================================================================="
cat <<CHECKLIST

------------------------------------------------------------------
PART A -- everything working normally
------------------------------------------------------------------

  cd "$WORK"    # already checked out on feature/demo, dirty as described

1) git mlog
   Expect: 4 commits ahead of master (add greeting, add math utils,
   add config, fixup! add math utils), newest first, decorated/graphed.

2) git status
   Expect: greeting.py and mathutils.py modified, unstaged. Nothing staged.

3) git mfixupa
   Expect: BOTH files' commits fail once each ("pre-commit [feature/demo]:
   reformatted staged .py file(s)...") then a "-- commit hook failed ...
   re-staging and retrying" message from .git_tools, then succeed. Both
   land as their OWN "fixup!" commits -- not squashed into their targets
   (no --squash was passed).

4) git log --oneline
   Expect: two new "fixup! add greeting" / "fixup! add math utils"
   commits on top; greeting.py's content includes "# reformatted-by-hook".

5) Give msquash something real to do:
     echo "def div(a, b): return a / b" >> mathutils.py
     git add mathutils.py
     git mfixup
   Expect: a picker (fzf, or a numbered prompt if fzf isn't installed)
   listing "add config", "add math utils", "add greeting" -- fixup
   commits excluded. Pick "add math utils". The hook fires+retries here
   too, same reason as step 3.

6) git msquash
   Expect:
     - a message condensing 3 "fixup! add math utils" commits into one
       (from setup, from step 3, and from step 5) -- combined content
       should have sub/mul/div all present.
     - a warning that condensing reorders the "fixup! add greeting"
       commit (it sits between two of the three) -- read it and judge
       whether that reordering is the one you'd expect.
     - git log --oneline afterwards: only ONE "fixup! add math utils"
       commit remains.

7) git mbranch
   Expect: feature/demo, deadbeef, scratch/notes, master listed
   newest-first, "*" marking whichever branch you're actually on.
   ("deadbeef" being present -- not filtered out as if it looked like a
   detached-HEAD SHA -- is itself one of the edge cases; see #16.)

------------------------------------------------------------------
PART B -- edge cases (each is its own worktree/branch off master; none of
these depend on each other or on Part A's state)
------------------------------------------------------------------

8) Hook rejects once, then succeeds on retry, in isolation:
     cd "$SCEN/hook-retry-succeeds"
     git mfixup
   Pick "add widget". Expect one failure message, one "re-staging and
   retrying" message, then success as its own fixup! commit. git log
   --oneline: fixup! commit present, not squashed.

9) Hook rejects and changes NOTHING on disk -> must fail immediately,
   no pointless retry:
     cd "$SCEN/hook-fails-no-modify"
     git mfixup
   Pick "add util". Expect: ONE hook failure message, then .git_tools
   reports "... failed and left no working-tree changes to retry with"
   and exits non-zero. git log --oneline: NO fixup! commit was created.
   git status: util.py is still staged, untouched, exactly as you left it.

10) Hook rejects AND modifies every single time (never converges) ->
    retries must give up, not loop forever:
      cd "$SCEN/hook-always-fails-modifies"
      git mfixup
    Pick "add broken helper". Expect: 3 failure messages (default retry
    budget), then "kept failing after 3 attempts ... fix the hook
    failure manually", non-zero exit. git log --oneline: no commit was
    created. broken.py is left staged with all 3 rounds of the hook's
    edits piled up in it -- worth eyeballing that nothing got lost, just
    never committed.

11) A hook-triggered retry must not sweep in an unrelated unstaged file:
      cd "$SCEN/unrelated-not-swept"
      git mfixup
    Pick "add target". Expect the usual fail-once-then-succeed retry on
    target.py. Afterward:
      git show --stat HEAD        # must list ONLY target.py
      git status --short          # other.py must still show " M other.py"
                                   #   (untouched, still unstaged)
    If other.py's edit ever shows up inside the fixup commit, that's the
    bug this scenario exists to catch.

12) mfixup refuses when nothing is staged:
      cd "$SCEN/mfixup-requires-staged"
      git mfixup
    Expect an immediate "nothing is staged; git add your changes first"
    error, no picker shown, exit non-zero.

13) mfixupa refuses when something is already staged:
      cd "$SCEN/mfixupa-requires-clean-stage"
      git mfixupa
    Expect an immediate "there are already staged changes; unstage them
    first..." error, exit non-zero, nothing committed.

14) A file only touched by a commit that predates the branch point ->
    mfixupa must SKIP it, never reach back to a commit already on master:
      cd "$SCEN/skip-file-not-ahead-of-branch"
      git mfixupa
    Expect it to report "no file could be matched to a commit; nothing
    was fixed up" (only_in_base.txt is the only unstaged file here, and
    the only commit that touches it -- "add file only touched before
    the branch point" -- is on master itself, not ahead of it). Afterward:
      git log --oneline               # unchanged, no fixup! commit made
      git status --short              # only_in_base.txt still shows modified, untouched

15) A file touched by TWO different commits ahead of the default branch
    -> mfixupa itself must open a picker, not just report ambiguity:
      cd "$SCEN/mfixupa-multi-candidate"
      git mfixupa
    Expect a picker (fzf, or numbered prompt) listing "add shared v2"
    and "add shared v1" for shared.txt, labeled with the "fixing up:"
    header from earlier. Pick either one and confirm afterward that
    exactly one new "fixup! add shared v*" commit was created (git log
    --oneline) targeting whichever you picked.

16) A single mfixupa run with everything mixed together at once: one
    unambiguous file (auto), one ambiguous file (picker), one file with
    no candidate ahead of the branch (skipped), and one untracked file
    that must be completely ignored:
      cd "$SCEN/mfixupa-mixed-batch"
      git status --short           # note brand_new.txt shows "??" (untracked)
      git mfixupa
    Expect:
      - alpha.txt fixed up automatically into "add alpha", no picker.
      - a picker for beta.txt listing "add beta v2"/"add beta v1" -- pick
        either.
      - a "-- skipped (no commit ahead of ... touches them): only_in_base.txt"
        message.
      - brand_new.txt is never mentioned anywhere in the output.
    Afterward:
      git log --oneline             # alpha + beta fixups present, exactly
                                     #   2 new fixup! commits, nothing for
                                     #   only_in_base.txt or brand_new.txt
      git status --short            # only_in_base.txt still modified,
                                     #   brand_new.txt still "??", both
                                     #   exactly as you left them
      cat brand_new.txt              # untouched, still there

17) msquash refuses (rather than silently flattening history) when a
    merge commit sits ahead of the default branch:
      cd "$SCEN/merge-commit-guard"
      git log --oneline --graph   # note the merge commit in the graph
      git rev-parse HEAD          # note this, compare after
      git msquash
    There are two "fixup! add x" commits here that would normally get
    condensed -- expect msquash to instead print an error mentioning
    "merge commit" and refuse, and HEAD (git rev-parse HEAD again) to be
    completely unchanged.

18) A branch literally named like a hex SHA must still appear in
    mbranch, not get filtered out as if it were a detached-HEAD SHA:
      cd "$WORK"
      git mbranch
    Expect "deadbeef" in the list (see step 7 -- it was checked out
    once during setup). If it's missing, that's the bug this scenario
    exists to catch.

------------------------------------------------------------------
PART C -- a non-master default branch, set via config (separate repo)
------------------------------------------------------------------

19) This repo's mainline is "release/main", not "master" -- and since
    branch resolution is no longer auto-detected from anything on the
    remote, "git config gitm.default-branch release/main" (already set
    for you here) is the only thing making that work:
      cd "$SLASH_WORK"
      git config --get gitm.default-branch   # confirm: release/main
      git mlog
      echo "typo fix" >> f.txt
      git add f.txt
      git mfixup
    Expect git mlog to correctly show "touch f" as the one commit ahead
    of origin/release/main. Pick "touch f" in the mfixup picker (there's
    only one candidate). If the config value were being mangled (e.g.
    truncated at the slash), this would instead fail with something like
    "'origin/main' does not exist".

    Sanity check the config override actually matters -- this repo has
    no "master" branch at all, remote or local, so asking for it
    explicitly should fail:
      git mlog --branch master
    Expect "neither 'origin/master' nor local 'master' exists".

------------------------------------------------------------------
PART D -- no remote at all (separate repo)
------------------------------------------------------------------

20) No "git clone", no "origin" -- this repo was just "git init"'d. There's
    no "origin/master" for any command to compare against, only a local
    "master" branch. Every command must fall back to comparing against
    that local branch instead of erroring:
      cd "$NO_REMOTE_REPO"
      git remote -v                # confirm: genuinely nothing listed
      git mlog
    Expect this to work and show "touch f" and "touch g" -- NOT an error
    about 'origin/master' not existing. Try mfixup too:
      echo "typo fix" >> f.txt
      git add f.txt
      git mfixup
    Pick "touch f" (the only candidate). And mfixupa (g.txt was left
    with an unstaged change from setup):
      git status --short           # g.txt shows modified, unstaged
      git mfixupa
    Expect it to auto-fixup into "touch g", no picker (only one commit
    touched g.txt). All of this should work exactly as it would with a
    real origin/master.

------------------------------------------------------------------
When you're done poking at it:
  rm -rf "$DEST"
------------------------------------------------------------------

CHECKLIST
