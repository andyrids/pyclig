"""Message primitives for a CLI's STDOUT & STDERR consoles.

Each function renders for the stream behind its `Console`: wrapped on a
terminal, otherwise one line per message that never wraps, for logs & `grep`.
Styles are always applied; the console drops them unless colour is wanted
(a terminal, or `FORCE_COLOR` on a pipe). Text is printed as `rich.text.Text`
and never parsed as markup or emoji codes, so user input (`[/b]`,
`:warning:`, Windows paths) prints as written. Control characters, including
terminal escapes, are dropped.

NOTE: The console is always passed in, never a global, so a live display
(`Progress`, `Status`) on the same console redraws cleanly around these
lines. Arguments after the console are keyword-only.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import re
import traceback
from collections.abc import Iterable
from typing import Literal

from rich.console import Console
from rich.text import Text

Level = Literal["error", "warning"]
"""A `notice` level."""

_LEVEL_STYLES: dict[Level, str] = {"error": "red", "warning": "yellow"}
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_QUIET = "_pyclig_quiet"


def silence(console: Console) -> None:
    """Mark `console` quiet: `info` lines are dropped & nothing animates.

    NOTE: The mark lives on the console itself, so it holds in worker
    threads & inside a `Progress`, where no click context is current.

    Args:
        console: The STDERR console of the run.
    """
    setattr(console, _QUIET, True)
    console.is_interactive = False


def is_quiet(console: Console) -> bool:
    """Check whether `silence` marked `console` quiet.

    Args:
        console: A console.

    Returns:
        Whether `-q` applies to it.
    """
    return bool(getattr(console, _QUIET, False))


def _text(message: str, style: str = "") -> Text:
    """Return `message` as `Text`, without control characters."""
    return Text(_CONTROL.sub("", message), style=style)


def _plain(console: Console, line: str) -> None:
    """Print an unstyled line that never wraps, for logs & `grep`."""
    console.print(_text(line), soft_wrap=True)


def _head(head: Text | str) -> Text:
    """Return `head` as `Text`: a `str` is sanitised, a `Text` is trusted."""
    return _text(head) if isinstance(head, str) else head


def _hanging(console: Console, *, head: Text | str, message: str) -> Text:
    """Return `head message`, wrapped with a hanging indent under `message`.

    NOTE: Wraps by hand, so wrapped lines carry no trailing padding.

    Args:
        console: The console whose width to wrap to.
        head: The prefix or mark leading the first line, e.g. `✓`.
        message: The text after it.

    Returns:
        The wrapped lines, joined by newlines.
    """
    mark = _head(head)
    room = max(console.width - mark.cell_len - 1, 20)
    rows = []
    for i, line in enumerate(_text(message).wrap(console, room)):
        line.rstrip()
        indent = mark if i == 0 else " " * mark.cell_len
        rows.append(Text.assemble(indent, " ", line))
    return Text("\n").join(rows)


def _line(console: Console, *, head: Text | str, message: str) -> Text:
    """Return `head message` as one line: wrapped on a terminal, else not.

    Args:
        console: The console the line is for.
        head: The prefix or mark leading the line.
        message: The text after it.

    Returns:
        The line, with a hanging indent when the console is a terminal.
    """
    if console.is_terminal:
        return _hanging(console, head=head, message=message)
    return Text.assemble(_head(head), " ", _text(message))


def hanging(console: Console, *, head: Text | str, message: str) -> None:
    """Print `head message`, wrapped with a hanging indent under `message`.

    NOTE: Wraps by hand, so wrapped lines carry no trailing padding. The
    lines print in one call, so messages from worker threads never
    interleave. A `str` head is sanitised like `message`; a `Text` head is
    printed as given.

    Args:
        console: The console to print to.
        head: The prefix or mark leading the first line, e.g. `✓`.
        message: The text after it.
    """
    console.print(
        _hanging(console, head=head, message=message), soft_wrap=True
    )


def notice(
    console: Console,
    *,
    level: Level,
    message: str,
    items: Iterable[str] = (),
) -> None:
    """Print a `level: message` line, its prefix bold & coloured.

    `items` follow it, each indented by two spaces: the one line of a
    grouped failure, e.g. `error: 2 files failed` over the files. Header &
    items print in one call, so worker threads & live displays cannot
    split them. Kept when the console is quiet; a `hint` after it carries
    the remedy.

    Args:
        console: The console to print to, usually STDERR.
        level: `error` (red) or `warning` (yellow).
        message: The message.
        items: Lines to list under the message, wrapped on a terminal.
    """
    head = Text(f"{level}:", style=f"bold {_LEVEL_STYLES[level]}")
    rows = [_line(console, head=head, message=message)]
    rows += [_line(console, head=" ", message=item) for item in items]
    console.print(Text("\n").join(rows), soft_wrap=True)


def info(console: Console, *, message: str) -> None:
    """Print a line of context, dim - dropped when the console is quiet.

    Args:
        console: The console to print to, usually STDERR.
        message: The message.
    """
    if not is_quiet(console):
        hint(console, message=message)


def hint(console: Console, *, message: str) -> None:
    """Print a line the user acts on, dim - kept when the console is quiet.

    Args:
        console: The console to print to, usually STDERR.
        message: The message, e.g. a remedy or a `--help` pointer.
    """
    console.print(
        _text(message, style="dim"), soft_wrap=not console.is_terminal
    )


def row(
    console: Console,
    *,
    mark: Text | str,
    label: str,
    detail: Text | str = "",
    width: int = 0,
    essential: bool = False,
) -> None:
    """Print one state row: `mark  label  detail`, never wrapped.

    Columns are two spaces apart; `label` is padded to `width` cells, so
    rows align when every call passes the widest label's cell length. The
    mark column is the caller's: pass a `mark` already padded to a fixed
    width. A `str` mark or detail is sanitised like `label`; a `Text` is
    printed as given. The line prints in one call, so rows from worker
    threads never interleave. Dropped when the console is quiet, unless
    `essential`.

    Args:
        console: The console to print to, usually STDERR.
        mark: The state word or symbol leading the row, e.g. `ok`.
        label: What changed, e.g. a step or a path.
        detail: What happened to it; without one, the row ends at `label`.
        width: The label column's width in cells; `0` pads nothing.
        essential: Keep the row when the console is quiet.
    """
    if is_quiet(console) and not essential:
        return
    cell = _text(label)
    pad = " " * max(width - cell.cell_len, 0)
    line = Text.assemble(_head(mark), "  ", cell, pad, "  ", _head(detail))
    line.rstrip()
    console.print(line, soft_wrap=True)


def summary(console: Console, *, message: str, failed: bool = False) -> None:
    """Print a closing line: `✓ message`, or `! message` when it failed.

    Wrapped with a hanging indent on a terminal, one line otherwise.
    Dropped when the console is quiet, unless `failed`. `-q` marks only the
    STDERR console, so a summary on STDOUT stays.

    Args:
        console: The console to print to.
        message: The outcome, e.g. `3 files checked`.
        failed: Whether the run failed, which keeps the line under `-q`.
    """
    if is_quiet(console) and not failed:
        return
    mark = Text("!", style="bold red") if failed else Text("✓", style="green")
    console.print(_line(console, head=mark, message=message), soft_wrap=True)


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
