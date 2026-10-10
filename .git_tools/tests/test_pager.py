"""Tests for gitm.pager.print_or_page (backs mlog/mlogf's screen-fit decision).

Deliberately doesn't drive a real terminal/pager (less waiting for a
keypress would hang a test) -- these mock isatty()/terminal size and assert
on whether subprocess.run (the pager invocation) happened.
"""

from __future__ import annotations

import os
from unittest import mock

import gitm.pager as pager


def test_print_or_page_writes_directly_when_not_a_tty():
    with mock.patch("sys.stdout.isatty", return_value=False), \
         mock.patch("subprocess.run") as run_mock, \
         mock.patch("sys.stdout.write") as write_mock:
        pager.print_or_page("a\nb\nc\n")

    assert not run_mock.called
    write_mock.assert_called_once_with("a\nb\nc\n")


def test_print_or_page_writes_directly_when_content_fits_terminal():
    with mock.patch("sys.stdout.isatty", return_value=True), \
         mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))), \
         mock.patch("subprocess.run") as run_mock, \
         mock.patch("sys.stdout.write") as write_mock:
        text = "\n".join(f"line{i}" for i in range(10)) + "\n"
        pager.print_or_page(text)

    assert not run_mock.called
    write_mock.assert_called_once_with(text)


def test_print_or_page_uses_pager_when_content_overflows_terminal():
    with mock.patch("sys.stdout.isatty", return_value=True), \
         mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))), \
         mock.patch("subprocess.run") as run_mock, \
         mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PAGER", None)
        text = "\n".join(f"line{i}" for i in range(100)) + "\n"
        pager.print_or_page(text)

    assert run_mock.called
    args, kwargs = run_mock.call_args
    assert args[0] == ["less", "-R"]
    assert kwargs["input"] == text


def test_print_or_page_respects_pager_env_var():
    with mock.patch("sys.stdout.isatty", return_value=True), \
         mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 24))), \
         mock.patch("subprocess.run") as run_mock, \
         mock.patch.dict(os.environ, {"PAGER": "less -F -X"}):
        text = "\n".join(f"line{i}" for i in range(100)) + "\n"
        pager.print_or_page(text)

    args, _ = run_mock.call_args
    assert args[0] == ["less", "-F", "-X"]


def test_print_or_page_noop_on_empty_text():
    with mock.patch("subprocess.run") as run_mock, \
         mock.patch("sys.stdout.write") as write_mock:
        pager.print_or_page("")

    assert not run_mock.called
    assert not write_mock.called
