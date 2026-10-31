"""Message primitives for a CLI's STDOUT & STDERR consoles.

Each function renders for the stream behind its `Console`: styled on a
terminal, otherwise one unstyled line per message that never wraps, for logs
& `grep`. Text is printed as `rich.text.Text` and never parsed as markup or
emoji codes, so user input (`[/b]`, `:warning:`, Windows paths) prints as
written. Control characters, including terminal escapes, are dropped.

NOTE: The console is always passed in, never a global, so a live display
(`Progress`, `Status`) on the same console redraws cleanly around these
lines. Arguments after the console are keyword-only.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import re
import traceback
from typing import Literal

from rich.console import Console
from rich.text import Text

Level = Literal["error", "warning"]
"""A `notice` level."""

_LEVEL_STYLES: dict[Level, str] = {"error": "red", "warning": "yellow"}
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _text(message: str, style: str = "") -> Text:
    """Return `message` as `Text`, without control characters."""
    return Text(_CONTROL.sub("", message), style=style)


def _plain(console: Console, line: str) -> None:
    """Print an unstyled line that never wraps, for logs & `grep`."""
    console.print(_text(line), soft_wrap=True)


def hanging(console: Console, *, head: Text | str, message: str) -> None:
    """Print `head message`, wrapped with a hanging indent under `message`.

    NOTE: Wraps by hand, so wrapped lines carry no trailing padding. The
    lines print in one call, so messages from worker threads never
    interleave.

    Args:
        console: The console to print to.
        head: The prefix or mark leading the first line, e.g. `✓`.
        message: The text after it.
    """
    head = _text(head) if isinstance(head, str) else head
    room = max(console.width - head.cell_len - 1, 20)
    rows = []
    for i, line in enumerate(_text(message).wrap(console, room)):
        line.rstrip()
        indent = head if i == 0 else " " * head.cell_len
        rows.append(Text.assemble(indent, " ", line))
    console.print(Text("\n").join(rows), soft_wrap=True)


def notice(console: Console, *, level: Level, message: str) -> None:
    """Print a `level: message` line, its prefix bold & coloured on a terminal.

    Args:
        console: The console to print to, usually STDERR.
        level: `error` (red) or `warning` (yellow).
        message: The message.
    """
    if not console.is_terminal:
        _plain(console, f"{level}: {message}")
        return
    head = Text(f"{level}:", style=f"bold {_LEVEL_STYLES[level]}")
    hanging(console, head=head, message=message)


def info(console: Console, *, message: str) -> None:
    """Print a line of context, dim on a terminal.

    Args:
        console: The console to print to, usually STDERR.
        message: The message.
    """
    if console.is_terminal:
        console.print(_text(message, style="dim"))
    else:
        _plain(console, message)


def print_exception(console: Console, error: BaseException) -> None:
    """Print an exception's traceback - Rich on a terminal, else plain.

    Args:
        console: The console to print to, usually STDERR.
        error: The exception, with its `__traceback__`.
    """
    if console.is_terminal:
        from rich.traceback import Traceback

        console.print(
            Traceback.from_exception(type(error), error, error.__traceback__)
        )
    else:
        _plain(console, "".join(traceback.format_exception(error)).rstrip())
