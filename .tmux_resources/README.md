# tmux_sessionizer

Builds tmux sessions from declarative TOML files, and applies pane layouts.

Lives in `~/.tmux_resources`. Replaces the two shell scripts that used to be
`~/.tmux_sessionizer` and `~/.tmux_layout_manager`, archived in
`~/.tmux_resources/legacy/`.

Standard library only, Python 3.8 or newer. Nothing to install.

---

## Contents

- [Quick start](#quick-start)
- [Commands](#commands)
- [Writing a session file](#writing-a-session-file)
  - [`[session]`](#session)
  - [`[[windows]]`](#windows)
  - [`[[windows.panes]]`](#windowspanes)
  - [Layouts](#layouts)
  - [Worked examples](#worked-examples)
- [How it behaves](#how-it-behaves)
- [Key bindings](#key-bindings)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

---

## Quick start

Session files live in **`~/.tmux_resources/`**, one per workspace, named after
the session in lowercase:

```
~/.tmux_resources/
├── development.tmux.toml
├── home.tmux.toml
├── ori.tmux.toml
└── research.tmux.toml
```

Write one:

```toml
# ~/.tmux_resources/blog.tmux.toml
[session]
name = "blog"
path = "~/writing/blog"

[[windows]]
name = "editor"
commands = ["nvim ."]

[[windows]]
name = "shell"
```

Check it, then open it:

```console
$ tmux_sessionizer check blog
  + /Users/you/.tmux_resources/blog.tmux.toml: 'blog' - 2 window(s), 2 pane(s)

$ tmux_sessionizer session ~/.tmux_resources/blog.tmux.toml
  + created session 'blog' (2 window(s)), attached
```

Run it again and it attaches to what is already there instead of rebuilding.

`tmux_sessionizer` here is `~/.tmux_resources/bin/tmux_sessionizer`. Add that `bin` to
your `$PATH`, or call it by full path as the key bindings do.

---

## Commands

### `session <file>` — create or attach

```console
$ tmux_sessionizer session ~/.tmux_resources/development.tmux.toml
$ tmux_sessionizer session development           # bare name: looked up in ~/.tmux_resources
$ tmux_sessionizer session development --no-attach
$ tmux_sessionizer session development --keep-scratch
```

If the session already exists it is attached, never rebuilt — so a key binding
is safe to press twice.

| flag | effect |
| --- | --- |
| `--no-attach` | build it, but stay where you are |
| `--keep-scratch` | do not clean up tmux's auto-named `0`, `1`, … sessions |

### `layout <layout>` — arrange the current window

Adds panes until the window matches the layout, then applies it.

```console
$ tmux_sessionizer layout "d330,201x60,0,0{100x60,0,0[...]}"   # count comes from the layout
$ tmux_sessionizer layout tiled -n 4                            # builtins need -n
$ tmux_sessionizer layout main-vertical -n 3 -t @7              # a specific window
$ tmux_sessionizer layout tiled -n 2 -c ~/projects/x            # cwd for the new panes
```

It never closes panes. If the window already has more than the layout needs it
says so and stops, rather than guessing which one you meant to lose.

### `layout_capture` — copy a layout you arranged by hand

Split and resize a window until it looks right, then:

```console
$ tmux_sessionizer layout_capture
d330,201x60,0,0{100x60,0,0[100x10,0,0,21,100x49,0,11,25],...}
```

Paste that into a session file as `layout = "…"`. Bound to `prefix m-P`, which
copies it straight to the clipboard.

### `check [<file>…]` — validate without touching tmux

```console
$ tmux_sessionizer check                    # every file in ~/.tmux_resources
$ tmux_sessionizer check blog
$ tmux_sessionizer check --no-path-check    # skip "does this directory exist"
```

Exits non-zero if anything is wrong. Safe to run anywhere; it starts no server.

### `list` — what is installed

```console
$ tmux_sessionizer list
development      /Users/you/.tmux_resources/development.tmux.toml
home             /Users/you/.tmux_resources/home.tmux.toml
```

---

## Writing a session file

A file describes one session: its name, where it starts, and the windows and
panes inside it. The whole format is three kinds of table.

```toml
[session]                 # exactly one
[[windows]]               # one or more, in order
  [[windows.panes]]       # zero or more inside each window, in order
```

Unknown keys are **errors, not warnings**. A silently ignored typo in a dotfile
is a bad afternoon, so `commnads = [...]` fails loudly and lists what was
allowed.

### `[session]`

| key | type | required | meaning |
| --- | --- | --- | --- |
| `name` | string | yes | the tmux session name |
| `path` | string | yes | starting directory for every window |
| `setup` | list of strings | no | commands run in **every pane of every window** |

```toml
[session]
name = "Development"
path = "~/Development"
setup = ["source .venv/bin/activate"]
```

`name` cannot contain whitespace, `.` or `:` — tmux uses those to separate
session, window and pane in a target.

`path` expands `~` and `$VARS`, and must exist (`check --no-path-check` skips
that when validating a file for another machine).

`setup` runs first in each pane, before that pane's own commands, and reaches
panes the file never mentions by name.

### `[[windows]]`

One table per window, in the order they should appear.

| key | type | required | meaning |
| --- | --- | --- | --- |
| `name` | string | yes | window name (duplicates are fine) |
| `commands` | list of strings | no | shorthand for a one-pane window |
| `panes` | tables | no | see below; mutually exclusive with `commands` |
| `layout` | string | no | builtin name or a captured layout |
| `path` | string | no | overrides `session.path` for this window |
| `focus` | bool | no | select this window on attach (default: the first) |

```toml
[[windows]]
name = "editor"
commands = ["nvim ."]        # one pane, two commands
```

A window with no `commands` and no `panes` is a single empty shell — which is
all three windows of the `Home` workspace.

### `[[windows.panes]]`

One table per pane. **Panes are positional**: the first block is the first pane,
the second is the second, and so on.

| key | type | required | meaning |
| --- | --- | --- | --- |
| `commands` | list of strings | no | typed into this pane, in order |
| `at` | integer ≥ 1 | no | address a pane by position instead |
| `focus` | bool | no | select this pane within its window |

```toml
[[windows]]
name = "grid"
layout = "tiled"

  [[windows.panes]]
  commands = ["btop"]
  [[windows.panes]]
  commands = ["tail -f log"]
```

**`at` is for sparse windows.** When a ten-pane layout has only two panes you
care about, listing eight empty blocks to reach the tenth is noise:

```toml
  [[windows.panes]]
  at = 1
  commands = ["ipython"]

  [[windows.panes]]
  at = 6
  commands = ["btop"]
```

Rules for `at`:

- It counts from **1**, always, whatever the server's `pane-base-index` is. A
  file written on one machine works on another.
- **Either every pane block sets it, or none do.** Mixing the two makes the
  order ambiguous, so it is rejected.
- The window grows to at least the highest `at`, so `at = 6` guarantees six
  panes exist.

### Layouts

`layout` takes either a builtin name —

`even-horizontal`, `even-vertical`, `main-horizontal`, `main-vertical`, `tiled`

— or a layout string captured from a real window:

```toml
layout = "d330,201x60,0,0{100x60,0,0[100x10,0,0,21,100x49,0,11,25],...}"
```

A captured layout **sets the pane count**: the window is grown to exactly the
number of panes the layout describes, then the layout is applied, so the result
is pixel-for-pixel what you arranged. A builtin name implies no count, so the
window is only as big as your pane blocks make it.

To get one: arrange a window by hand, then `prefix m-P` (or run
`tmux_sessionizer layout_capture`) and paste.

Layout strings are checksummed, and `check` verifies it — a truncated or
hand-edited layout is caught when you validate the file, rather than as an
opaque `invalid layout` from tmux later.

### Worked examples

**A single editor window** (`~/.tmux_resources/research.tmux.toml`):

```toml
[session]
name = "Research"
path = "~/research"

[[windows]]
name = "nvim"
commands = ["nvim ."]

[[windows]]
name = "generic"

[[windows]]
name = "generic"
```

**A sparse ten-pane grid** (`development.tmux.toml`, abridged):

```toml
[session]
name = "Development"
path = "~/Development"

[[windows]]
name = "nvim"
commands = ["nvim ."]

[[windows]]
name = "research"
layout = "3fcb,224x53,0,0[224x26,0,0{112x26,0,0[...]}]"   # 10 panes

  [[windows.panes]]
  at = 1
  commands = ["ipython"]

  [[windows.panes]]
  at = 6
  commands = ["ipython"]
```

**Per-window directories and focus:**

```toml
[session]
name = "review"
path = "~/code"

[[windows]]
name = "api"
path = "~/code/api"
commands = ["nvim ."]

[[windows]]
name = "web"
path = "~/code/web"
focus = true                 # attach here, not the first window

  [[windows.panes]]
  commands = ["npm run dev"]
  [[windows.panes]]
  commands = ["npm test -- --watch"]
  focus = true               # cursor lands in the test pane
```

---

## How it behaves

- **Attach if it exists.** `session` never rebuilds a session that is already
  there, so pressing a key binding twice is harmless and never loses work.
- **Atomic.** The session is built detached; if any step fails it is killed
  rather than left half-built for the next attach to inherit.
- **Balanced growth.** Every split is preceded by a re-tile, because tmux
  refuses to split a pane that is already too small — without it, a ten-pane
  layout fails around pane five.
- **Waits for the shell.** Commands are sent only once a pane's output has
  stopped changing, so keys do not land while the prompt is still being drawn.
- **Prunes scratch sessions.** After attaching, sessions tmux auto-named `0`,
  `1`, … are killed. `--keep-scratch` turns that off.
- **Exact targets.** Sessions are addressed as `=name`, so `work` never
  resolves to `workshop`.
- **Errors reach you.** Key bindings run through `run-shell`, which discards
  stderr, so failures are also written to tmux's status line.
- **Sizing.** A session is created at the attached client's size — but only
  when run from inside tmux; from outside, `#{client_width}` describes an
  unrelated terminal, so the local terminal's size is used instead.

---

## Key bindings

From `~/.tmux.conf.personal`:

| key | does |
| --- | --- |
| `prefix D` | Development |
| `prefix U` | Home |
| `prefix I` | Insights |
| `prefix T` | ori |
| `prefix C` | Current |
| `prefix R` | Research |
| `prefix m-U` / `m-I` / `m-O` | three ad-hoc five-pane layouts |
| `prefix m-P` | copy this window's layout to the clipboard |

Each workspace key names its file directly:

```tmux
bind-key D run-shell -b "~/.tmux_resources/bin/tmux_sessionizer session ~/.tmux_resources/development.tmux.toml"
```

---

## Troubleshooting

**`no session named 'x'`** — the lookup takes the name, lowercases it, and adds
`.tmux.toml`. A session named `ori` needs `ori.tmux.toml`. The error lists every
path it tried.

**`unknown key(s) 'commnads'`** — a typo; the message lists the allowed keys for
that table.

**`layout defines 10 panes but the config drives 11`** — an `at` is past the end
of the layout. Either lower it or capture a bigger layout.

**`no room for pane 6 of 10 in window 'w'. The session is 20x8. The layout was
recorded at 224x53.`** — the terminal is too small for that layout.

**`the layout describes 4 panes, but 2 were requested`** — `layout -n` disagrees
with the layout string. tmux would accept this silently and do nothing, so it is
refused here instead.

**`not running inside tmux; name a window with --target`** — `layout` and
`layout_capture` act on the current window. From outside tmux there is no such
thing, and tmux would happily answer with someone else's window.

**Keys typed into the wrong place, or a stray `%`** — that `%` is your shell
printing its default prompt before `.zshrc` finishes; it appears with a plain
`tmux split-window` too.

---

## Development

The code is in `~/.tmux_resources/tmux_sessionizer/`.

| module | responsibility |
| --- | --- |
| `layout.py` | pure string logic over layout descriptors — pane counts, checksums |
| `spec.py` | the session model — frozen dataclasses, no I/O |
| `config.py` | TOML text → validated spec, with file/line errors |
| `_toml.py` | a minimal TOML reader, used only when `tomllib` is missing |
| `discovery.py` | a name → a file in `~/.tmux_resources` |
| `tmux.py` | the only module that speaks to a tmux server |
| `builder.py` | spec → live session |
| `manager.py` | the `layout` and `layout_capture` commands |
| `cli.py` | argument parsing and exit codes |

Everything that touches the outside world goes through `tmux.Tmux`, which wraps
an injectable runner. `tests/faketmux.py` is an in-memory tmux server that plugs
into that seam, so the whole pipeline is tested without a tmux process —
including the failures that matter: splits that run out of room, layouts whose
pane count does not match the window, panes that are still booting.

```console
$ python3 -m pytest                  # everything
$ python3 -m pytest -m 'not slow'    # skip the tests that drive a real tmux
```

`tests/test_real_tmux.py` drives an actual tmux binary, because a fake agrees
with the code by construction and that is exactly how a wrong model hides a bug.
It runs on its own server (`tmux -L tmux-sessionizer-test`, via `$TMUX_SESSIONIZER_SOCKET`) and
never touches live sessions.

`tests/test_toml.py` is differential: every input is parsed by both `_toml` and
`tomllib`, and the results must match, so the Python you develop on and the
Python in the offline bundle cannot drift apart.
`tests/test_py38_compat.py` checks the sources statically against 3.8 grammar
and standard library, since there is no 3.8 interpreter here to run them under.

### Where things live

| | |
| --- | --- |
| code | `~/.tmux_resources/tmux_sessionizer/`, launcher `~/.tmux_resources/bin/tmux_sessionizer` |
| session files | `~/.tmux_resources/*.tmux.toml` |
| key bindings | `~/.tmux.conf.personal` |
| the old bash implementation | `~/.tmux_resources/legacy/` |

Override the session directory with `$TMUX_SESSIONIZER_SESSIONS` (`:`-separated, like
`$PATH`; earlier directories win).

### Compatibility

`~/.tmux_sessionizer` and `~/.tmux_layout_manager` are thin shims that call this
and accept the old arguments, including legacy `*.tmux-session.conf` paths whose
basename is read as the session name. The old `Temp` workspace is called `ori`,
which is the session name it always had.
