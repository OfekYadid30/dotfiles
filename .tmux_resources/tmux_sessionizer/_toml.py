"""A small TOML reader, for Python versions without :mod:`tomllib`.

``tomllib`` arrived in Python 3.11. tmux_sessionizer has to run on the Python that
Ubuntu 20.04 ships (3.8), and the offline bundle it is packed into cannot
install anything, so a third-party parser is not an option either.

This is deliberately *not* a full TOML implementation. It reads the subset that
session files are written in - tables, arrays of tables, strings, integers,
floats, booleans and arrays - and raises :class:`TOMLDecodeError` with a line
number on anything else, including valid TOML it does not cover (dates, inline
tables, dotted keys). Guessing would be worse than refusing.

On 3.11+ the standard library is used instead; ``tests/test_toml.py`` checks
the two agree on every session file and on a corpus of edge cases, so the
version you develop on and the version in the bundle cannot drift apart.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

__all__ = ["TOMLDecodeError", "loads"]


class TOMLDecodeError(ValueError):
    """Invalid, or valid-but-unsupported, TOML."""


_BARE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
_WHITESPACE = " \t"
_ESCAPES = {
    "b": "\b",
    "t": "\t",
    "n": "\n",
    "f": "\f",
    "r": "\r",
    '"': '"',
    "\\": "\\",
}


def loads(text: str) -> Dict[str, Any]:
    """Parse TOML *text* into a dictionary."""
    return _Parser(text).parse()


class _Parser:
    def __init__(self, text: str) -> None:
        # A leading BOM is legal and invisible; strip it before anything else.
        self.text = text[1:] if text.startswith("﻿") else text
        self.pos = 0
        self.root: Dict[str, Any] = {}
        self.current: Dict[str, Any] = self.root
        #: Header paths already opened with ``[table]``, to catch redefinition.
        self.defined: set = set()

    # -- position -------------------------------------------------------

    @property
    def line(self) -> int:
        return self.text.count("\n", 0, self.pos) + 1

    def fail(self, message: str) -> "TOMLDecodeError":
        return TOMLDecodeError(f"line {self.line}: {message}")

    def at_end(self) -> bool:
        return self.pos >= len(self.text)

    def peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        return self.text[index] if index < len(self.text) else ""

    def starts_with(self, prefix: str) -> bool:
        return self.text.startswith(prefix, self.pos)

    def skip_blanks(self) -> None:
        while not self.at_end() and self.peek() in _WHITESPACE:
            self.pos += 1

    def skip_comment(self) -> None:
        if self.peek() == "#":
            while not self.at_end() and self.peek() != "\n":
                self.pos += 1

    def skip_to_next_line(self) -> None:
        """Consume trailing space, an optional comment, and the newline."""
        self.skip_blanks()
        self.skip_comment()
        if self.at_end():
            return
        if self.peek() != "\n":
            raise self.fail(f"unexpected {self.peek()!r} after a value")
        self.pos += 1

    # -- document -------------------------------------------------------

    def parse(self) -> Dict[str, Any]:
        while True:
            self.skip_blanks()
            if self.at_end():
                return self.root
            char = self.peek()
            if char == "\n":
                self.pos += 1
            elif char == "\r":
                self.pos += 1  # tolerate CRLF
            elif char == "#":
                self.skip_comment()
            elif char == "[":
                self.parse_header()
            else:
                self.parse_keyval()

    def parse_header(self) -> None:
        is_array = self.starts_with("[[")
        self.pos += 2 if is_array else 1
        self.skip_blanks()
        path = self.parse_key()
        self.skip_blanks()
        closing = "]]" if is_array else "]"
        if not self.starts_with(closing):
            raise self.fail(f"expected {closing!r} to close a table header")
        self.pos += len(closing)
        self.current = self.open_table(path, is_array=is_array)
        self.skip_to_next_line()

    def parse_keyval(self) -> None:
        path = self.parse_key()
        if len(path) != 1:
            raise self.fail("dotted keys are not supported; use a [table] header")
        self.skip_blanks()
        if self.peek() != "=":
            raise self.fail("expected '=' after a key")
        self.pos += 1
        self.skip_blanks()
        value = self.parse_value()
        key = path[0]
        if key in self.current:
            raise self.fail(f"duplicate key {key!r}")
        self.current[key] = value
        self.skip_to_next_line()

    # -- tables ---------------------------------------------------------

    def open_table(self, path: Tuple[str, ...], *, is_array: bool) -> Dict[str, Any]:
        node: Dict[str, Any] = self.root
        for index, part in enumerate(path[:-1]):
            child = node.setdefault(part, {})
            if isinstance(child, list):
                if not child:
                    raise self.fail(f"{'.'.join(path[: index + 1])} has no table to extend")
                child = child[-1]
            if not isinstance(child, dict):
                raise self.fail(f"{'.'.join(path[: index + 1])} is not a table")
            node = child

        last = path[-1]
        if is_array:
            existing = node.setdefault(last, [])
            if not isinstance(existing, list):
                raise self.fail(f"{'.'.join(path)} was already defined as a table")
            table: Dict[str, Any] = {}
            existing.append(table)
            return table

        if path in self.defined:
            raise self.fail(f"table [{'.'.join(path)}] is defined twice")
        self.defined.add(path)
        existing = node.setdefault(last, {})
        if not isinstance(existing, dict):
            raise self.fail(f"{'.'.join(path)} was already defined as an array")
        return existing

    # -- keys -----------------------------------------------------------

    def parse_key(self) -> Tuple[str, ...]:
        parts: List[str] = []
        while True:
            self.skip_blanks()
            char = self.peek()
            if char in ('"', "'"):
                parts.append(self.parse_string())
            else:
                start = self.pos
                while not self.at_end() and self.peek() in _BARE:
                    self.pos += 1
                if self.pos == start:
                    raise self.fail("expected a key")
                parts.append(self.text[start : self.pos])
            self.skip_blanks()
            if self.peek() == ".":
                self.pos += 1
                continue
            return tuple(parts)

    # -- values ---------------------------------------------------------

    def parse_value(self) -> Any:
        char = self.peek()
        if char in ('"', "'"):
            return self.parse_string()
        if char == "[":
            return self.parse_array()
        if char == "{":
            raise self.fail("inline tables are not supported; use a [table] header")
        if self.starts_with("true"):
            self.pos += 4
            return True
        if self.starts_with("false"):
            self.pos += 5
            return False
        return self.parse_number()

    def parse_string(self) -> str:
        if self.starts_with('"""'):
            return self.parse_multiline('"""', escaped=True)
        if self.starts_with("'''"):
            return self.parse_multiline("'''", escaped=False)
        if self.peek() == "'":
            self.pos += 1
            end = self.text.find("'", self.pos)
            if end < 0 or "\n" in self.text[self.pos : end]:
                raise self.fail("unterminated literal string")
            value = self.text[self.pos : end]
            self.pos = end + 1
            return value
        if self.peek() != '"':
            raise self.fail("expected a string")
        self.pos += 1
        return self.parse_basic_body(terminator='"')

    def parse_basic_body(self, *, terminator: str, multiline: bool = False) -> str:
        out: List[str] = []
        while True:
            if self.at_end():
                raise self.fail("unterminated string")
            if self.starts_with(terminator):
                self.pos += len(terminator)
                return "".join(out)
            char = self.peek()
            if char == "\n" and not multiline:
                raise self.fail("unterminated string")
            if char == "\\":
                out.append(self.parse_escape(multiline=multiline))
                continue
            out.append(char)
            self.pos += 1

    def parse_escape(self, *, multiline: bool) -> str:
        self.pos += 1  # the backslash
        char = self.peek()
        if char in _ESCAPES:
            self.pos += 1
            return _ESCAPES[char]
        if char in ("u", "U"):
            width = 4 if char == "u" else 8
            self.pos += 1
            digits = self.text[self.pos : self.pos + width]
            if len(digits) != width or any(d not in "0123456789abcdefABCDEF" for d in digits):
                raise self.fail(f"malformed \\{char} escape")
            self.pos += width
            return chr(int(digits, 16))
        if multiline and (char == "\n" or (char in _WHITESPACE and self._only_blanks_to_eol())):
            # A backslash at end of line swallows the newline and the indent.
            while not self.at_end() and self.peek() in _WHITESPACE + "\n":
                self.pos += 1
            return ""
        raise self.fail(f"unknown escape '\\{char}'")

    def _only_blanks_to_eol(self) -> bool:
        index = self.pos
        while index < len(self.text) and self.text[index] in _WHITESPACE:
            index += 1
        return index < len(self.text) and self.text[index] == "\n"

    def parse_multiline(self, quotes: str, *, escaped: bool) -> str:
        self.pos += 3
        # A newline immediately after the opening quotes is not part of the value.
        if self.peek() == "\n":
            self.pos += 1
        elif self.starts_with("\r\n"):
            self.pos += 2
        if not escaped:
            end = self.text.find(quotes, self.pos)
            if end < 0:
                raise self.fail("unterminated multi-line literal string")
            value = self.text[self.pos : end]
            self.pos = end + 3
            return value
        return self.parse_basic_body(terminator=quotes, multiline=True)

    def parse_array(self) -> List[Any]:
        self.pos += 1  # '['
        items: List[Any] = []
        while True:
            self.skip_array_padding()
            if self.at_end():
                raise self.fail("unterminated array")
            if self.peek() == "]":
                self.pos += 1
                return items
            items.append(self.parse_value())
            self.skip_array_padding()
            if self.peek() == ",":
                self.pos += 1
                continue
            if self.peek() == "]":
                self.pos += 1
                return items
            raise self.fail("expected ',' or ']' in an array")

    def skip_array_padding(self) -> None:
        """Whitespace, newlines and comments, all legal inside an array."""
        while not self.at_end():
            char = self.peek()
            if char in _WHITESPACE or char in "\n\r":
                self.pos += 1
            elif char == "#":
                self.skip_comment()
            else:
                return

    def parse_number(self) -> Any:
        start = self.pos
        while not self.at_end() and self.peek() not in ",]}\n\r#" + _WHITESPACE:
            self.pos += 1
        raw = self.text[start : self.pos].strip()
        if not raw:
            raise self.fail("expected a value")

        cleaned = raw.replace("_", "")
        try:
            if cleaned[:2].lower() in ("0x", "0o", "0b") or cleaned[:3].lower() in (
                "+0x", "-0x", "+0o", "-0o", "+0b", "-0b",
            ):
                return int(cleaned, 0)
            if any(char in cleaned for char in ".eE") and not cleaned.lstrip("+-")[:1].isalpha():
                return float(cleaned)
            return int(cleaned, 10)
        except ValueError:
            raise self.fail(
                f"{raw!r} is not a supported value; this reader handles strings, "
                f"integers, floats, booleans and arrays"
            ) from None
