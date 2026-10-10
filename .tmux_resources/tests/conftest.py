"""Shared fixtures.

There is no packaging step, so tests import ``tmux_sessionizer`` straight from
this directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tmux_sessionizer.builder import SessionBuilder  # noqa: E402
from tmux_sessionizer.tmux import Tmux  # noqa: E402

from .faketmux import FakeTmux  # noqa: E402

#: A real ten-pane layout, copied from the legacy Development session file.
DEV_LAYOUT = (
    "3fcb,224x53,0,0[224x26,0,0{112x26,0,0[112x13,0,0{56x13,0,0,129,55x13,57,0,170},"
    "112x12,0,14,169],111x26,113,0[111x13,113,0{55x13,113,0,133,55x13,169,0,171},"
    "111x12,113,14,168]},224x13,0,27{112x13,0,27,128,111x13,113,27,132},"
    "224x12,0,41{112x12,0,41,130,111x12,113,41,131}]"
)

#: A real four-pane layout, from the legacy Temp session file.
TEMP_LAYOUT = (
    "d330,201x60,0,0{100x60,0,0[100x10,0,0,21,100x49,0,11,25],"
    "100x60,101,0[100x40,101,0,23,100x19,101,41,24]}"
)


@pytest.fixture
def server() -> FakeTmux:
    return FakeTmux()


class FakeClock:
    """A clock that only moves when someone sleeps.

    Pane-readiness polling is time-based, so tests need time they control:
    real sleeps would make the suite slow and a stubbed-out sleep would make
    any deadline unreachable.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


#: A plausible $TMUX value, for the code paths that only run inside tmux.
INSIDE_TMUX = {"TMUX": "/private/tmp/tmux-501/default,3626,1"}


@pytest.fixture
def tmux(server: FakeTmux, clock: FakeClock) -> Tmux:
    """A Tmux client wired to the fake server and a clock the test drives."""
    return Tmux(runner=server, sleep=clock.sleep, monotonic=clock.monotonic, env={})


@pytest.fixture
def tmux_inside(server: FakeTmux, clock: FakeClock) -> Tmux:
    """As :func:`tmux`, but running inside a tmux client."""
    return Tmux(
        runner=server, sleep=clock.sleep, monotonic=clock.monotonic, env=dict(INSIDE_TMUX)
    )


@pytest.fixture
def builder(tmux: Tmux) -> SessionBuilder:
    return SessionBuilder(tmux, terminal_size=lambda: (120, 40))
