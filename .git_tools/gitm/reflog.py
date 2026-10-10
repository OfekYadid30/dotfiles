"""Recently-visited-branch tracking, for mbranch.

Git doesn't keep a dedicated "branch history", but every `checkout`/`switch`
that moves HEAD between branches is recorded in HEAD's reflog. We parse that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .gitrun import capture_lines, run

# e.g. "checkout: moving from main to feature/foo"
_CHECKOUT_RE = re.compile(r"checkout: moving from (?P<from>\S+) to (?P<to>\S+)")


@dataclass
class BranchVisit:
    branch: str
    when: str  # human-readable relative date, e.g. "2 hours ago"


def _is_branch(name: str) -> bool:
    # Reflogs also record moves to bare SHAs (detached HEAD); skip those. A
    # real ref lookup (rather than "looks like a hex string") is required
    # since a branch can legitimately be named e.g. "deadbeef".
    return run(["show-ref", "--verify", "-q", f"refs/heads/{name}"], check=False).ok


def recent_branches(limit: int = 20) -> list[BranchVisit]:
    """Most-recently-visited branches first, deduplicated, newest visit wins."""
    lines = capture_lines(
        ["reflog", "show", "--date=relative", "--format=%gd|%gs", "HEAD"]
    )

    seen: set[str] = set()
    visits: list[BranchVisit] = []
    for line in lines:
        gd, _, subject = line.partition("|")
        match = _CHECKOUT_RE.search(subject)
        if not match:
            continue
        to_branch = match.group("to")
        if to_branch in seen or not _is_branch(to_branch):
            continue
        seen.add(to_branch)
        when_match = re.search(r"\{(.*)\}", gd)
        when = when_match.group(1) if when_match else gd
        visits.append(BranchVisit(branch=to_branch, when=when))
        if len(visits) >= limit:
            break
    return visits
