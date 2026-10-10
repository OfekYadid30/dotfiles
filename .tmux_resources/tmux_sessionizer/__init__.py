"""tmux_sessionizer - build tmux sessions from declarative TOML files.

Replaces the two shell scripts ``~/.tmux_sessionizer`` and
``~/.tmux_layout_manager`` with one package. The split mirrors what actually
varies:

* :mod:`tmux_sessionizer.layout`   - pure string logic over tmux layout descriptors.
* :mod:`tmux_sessionizer.spec`     - the in-memory session model (no I/O, no tmux).
* :mod:`tmux_sessionizer.config`   - TOML text -> validated spec, with file/line errors.
* :mod:`tmux_sessionizer.tmux`     - the only module that speaks to a tmux server.
* :mod:`tmux_sessionizer.builder`  - turns a spec into a live session.
* :mod:`tmux_sessionizer.manager`  - the standalone "ensure N panes, apply layout" tool.

Everything that touches the outside world goes through
:class:`tmux_sessionizer.tmux.Tmux`, which wraps an injectable ``Runner``. That is the
single seam the tests replace, so the whole build pipeline is exercised without
a tmux server.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
