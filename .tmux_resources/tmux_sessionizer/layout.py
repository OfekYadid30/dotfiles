"""Layout descriptors.

Pure string logic, no tmux and no I/O, so the fiddly parts - counting the panes
a serialized layout defines, and telling a layout apart from a typo - are unit
testable on their own.

tmux understands two kinds of layout:

* a builtin name, e.g. ``tiled`` or ``main-vertical``;
* a *serialized* layout as produced by ``#{window_layout}``, e.g.
  ``3fcb,224x53,0,0[224x26,0,0{112x26,0,0,1,111x26,113,0,2},224x26,0,27,3]``.

A serialized layout is a checksum, then a tree of nodes. A node is
``<w>x<h>,<x>,<y>`` followed by ``,<pane-id>`` for a leaf, ``{...}`` for a
left-to-right split, or ``[...]`` for a top-to-bottom split. Counting leaves
therefore counts panes.
"""

from __future__ import annotations

import re

from .errors import LayoutError

#: Layout names tmux resolves itself.
BUILTIN_LAYOUTS = frozenset(
    {
        "even-horizontal",
        "even-vertical",
        "main-horizontal",
        "main-vertical",
        "tiled",
    }
)

#: A leaf node: dimensions, position and a pane id. Container nodes are not
#: matched because they are followed by ``{`` or ``[`` rather than a number.
_PANE_NODE = re.compile(r"\d+x\d+,\d+,\d+,\d+")

#: ``<checksum>,<w>x<h>,<x>,<y>`` - enough to distinguish a layout from a name.
_SERIALIZED = re.compile(r"^(?P<checksum>[0-9A-Fa-f]+),(?P<body>(?P<w>\d+)x(?P<h>\d+),\d+,\d+)")


def is_builtin(value: str) -> bool:
    return value in BUILTIN_LAYOUTS


def is_serialized(value: str) -> bool:
    return _SERIALIZED.match(value) is not None


def looks_like_layout(value: str) -> bool:
    return is_builtin(value) or is_serialized(value)


def checksum(body: str) -> str:
    """tmux's layout checksum for *body* (the layout minus its ``csum,`` prefix).

    Ported from ``layout_checksum`` in tmux's ``layout-custom.c``. Verifying it
    turns a truncated or hand-edited layout into a clear config error instead of
    an opaque "invalid layout" from tmux at build time.
    """
    csum = 0
    for char in body:
        csum = (csum >> 1) + ((csum & 1) << 15)
        csum = (csum + ord(char)) & 0xFFFF
    return f"{csum:04x}"


def count_panes(layout: str) -> int:
    """How many panes *layout* describes, or 0 for a builtin name."""
    if is_builtin(layout):
        return 0
    return len(_PANE_NODE.findall(layout))


def natural_size(layout: str) -> tuple[int, int] | None:
    """The window size a serialized layout was recorded at, if it is one."""
    match = _SERIALIZED.match(layout)
    if match is None:
        return None
    return int(match.group("w")), int(match.group("h"))


def validate(layout: str) -> str:
    """Return *layout* unchanged, or raise :class:`LayoutError` explaining why not."""
    value = layout.strip()
    if not value:
        raise LayoutError("Layout is empty.")
    if is_builtin(value):
        return value

    match = _SERIALIZED.match(value)
    if match is None:
        names = ", ".join(sorted(BUILTIN_LAYOUTS))
        raise LayoutError(
            f"Layout is neither a builtin name ({names}) nor a serialized layout "
            f"like '3fcb,224x53,0,0[...]': {value!r}"
        )

    if count_panes(value) <= 0:
        raise LayoutError(f"Serialized layout defines no panes: {value!r}")

    expected = match.group("checksum")
    if len(expected) == 4:
        actual = checksum(value[len(expected) + 1 :])
        if actual != expected.lower():
            raise LayoutError(
                f"Serialized layout checksum is {expected!r} but the body hashes to "
                f"{actual!r}; the layout looks truncated or edited by hand."
            )
    return value
