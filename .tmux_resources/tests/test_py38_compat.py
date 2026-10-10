"""tmux_sessionizer must stay importable on Python 3.8.

The offline bundle targets Ubuntu 20.04, whose ``python3`` is 3.8, and there is
no 3.8 interpreter on the development machine to just run the suite under. So
the sources are checked statically instead: 3.8 grammar, no standard-library
APIs newer than 3.8, and ``from __future__ import annotations`` everywhere so
``X | None`` annotations are never evaluated.

If tmux_sessionizer ever genuinely needs something newer, delete this file on purpose —
do not weaken it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

TARGET = (3, 8)
ROOT = Path(__file__).resolve().parent.parent

SOURCES = sorted(ROOT.glob("tmux_sessionizer/*.py"))

#: Attribute names introduced after 3.8, as {name: version}.
YOUNGER_ATTRS = {
    "removeprefix": "3.9",
    "removesuffix": "3.9",
    "is_relative_to": "3.9",
    "with_stem": "3.9",
    "pairwise": "3.10",
    "bit_count": "3.10",
    "get_type_hints": None,  # fine, listed to document that it was considered
}
YOUNGER_MODULES = {"tomllib": "3.11", "graphlib": "3.9", "zoneinfo": "3.9", "tomli": "3rd-party"}


def annotation_nodes(tree: ast.AST) -> set:
    """Every node that lives inside an annotation.

    ``from __future__ import annotations`` makes those strings at runtime, so
    ``int | None`` there is fine on 3.8 while the same syntax in real code is not.
    """
    inside = set()
    for node in ast.walk(tree):
        annotations = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations.append(node.returns)
            args = node.args
            annotations += [
                arg.annotation
                for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
                if arg is not None
            ]
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        for annotation in annotations:
            if annotation is not None:
                inside.update(id(child) for child in ast.walk(annotation))
    return inside


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(ROOT)))
def test_the_source_parses_as_python_38(path: Path) -> None:
    try:
        ast.parse(path.read_text(encoding="utf-8"), str(path), feature_version=TARGET)
    except SyntaxError as exc:
        pytest.fail(f"{path.relative_to(ROOT)}:{exc.lineno}: not valid 3.8 syntax: {exc.msg}")


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(ROOT)))
def test_annotations_are_postponed(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    if not annotation_nodes(tree):
        return  # nothing to postpone
    assert "from __future__ import annotations" in source, (
        f"{path.relative_to(ROOT)} uses annotations without postponing them; "
        f"'X | None' would be evaluated at runtime and fail on 3.8"
    )


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(ROOT)))
def test_no_type_unions_outside_annotations(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    inside = annotation_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr) and id(node) not in inside:
            # A real bitwise-or is fine; a type union here would fail on 3.8.
            operands = (node.left, node.right)
            assert not any(
                isinstance(operand, ast.Constant) and operand.value is None for operand in operands
            ), f"{path.relative_to(ROOT)}:{node.lineno}: type union outside an annotation"


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(ROOT)))
def test_no_standard_library_newer_than_38(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            version = YOUNGER_ATTRS.get(node.attr)
            if version:
                problems.append(f"line {node.lineno}: .{node.attr}() needs Python {version}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                version = YOUNGER_MODULES.get(alias.name.split(".")[0])
                if version and not _is_guarded(tree, node):
                    problems.append(f"line {node.lineno}: {alias.name} needs {version}")
        elif isinstance(node, ast.ImportFrom):
            version = YOUNGER_MODULES.get((node.module or "").split(".")[0])
            if version and not _is_guarded(tree, node):
                problems.append(f"line {node.lineno}: {node.module} needs {version}")
    assert not problems, f"{path.relative_to(ROOT)}: " + "; ".join(problems)


def _is_guarded(tree: ast.AST, target: ast.AST) -> bool:
    """Is *target* inside a try/except that catches the import failing?"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and any(
            child is target for body in (node.body,) for child in body
        ):
            return any(
                isinstance(handler.type, ast.Name)
                and handler.type.id in ("ImportError", "ModuleNotFoundError")
                for handler in node.handlers
            )
    return False


#: Everything the package may import. Standard library only, plus itself - a
#: third-party import would not survive being copied to another machine, and an
#: unvetted one would not be covered by the 3.8 checks above.
ALLOWED_ROOTS = {
    "__future__", "argparse", "ast", "dataclasses", "os", "pathlib", "re",
    "shutil", "subprocess", "sys", "time", "tomllib", "typing",
    "tmux_sessionizer",
}


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: path.name)
def test_the_package_imports_nothing_third_party(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                continue                     # "from . import x" - our own package
            modules = [node.module or ""]
        elif isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        else:
            continue
        for module in modules:
            root = module.split(".")[0]
            assert root in ALLOWED_ROOTS, f"{path.name} imports {module!r}"
