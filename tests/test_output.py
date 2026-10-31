"""Tests for `pyclig._output` - message primitives."""

import io

import pytest
from rich.console import Console

import pyclig


def _console(*, tty: bool, width: int = 40) -> tuple[Console, io.StringIO]:
    """Return a console writing to a buffer, & the buffer."""
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=tty,
        width=width,
        color_system="standard" if tty else None,
        markup=False,
    )
    return console, buffer


def test_notice_plain_off_a_terminal() -> None:
    """Assert a notice is one unwrapped `level: message` line off a TTY."""
    console, buffer = _console(tty=False, width=20)
    message = "a long message that would wrap on a terminal"
    pyclig.notice(console, level="warning", message=message)
    assert buffer.getvalue() == f"warning: {message}\n"


def test_notice_styled_and_wrapped_on_a_terminal() -> None:
    """Assert a notice is coloured & hanging-indented on a TTY."""
    console, buffer = _console(tty=True, width=24)
    pyclig.notice(console, level="error", message="one two three four five")
    lines = buffer.getvalue().splitlines()
    assert lines[0].startswith("\x1b[1;31merror:\x1b[0m one two")
    assert lines[1].startswith(" " * len("error: "))


@pytest.mark.parametrize("message", ["[/b]", "[red]x", ":warning:"])
def test_notice_prints_markup_literally(message: str) -> None:
    """Assert markup & emoji codes print as written, on any stream."""
    for tty in (False, True):
        console, buffer = _console(tty=tty)
        pyclig.notice(console, level="error", message=message)
        assert message in buffer.getvalue()


def test_messages_drop_terminal_escapes() -> None:
    """Assert escape sequences in a message cannot restyle the terminal."""
    console, buffer = _console(tty=False)
    pyclig.info(console, message="path\x1b[2J\r/file")
    assert buffer.getvalue() == "path[2J/file\n"


def test_info_dim_on_a_terminal() -> None:
    """Assert `info` is dim on a TTY & plain off one."""
    console, buffer = _console(tty=True)
    pyclig.info(console, message="context")
    assert buffer.getvalue() == "\x1b[2mcontext\x1b[0m\n"
    console, buffer = _console(tty=False)
    pyclig.info(console, message="context")
    assert buffer.getvalue() == "context\n"


def test_hanging_indents_wrapped_lines() -> None:
    """Assert `hanging` aligns wrapped lines under the message."""
    console, buffer = _console(tty=False, width=20)
    pyclig.hanging(console, head="✓", message="alpha beta gamma delta")
    assert buffer.getvalue().splitlines() == ["✓ alpha beta gamma", "  delta"]
