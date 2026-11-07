"""Logging for a CLI run, bound to the run's STDERR console.

Without `-d`, records render as `warning:` / `error:` notices
(`EventHandler`). With `-d`, records add levels, times & call sites: laid out
by a `RichHandler` on a terminal, else one plain line each (`DebugHandler`):

```text
[2026-10-31T09:14:03+0000] DEBUG    [convert] converting 'nope'  cli.py:47
```

NOTE: When the root logger has no handlers as the run starts, the root gets
one too & `warnings` print through it: third-party notices show, without
`file:line` unless `-d` is on. A root configured by the application (e.g.
`logging.basicConfig`) is left alone.

Every handler writes through the console it is given. Pass the same
STDERR console to any `Progress` or `Status`, so Rich redraws the live
display around log lines instead of printing through it. The logger's state
is restored when the run ends, so repeated in-process runs (tests) never
stack handlers. Library code should only ever add a `NullHandler`, in its
`__init__.py`:

```python
logging.getLogger(__name__).addHandler(logging.NullHandler())
```

License:
    SPDX-License-Identifier: Apache-2.0
"""

import collections
import contextlib
import logging
import warnings
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import TextIO

import click
from rich.console import Console
from rich.text import Text

from pyclig._output import _plain, info, notice, print_exception

DATEFMT = "[%Y-%m-%dT%H:%M:%S%z]"
"""The `-d` handlers' time format, in local time with its UTC offset."""

DEBUG_FORMAT = (
    "%(asctime)s %(levelname)-8s [%(funcName)s] %(message)s"
    "  %(filename)s:%(lineno)d"
)
"""The `DebugHandler` record format; `asctime` is formatted with `DATEFMT`."""

_MARKER = "_pyclig_handler"


class EventHandler(logging.Handler):
    """Render log records as `warning:` / `error:` lines.

    NOTE: Records below `WARNING` render as dim context lines. A record with
    `exc_info` (`logger.exception`) is followed by its traceback.

    Attributes:
        console: The console records are printed to, usually STDERR.
    """

    def __init__(self, console: Console, level: int = logging.NOTSET) -> None:
        """Create the handler.

        Args:
            console: The console to print records to.
            level: The handler's level.
        """
        super().__init__(level)
        self.console = console

    def emit(self, record: logging.LogRecord) -> None:
        """Print the record as a notice, then any traceback.

        Args:
            record: The log record.
        """
        try:
            message = record.getMessage()
            if record.levelno >= logging.ERROR:
                notice(self.console, level="error", message=message)
            elif record.levelno >= logging.WARNING:
                notice(self.console, level="warning", message=message)
            else:
                info(self.console, message=message)
            if record.exc_info and record.exc_info[1] is not None:
                print_exception(self.console, record.exc_info[1])
        except Exception:
            self.handleError(record)


class _DebugFormatter(logging.Formatter):
    """Format records with `DEBUG_FORMAT`, timed with `DATEFMT`."""

    def formatTime(
        self, record: logging.LogRecord, datefmt: str | None = None
    ) -> str:
        """Return the record's local time with its UTC offset.

        NOTE: The stdlib `datefmt` path uses `time.strftime`, whose `%z` can
        print a zone name on Windows.

        Args:
            record: The log record.
            datefmt: Ignored; `DATEFMT` is always used.

        Returns:
            The formatted time.
        """
        return _timestamp(datetime.fromtimestamp(record.created))


class DebugHandler(logging.Handler):
    """Render log records as plain lines, for `-d` off a terminal.

    NOTE: Each record, with any traceback after it, prints in one call that
    never wraps, so it stays one `grep`-able line & never interleaves with
    output from another thread.

    Attributes:
        console: The console records are printed to, usually STDERR.
    """

    def __init__(self, console: Console, level: int = logging.NOTSET) -> None:
        """Create the handler.

        Args:
            console: The console to print records to.
            level: The handler's level.
        """
        super().__init__(level)
        self.console = console
        self.setFormatter(_DebugFormatter(DEBUG_FORMAT))

    def emit(self, record: logging.LogRecord) -> None:
        """Print the formatted record.

        Args:
            record: The log record.
        """
        try:
            _plain(self.console, self.format(record))
        except Exception:
            self.handleError(record)


def configure(
    name: str,
    console: Console,
    *,
    debug: bool,
    log_file: Path | None = None,
) -> None:
    """Attach a CLI handler, bound to `console`, to the `name` logger.

    NOTE: Replaces any handler a previous call added & keeps the rest (e.g.
    the library `NullHandler`). Records stop at this logger
    (`propagate = False`), so nothing is printed twice by a root handler.
    When the root logger has no other handler, it gets one as well - at
    `WARNING`, or every record the root passes with `debug` - & its level
    is never changed. A debug log file is opened on the first call & kept
    by later ones (`-d`), until `scoped` exits.

    Args:
        name: The logger name, usually the application package.
        console: The STDERR console of the run.
        debug: Log at `DEBUG` - through a `RichHandler` when `console` is a
            terminal, else the plain `DebugHandler`. Otherwise the
            `EventHandler` logs at `WARNING`.
        log_file: Append every record, at `DEBUG`, to this file as well -
            `<PROG>_LOG_FILE`. If it cannot be opened, a warning says so.
    """
    logger = logging.getLogger(name)
    file = _log_file(logger) or _open_log(console, log_file)
    _remove_handlers(logger, keep=file)
    _remove_handlers(logging.root, keep=file)
    level = logging.NOTSET if debug else logging.WARNING
    _attach(logger, _handler(console, debug=debug), level)
    logger.setLevel(logging.DEBUG if debug or file else logging.WARNING)
    logger.propagate = False
    if not logging.root.handlers:
        _attach(logging.root, _handler(console, debug=debug), level)
        if file:
            logging.root.addHandler(file)
    if file:
        logger.addHandler(file)


def log_failure(name: str, error: BaseException) -> str | None:
    """Write `error` & its traceback to the `name` logger's debug log file.

    Args:
        name: The logger name.
        error: The exception that ended the run.

    Returns:
        The file's path, or None when the run has no debug log file.
    """
    file = _log_file(logging.getLogger(name))
    if file is None:
        return None
    record = logging.LogRecord(
        name,
        logging.ERROR,
        __file__,
        0,
        "unexpected %s",
        (type(error).__name__,),
        (type(error), error, error.__traceback__),
    )
    file.handle(record)
    return file.baseFilename


@contextlib.contextmanager
def scoped(name: str) -> Generator[None, None, None]:
    """Restore the `name` logger's handlers, level & propagation on exit.

    NOTE: When the root logger has no handlers on entry, `warnings` print
    through it for the run (`showwarning` is replaced, then restored) & the
    root handler `configure` adds is removed on exit.

    Args:
        name: The logger name.

    Yields:
        None, while the run configures the logger.
    """
    logger = logging.getLogger(name)
    saved = logger.handlers[:], logger.level, logger.propagate
    shown = None if logging.root.handlers else warnings.showwarning
    if shown is not None:
        warnings.showwarning = _show_warning
    try:
        yield
    finally:
        _remove_handlers(logger)
        logger.handlers[:] = saved[0]
        logger.setLevel(saved[1])
        logger.propagate = saved[2]
        _remove_handlers(logging.root)
        if shown is not None:
            warnings.showwarning = shown


@contextlib.contextmanager
def held(name: str, *, level: int, debug: bool) -> Generator[None, None, None]:
    """Hold the `name` logger's records below `WARNING`, shown on failure.

    NOTE: The logger is lowered to `level` for the block; the console
    handler keeps its level, so a held handler keeps the records it drops
    (up to 1000). If an `Exception` other than `click.Abort` or
    `click.exceptions.Exit` leaves the block, they are replayed through the
    console handler before it propagates; otherwise they are dropped. A
    debug log file still gets every record live. A no-op with `debug`.

    Args:
        name: The logger name.
        level: The lowest level held.
        debug: Whether the run logs at `DEBUG`, which shows every record.

    Yields:
        None, while the block runs.
    """
    logger = logging.getLogger(name)
    console = next(
        (
            h
            for h in logger.handlers
            if getattr(h, _MARKER, False) and not isinstance(h, _LogFile)
        ),
        None,
    )
    if debug or console is None:
        yield
        return
    saved = logger.level
    holder = _Held(level)
    logger.addHandler(holder)
    if not saved or level < saved:
        logger.setLevel(level)
    try:
        yield
    except (click.Abort, click.exceptions.Exit):
        raise
    except Exception:
        logger.removeHandler(holder)
        for record in holder.records:
            console.handle(record)
        raise
    finally:
        logger.removeHandler(holder)
        logger.setLevel(saved)


class _Held(logging.Handler):
    """Keep the records below `WARNING`, the newest 1000, for `held`."""

    def __init__(self, level: int) -> None:
        super().__init__(level)
        self.records: collections.deque[logging.LogRecord] = collections.deque(
            maxlen=1000
        )

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            self.records.append(record)


def _handler(console: Console, *, debug: bool) -> logging.Handler:
    """Return the run's handler for `console`, as `configure` describes."""
    handler: logging.Handler
    if debug and console.is_terminal:
        from rich.logging import RichHandler

        handler = RichHandler(
            console=console,
            show_path=True,
            rich_tracebacks=True,
            markup=False,
            omit_repeated_times=False,
            log_time_format=_format_time,
        )
        handler.setFormatter(logging.Formatter("[%(funcName)s] %(message)s"))
    elif debug:
        handler = DebugHandler(console)
    else:
        handler = EventHandler(console)
    return handler


def _attach(
    logger: logging.Logger, handler: logging.Handler, level: int = 0
) -> None:
    """Mark `handler` as the run's, so it is removed later, & add it."""
    setattr(handler, _MARKER, True)
    handler.setLevel(level)
    logger.addHandler(handler)


def _log_file(logger: logging.Logger) -> logging.FileHandler | None:
    """Return the debug log file handler `configure` added to `logger`."""
    for handler in logger.handlers:
        if isinstance(handler, _LogFile):
            return handler
    return None


class _LogFile(logging.FileHandler):
    """The run's debug log file, appended with `DEBUG_FORMAT`."""


def _open_log(console: Console, path: Path | None) -> _LogFile | None:
    """Open the debug log file at `path`, or warn that it cannot be."""
    if path is None:
        return None
    try:
        handler = _LogFile(path, "a", encoding="utf-8")
    except OSError as error:
        reason = error.strerror or str(error)
        notice(
            console,
            level="warning",
            message=f"cannot write the debug log to {path}: {reason}",
        )
        return None
    handler.setFormatter(_DebugFormatter(DEBUG_FORMAT))
    setattr(handler, _MARKER, True)
    return handler


def _show_warning(  # noqa: PLR0913 - the `warnings.showwarning` signature
    message: Warning | str,
    category: type[Warning],
    filename: str,
    lineno: int,
    file: TextIO | None = None,
    line: str | None = None,
) -> None:
    """Log a warning as a `py.warnings` record carrying the message only.

    NOTE: The record keeps the warning's file & line as its call site, which
    only the `-d` handlers print. An explicit `file` is printed as before.
    """
    if file is not None:
        file.write(
            warnings.formatwarning(message, category, filename, lineno, line)
        )
        return
    logger = logging.getLogger("py.warnings")
    if logger.isEnabledFor(logging.WARNING):
        record = logger.makeRecord(
            logger.name,
            logging.WARNING,
            filename,
            lineno,
            str(message),
            (),
            None,
            func=category.__name__,
        )
        logger.handle(record)


def _timestamp(when: datetime) -> str:
    """Format a record's time with `DATEFMT`, adding the local UTC offset."""
    return when.astimezone().strftime(DATEFMT)


def _format_time(when: datetime) -> Text:
    """Format a record's time for the `RichHandler`."""
    return Text(_timestamp(when))


def _remove_handlers(
    logger: logging.Logger, keep: logging.Handler | None = None
) -> None:
    """Remove the handlers `configure` added to `logger` & close them,
    except `keep`, which is only removed."""
    for handler in [h for h in logger.handlers if getattr(h, _MARKER, False)]:
        logger.removeHandler(handler)
        if handler is not keep:
            handler.close()
