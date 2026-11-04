"""Tests for `pyclig._output` - message primitives."""

import io
import itertools
import threading
from unittest.mock import patch

import pytest
from rich.console import Console
from rich.text import Text

import pyclig
from pyclig._output import silence


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


def test_wrapped_notices_from_threads_never_interleave() -> None:
    """Assert a wrapped notice's lines stay together under threads."""
    console, buffer = _console(tty=True, width=40)
    message = "word " * 15

    def emit() -> None:
        for _ in range(20):
            pyclig.notice(console, level="warning", message=message)

    threads = [threading.Thread(target=emit) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    lines = buffer.getvalue().splitlines()
    heads = [i for i, line in enumerate(lines) if "warning:" in line]
    assert len(heads) == 8 * 20
    assert {b - a for a, b in itertools.pairwise(heads)} == {3}


def test_messages_drop_c1_controls() -> None:
    """Assert 8-bit C1 codes (`\x9b` is CSI) are dropped like 7-bit ones."""
    console, buffer = _console(tty=False)
    pyclig.info(console, message="path\x9b2J\x85/file")
    assert buffer.getvalue() == "path2J/file\n"


def test_hint_kept_and_info_dropped_when_quiet() -> None:
    """Assert `-q` drops `info` but keeps `hint`, which the user acts on."""
    console, buffer = _console(tty=False)
    silence(console)
    pyclig.info(console, message="context")
    pyclig.hint(console, message="run `prog --help`")
    assert buffer.getvalue() == "run `prog --help`\n"


def test_notice_items_indented_off_a_terminal() -> None:
    """Assert grouped items follow the header, one unwrapped line each."""
    console, buffer = _console(tty=False, width=20)
    pyclig.notice(
        console,
        level="error",
        message="2 files failed",
        items=["a.txt: a reason too long for the width", "b.txt: bad"],
    )
    assert buffer.getvalue() == (
        "error: 2 files failed\n"
        "  a.txt: a reason too long for the width\n"
        "  b.txt: bad\n"
    )


def test_notice_items_wrapped_on_a_terminal() -> None:
    """Assert items on a TTY wrap with a hanging indent under the item."""
    console, buffer = _console(tty=True, width=24)
    pyclig.notice(
        console,
        level="error",
        message="failed",
        items=["one two three four five six"],
    )
    lines = buffer.getvalue().splitlines()
    assert lines[0].startswith("\x1b[1;31merror:\x1b[0m failed")
    assert lines[1:] == ["  one two three four", "  five six"]


@pytest.mark.parametrize("item", ["[/b]", ":warning:", "a\x1b[2Jb"])
def test_notice_items_print_literally(item: str) -> None:
    """Assert items print markup as written & drop control codes."""
    console, buffer = _console(tty=True)
    pyclig.notice(console, level="warning", message="m", items=[item])
    assert buffer.getvalue().splitlines()[1] == "  " + item.replace("\x1b", "")


def test_notice_with_items_prints_once_and_survives_quiet() -> None:
    """Assert a grouped notice is one print, kept when the console is quiet."""
    console, buffer = _console(tty=True)
    silence(console)
    with patch.object(console, "print", wraps=console.print) as spy:
        pyclig.notice(console, level="error", message="m", items=["a", "b"])
    assert spy.call_count == 1
    assert buffer.getvalue().count("\n") == 3


def test_row_pads_label_by_cell_width() -> None:
    """Assert a row pads the label column by cell length, not characters."""
    console, buffer = _console(tty=False)
    pyclig.row(console, mark="ok", label="名", detail="detail", width=4)
    assert buffer.getvalue() == "ok  名    detail\n"


def test_row_never_wraps() -> None:
    """Assert a row stays one line on a narrow terminal & off it."""
    for tty in (False, True):
        console, buffer = _console(tty=tty, width=20)
        pyclig.row(console, mark="ok", label="a label", detail="a long detail")
        assert buffer.getvalue() == "ok  a label  a long detail\n"


def test_row_omits_padding_without_detail() -> None:
    """Assert a row with no detail carries no trailing padding."""
    console, buffer = _console(tty=False)
    pyclig.row(console, mark="ok", label="short", width=10)
    assert buffer.getvalue() == "ok  short\n"


def test_row_dropped_when_quiet_unless_essential() -> None:
    """Assert `-q` drops rows, except those marked essential."""
    console, buffer = _console(tty=False)
    silence(console)
    pyclig.row(console, mark="ok", label="dropped")
    pyclig.row(console, mark="!", label="kept", essential=True)
    assert buffer.getvalue() == "!  kept\n"


def test_row_sanitises_strings_and_trusts_text() -> None:
    """Assert `str` cells print markup literally & drop control codes."""
    console, buffer = _console(tty=True)
    mark = Text("ok", style="green")
    pyclig.row(console, mark=mark, label="[/b]\x1b[2J", detail="a\x9bb")
    assert buffer.getvalue() == "\x1b[32mok\x1b[0m  [/b][2J  ab\n"
    console, buffer = _console(tty=False)
    pyclig.row(console, mark=":warning:\x7f", label="x")
    assert buffer.getvalue() == ":warning:  x\n"


def test_summary_marks_success_and_failure() -> None:
    """Assert a summary leads with `✓`, or `!` when it failed."""
    console, buffer = _console(tty=False)
    pyclig.summary(console, message="3 files checked")
    pyclig.summary(console, message="2 files failed", failed=True)
    assert buffer.getvalue() == "✓ 3 files checked\n! 2 files failed\n"


def test_summary_wraps_only_on_a_terminal() -> None:
    """Assert a summary wraps under its text on a TTY, & is one line off."""
    message = "one two three four five six seven"
    console, buffer = _console(tty=True, width=24)
    pyclig.summary(console, message=message)
    assert buffer.getvalue().splitlines()[1:] == ["  five six seven"]
    console, buffer = _console(tty=False, width=24)
    pyclig.summary(console, message=message)
    assert buffer.getvalue() == f"✓ {message}\n"


@pytest.mark.parametrize(
    ("message", "shown"),
    [
        ("[/b]", "[/b]"),
        (":warning:", ":warning:"),
        ("a\x9b2Jb\x1b[0m", "a2Jb[0m"),
    ],
)
def test_summary_prints_literally(message: str, shown: str) -> None:
    """Assert a summary prints markup as written & drops control codes."""
    console, buffer = _console(tty=True)
    pyclig.summary(console, message=message)
    assert buffer.getvalue().endswith(f" {shown}\n")


def test_summary_dropped_when_quiet_unless_failed() -> None:
    """Assert `-q` drops a success summary & keeps a failed one."""
    console, buffer = _console(tty=False)
    silence(console)
    pyclig.summary(console, message="done")
    pyclig.summary(console, message="failed", failed=True)
    assert buffer.getvalue() == "! failed\n"


def test_summary_on_stdout_stays_when_stderr_quiet() -> None:
    """Assert `-q` marks STDERR only, so a summary on STDOUT prints."""
    err, _ = _console(tty=False)
    out, buffer = _console(tty=False)
    silence(err)
    pyclig.summary(out, message="done")
    assert buffer.getvalue() == "✓ done\n"
