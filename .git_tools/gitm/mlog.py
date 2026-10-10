"""Shared implementation behind `git mlog` / `git mlogf`.

Both commands show the same thing -- commits HEAD has ahead of the default
branch -- differing only in whether each commit's changed files are listed
too. That's a single boolean, so both bin/ scripts just call show_log()
with different defaults rather than duplicating the git-invocation logic.

Rather than styling git's own `--oneline --graph --stat` output, we ask git
for raw fields (and `--numstat` per-file counts) and lay the lines out
ourselves. That gives full control over the look:
  - no `HEAD -> <branch>` / `<branch>` decoration on the tip -- it's always
    the current branch, so it's just noise; other refs (origin/<branch>,
    tags, other local branches) are kept, since those carry information
  - no graph column (the range is normally linear); merge commits are
    marked with a "merge" tag instead
  - file names colored and aligned, with green/red +/- counts per file
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cli import colorize
from .gitrun import run, try_capture
from .pager import print_or_page
from .refs import default_branch, upstream_ref

# ASCII record/unit separators: can't appear in a subject line, so splitting
# on them is unambiguous (unlike spaces or tabs).
_RS = "\x1e"
_US = "\x1f"
_FORMAT = _US.join(["%h", "%s", "%ar", "%D", "%p"])

HASH_COLOR = "33"      # yellow
REF_COLOR = "36"       # cyan
MERGE_COLOR = "35"     # magenta
FILE_COLOR = "34"      # blue
ADD_COLOR = "32"       # green
DEL_COLOR = "31"       # red
DIM = "2"


@dataclass
class FileChange:
    path: str
    added: int | None    # None for binary files (numstat reports "-")
    deleted: int | None


@dataclass
class LogEntry:
    short: str
    subject: str
    when: str
    refs: list[str]
    is_merge: bool
    files: list[FileChange] = field(default_factory=list)


def _visible_refs(decoration: str, current: str) -> list[str]:
    """Drop the decorations that only restate "this is where you are":
    `HEAD -> <branch>`, a bare `HEAD`, the current branch, and `<remote>/HEAD`.
    """
    refs = []
    for ref in filter(None, (r.strip() for r in decoration.split(","))):
        if ref.startswith("HEAD") or ref == current or ref.endswith("/HEAD"):
            continue
        refs.append(ref)
    return refs


def _parse_numstat(line: str) -> FileChange | None:
    parts = line.split("\t", 2)
    if len(parts) != 3:
        return None
    added, deleted, path = parts
    return FileChange(
        path=path,
        added=int(added) if added.isdigit() else None,
        deleted=int(deleted) if deleted.isdigit() else None,
    )


def _parse_log(output: str, current: str) -> list[LogEntry]:
    entries = []
    for record in filter(None, output.split(_RS)):
        header, _, body = record.partition("\n")
        short, subject, when, decoration, parents = header.split(_US)
        entry = LogEntry(
            short=short,
            subject=subject,
            when=when,
            refs=_visible_refs(decoration, current),
            is_merge=len(parents.split()) > 1,
        )
        entry.files = [c for c in map(_parse_numstat, body.splitlines()) if c]
        entries.append(entry)
    return entries


def _counts(added: int | None, deleted: int | None) -> str:
    if added is None:
        return colorize("binary", DIM)
    parts = []
    if added:
        parts.append(colorize(f"+{added}", ADD_COLOR))
    if deleted:
        parts.append(colorize(f"-{deleted}", DEL_COLOR))
    return " ".join(parts)


def _format_header(entry: LogEntry, when_width: int) -> str:
    # Date goes before the subject (padded to a common width) so subjects
    # all start in the same column regardless of their length.
    parts = [
        colorize(entry.short, HASH_COLOR),
        colorize(entry.when.ljust(when_width), DIM),
        entry.subject,
    ]
    if entry.is_merge:
        parts.append(colorize("merge", MERGE_COLOR))
    if entry.refs:
        parts.append(colorize(f"[{', '.join(entry.refs)}]", REF_COLOR))
    return "  ".join(parts)


def _format_files(entry: LogEntry) -> list[str]:
    # Indent past the hash column so file names sit under the date/subject.
    indent = " " * (len(entry.short) + 2)
    if not entry.files:
        return [indent + colorize("(no file changes)", DIM)]

    width = max(len(f.path) for f in entry.files)
    return [
        f"{indent}{colorize(f.path.ljust(width), FILE_COLOR)}  {_counts(f.added, f.deleted)}".rstrip()
        for f in entry.files
    ]


def show_log(branch: str | None, remote: str, stat: bool) -> None:
    resolved_branch = default_branch(branch, remote)
    ref = upstream_ref(resolved_branch, remote)
    current = try_capture(["symbolic-ref", "--short", "-q", "HEAD"])

    log_args = ["log", f"--format={_RS}{_FORMAT}", "--decorate=short"]
    if stat:
        log_args.append("--numstat")
    log_args.append(f"{ref}..HEAD")

    entries = _parse_log(run(log_args).stdout, current)
    if not entries:
        return

    when_width = max(len(e.when) for e in entries)
    blocks = []
    for entry in entries:
        lines = [_format_header(entry, when_width)]
        if stat:
            lines += _format_files(entry)
        blocks.append("\n".join(lines))

    # With files listed, a blank line between commits keeps each one's file
    # list visually attached to it; without, a tight list reads better.
    separator = "\n\n" if stat else "\n"
    print_or_page(separator.join(blocks) + "\n")
