"""Per-run signal handlers - Ctrl-C says so at once & SIGTERM exits 143.

Python's default SIGINT handler raises `KeyboardInterrupt` wherever the
main thread is, so `warning: interrupted` waits for the stack to unwind,
and SIGTERM ends the process silently. `scoped` installs handlers for one
run & restores the previous ones afterwards.

| Signal                    | Action                                      |
| ------------------------- | ------------------------------------------- |
| First, outside a clean-up | Notice, recorded, `KeyboardInterrupt`       |
| First, inside a clean-up  | Notice, recorded; the block finishes first  |
| Later                     | `KeyboardInterrupt` again, no second notice |
| While the runner reports  | The runner exits at once with the code      |

The notice ends the `^C` line on a terminal, then prints `warning:
interrupted` (SIGINT, Ctrl-Break) or `warning: terminated` (SIGTERM). The
runner reads `State.signal` for the code: 143 for SIGTERM, else 130.

NOTE: Handlers belong to the main thread, so a run on another thread is
left alone. `signal` is imported inside the functions, so `import pyclig`
touches no handler. On Windows `os.kill(pid, SIGTERM)` is
`TerminateProcess` - exit 15 with no message - and Ctrl-Break is the stop
signal a program can catch; a blocking call delays the notice there.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import contextlib
import sys
import threading
from collections.abc import Callable, Generator
from types import FrameType
from typing import TYPE_CHECKING

from pyclig._exit import ExitCode
from pyclig._output import notice

if TYPE_CHECKING:
    from pyclig._run import State

Handler = Callable[[int, FrameType | None], None]
"""A Python-level signal handler."""


@contextlib.contextmanager
def scoped(state: "State") -> Generator[None, None, None]:
    """Handle SIGINT, SIGTERM & (Windows) SIGBREAK for one run.

    Args:
        state: The run's state, recording the signal & its notice.

    Yields:
        None, while the run owns the handlers.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    import signal

    handler = _handler(state)
    saved = {sig: signal.signal(sig, handler) for sig in _signals()}
    try:
        yield
    finally:
        for sig, previous in saved.items():
            signal.signal(
                sig, signal.SIG_DFL if previous is None else previous
            )


def exit_code(state: "State") -> ExitCode:
    """Return the code for the run's signal: 143 for SIGTERM, else 130."""
    import signal

    if state.signal == signal.SIGTERM:
        return ExitCode.TERMINATE
    return ExitCode.INTERRUPT


def message(state: "State") -> str:
    """Return the notice for the run's signal: terminated or interrupted."""
    import signal

    return "terminated" if state.signal == signal.SIGTERM else "interrupted"


def _signals() -> list[int]:
    """Return the signals a run handles."""
    import signal

    handled: list[int] = [signal.SIGINT, signal.SIGTERM]
    if sys.platform == "win32":
        handled.append(signal.SIGBREAK)
    return handled


def _handler(state: "State") -> Handler:
    """Return the run's handler (see the module table)."""

    def handle(signum: int, frame: FrameType | None) -> None:
        if state.signal is None:
            state.signal = signum
            _announce(state, signum)
            if state.cleaning:
                return
        raise KeyboardInterrupt

    return handle


def _announce(state: "State", signum: int) -> None:
    """Print the notice, ending a terminal's `^C` line first."""
    import signal

    state.announced = True
    if signum == signal.SIGINT and state.err.is_terminal:
        state.err.line()
    notice(state.err, level="warning", message=message(state))
