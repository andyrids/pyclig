"""Logging for a CLI run, bound to the run's STDERR console.

Without `-d`, records render as `warning:` / `error:` notices
(`EventHandler`). With `-d`, a `RichHandler` adds levels, times & call sites.

NOTE: Both handlers write through the console they are given. Pass the same
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

import contextlib
import logging
from collections.abc import Generator
from datetime import datetime

from rich.console import Console
from rich.text import Text

from pyclig._output import info, notice, print_exception

DATEFMT = "[%Y-%m-%dT%H:%M:%S%z]"
"""The `-d` handler's time format, in local time with its UTC offset."""

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


def configure(name: str, console: Console, *, debug: bool) -> None:
    """Attach a CLI handler, bound to `console`, to the `name` logger.

    NOTE: Replaces any handler a previous call added & keeps the rest (e.g.
    the library `NullHandler`). Records stop at this logger
    (`propagate = False`), so nothing is printed twice by a root handler.

    Args:
        name: The logger name, usually the application package.
        console: The STDERR console of the run.
        debug: Use the verbose `RichHandler` at `DEBUG`, else the
            `EventHandler` at `WARNING`.
    """
    logger = logging.getLogger(name)
    _remove_handlers(logger)
    handler: logging.Handler
    if debug:
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
    else:
        handler = EventHandler(console)
    setattr(handler, _MARKER, True)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if debug else logging.WARNING)
    logger.propagate = False


@contextlib.contextmanager
def scoped(name: str) -> Generator[None, None, None]:
    """Restore the `name` logger's handlers, level & propagation on exit.

    Args:
        name: The logger name.

    Yields:
        None, while the run configures the logger.
    """
    logger = logging.getLogger(name)
    saved = logger.handlers[:], logger.level, logger.propagate
    try:
        yield
    finally:
        _remove_handlers(logger)
        logger.handlers[:] = saved[0]
        logger.setLevel(saved[1])
        logger.propagate = saved[2]


def _format_time(when: datetime) -> Text:
    """Format a record's time with `DATEFMT`, adding the local UTC offset."""
    return Text(when.astimezone().strftime(DATEFMT))


def _remove_handlers(logger: logging.Logger) -> None:
    """Remove & close the handlers `configure` added to `logger`."""
    for handler in [h for h in logger.handlers if getattr(h, _MARKER, False)]:
        logger.removeHandler(handler)
        handler.close()
