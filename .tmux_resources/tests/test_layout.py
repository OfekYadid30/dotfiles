"""Layout descriptor logic."""

from __future__ import annotations

import pytest

from tmux_sessionizer import layout
from tmux_sessionizer.errors import LayoutError

from .conftest import DEV_LAYOUT, TEMP_LAYOUT


@pytest.mark.parametrize("name", sorted(layout.BUILTIN_LAYOUTS))
def test_builtin_names_are_recognised(name: str) -> None:
    assert layout.is_builtin(name)
    assert layout.looks_like_layout(name)
    assert not layout.is_serialized(name)
    # A builtin implies no particular pane count.
    assert layout.count_panes(name) == 0


@pytest.mark.parametrize(
    "value",
    ["", "tile", "main vertical", "nvim .", "ipython", "224x53", "zzzz,224x53,0,0"],
)
def test_non_layouts_are_rejected(value: str) -> None:
    assert not layout.looks_like_layout(value)
    with pytest.raises(LayoutError):
        layout.validate(value)


@pytest.mark.parametrize(
    ("value", "panes", "size"),
    [(DEV_LAYOUT, 10, (224, 53)), (TEMP_LAYOUT, 4, (201, 60))],
)
def test_real_layouts_are_measured(value: str, panes: int, size: tuple[int, int]) -> None:
    assert layout.is_serialized(value)
    assert layout.count_panes(value) == panes
    assert layout.natural_size(value) == size
    assert layout.validate(value) == value


def test_container_nodes_are_not_counted_as_panes() -> None:
    # Two leaves inside one horizontal split: the container must not count.
    assert layout.count_panes("bd1d,80x24,0,0{40x24,0,0,1,39x24,41,0,2}") == 2


def test_checksum_matches_tmux() -> None:
    for value in (DEV_LAYOUT, TEMP_LAYOUT):
        prefix, _, body = value.partition(",")
        assert layout.checksum(body) == prefix


def test_truncated_layout_is_caught_by_its_checksum() -> None:
    broken = DEV_LAYOUT.replace("224x53", "224x54", 1)
    with pytest.raises(LayoutError, match="checksum"):
        layout.validate(broken)


def test_serialized_layout_without_panes_is_rejected() -> None:
    body = "80x24,0,0"
    with pytest.raises(LayoutError, match="no panes"):
        layout.validate(f"{layout.checksum(body)},{body}")


def test_validate_trims_surrounding_whitespace() -> None:
    assert layout.validate("  tiled  ") == "tiled"


def test_natural_size_is_none_for_builtins() -> None:
    assert layout.natural_size("tiled") is None
