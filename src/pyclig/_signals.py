"""Per-run signal handlers - Ctrl-C says so at once & SIGTERM exits 143.

Python's default SIGINT handler raises `KeyboardInterrupt` wherever the
main thread is, so `warning: interrupted` waits for the stack to unwind,
and SIGTERM ends the process silently. `scoped` installs handlers for one
run & restores the previous ones afterwards.

| Signal                    | Action                                      |
| ------------------------- | ------------------------------------------- |
| First, outside a clean-up | Notice, recorded, `KeyboardInterrupt`       |
| First, inside a clean-up  | Notice & hint; the block finishes first     |
| Later, outside a clean-up | `KeyboardInterrupt` again, no second notice |
| Later, inside a clean-up  | `warning: clean-up skipped`, immediate exit |
| While the runner reports  | The runner exits at once with the code      |

The notice ends the `^C` line on a terminal, then prints `warning:
interrupted` (SIGINT, Ctrl-Break) or `warning: terminated` (SIGTERM). The
runner reads `State.signal` for the code: 143 for SIGTERM, else 130.

`cleanup` bounds a clean-up after an interrupt (`ctx.cleanup`): another
signal or the timeout flushes the streams, prints a warning & exits with
the code. A `Watcher` thread owns `signal.set_wakeup_fd` while the block
is active, so both are handled while the main thread is blocked - on
Windows, Ctrl-Break never wakes a blocked call. When another wakeup fd is
already set (asyncio's proactor loop), it is left alone & the Python
handler forwards the signal to the watcher instead.

NOTE: Handlers belong to the main thread, so a run on another thread is
left alone. `signal`, `socket` & `select` are imported inside the
functions, so `import pyclig` touches no handler. On Windows
`os.kill(pid, SIGTERM)` is `TerminateProcess` - exit 15 with no message -
and Ctrl-Break is the stop signal a program can catch.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import contextlib
import logging
import os
import sys
import threading
import time
from collections.abc import Callable, Generator
from types import FrameType
from typing import TYPE_CHECKING, Any

from pyclig._exit import ExitCode
from pyclig._output import hint, notice

if TYPE_CHECKING:
    from pyclig._run import State

Handler = Callable[[int, FrameType | None], None]
"""A Python-level signal handler."""

_STOP = b"\x00"
"""The byte that ends a watcher; no signal is numbered 0."""

_SAY_TIMEOUT = 0.5
"""How long an exit waits for its message when the console is held."""


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


@contextlib.contextmanager
def cleanup(
    state: "State", *, timeout: float | None = 10.0
) -> Generator[None, None, None]:
    """Bound a clean-up block after an interrupt (see module docstring).

    Entered after an interrupt, it prints the hint & starts the timer. A
    signal inside the block prints the notice & hint and lets the block
    finish, after which `KeyboardInterrupt` is raised. Nested blocks count
    depth & keep the outermost block's timer. Off the main thread, or with
    no interrupt, the block runs normally.

    Args:
        state: The run's state.
        timeout: Seconds allowed from the interrupt, or None for no bound.

    Yields:
        None, while the block runs.

    Raises:
        KeyboardInterrupt: After the block, for a signal received inside.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    if state.watcher is not None:
        state.cleaning += 1
        try:
            yield
        finally:
            state.cleaning -= 1
        return
    interrupted = state.signal is not None
    watcher = Watcher(state, timeout)
    state.watcher, state.cleaning = watcher, 1
    try:
        if interrupted:
            _hint(state)
        watcher.start()
        yield
    finally:
        watcher.stop()
        state.watcher, state.cleaning = None, 0
    if not interrupted and state.signal is not None:
        raise KeyboardInterrupt


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


class Watcher:
    """A daemon thread owning the wakeup fd while a clean-up block runs.

    Signals arrive as bytes on a pipe (POSIX) or socket pair (Windows):
    the first prints the notice & hint and starts the timer; another, or
    the timer, exits the process. `stop` ends the thread & restores the
    wakeup fd it took.
    """

    def __init__(self, state: "State", timeout: float | None) -> None:
        """Create the watcher, without starting it.

        Args:
            state: The run's state.
            timeout: Seconds allowed from the interrupt, or None.
        """
        self.state = state
        self.timeout = timeout
        self.deadline: float | None = None
        self.owns_fd = False
        self._wake = _Wake()
        self._thread = threading.Thread(
            target=self._run, name="pyclig-cleanup", daemon=True
        )

    def start(self) -> None:
        """Take the wakeup fd, unless another is set, & start the thread."""
        import signal

        previous = signal.set_wakeup_fd(
            self._wake.fileno(), warn_on_full_buffer=False
        )
        if previous == -1:
            self.owns_fd = True
        else:
            signal.set_wakeup_fd(previous)
        if self.state.signal is not None:
            self._arm()
        self._thread.start()

    def stop(self) -> None:
        """End the thread, give the wakeup fd back & close the pair."""
        import signal

        self._wake.write(_STOP)
        self._thread.join(_SAY_TIMEOUT * 2)
        if self.owns_fd:
            signal.set_wakeup_fd(-1)
        self._wake.close()

    def notify(self, signum: int) -> None:
        """Forward a signal the Python handler saw (no wakeup fd owned)."""
        self._wake.write(bytes([signum]))

    def _arm(self) -> None:
        """Start the timer, counting from now."""
        if self.timeout is not None and self.deadline is None:
            self.deadline = time.monotonic() + self.timeout

    def _run(self) -> None:
        import select

        while True:
            remaining = None
            if self.deadline is not None:
                remaining = max(0.0, self.deadline - time.monotonic())
            ready, _, _ = select.select([self._wake.reader], [], [], remaining)
            if not ready:
                seconds = f"{self.timeout:g}s"
                _finish(self.state, f"clean-up timed out after {seconds}")
                return
            for signum in self._wake.read():
                if signum == 0:
                    return
                if self._signalled(signum):
                    return

    def _signalled(self, signum: int) -> bool:
        """Handle one signal; True when the process is exiting."""
        state = self.state
        if state.signal is not None:
            _finish(state, "clean-up skipped")
            return True
        state.signal = signum
        self._arm()

        def speak() -> None:
            _announce(state, signum)
            _hint(state)

        _say(speak)
        return False


class _Wake:
    """A pipe (POSIX) or socket pair (Windows) for the wakeup fd."""

    def __init__(self) -> None:
        self.reader: Any
        self._fd: int
        self._read: Callable[[], bytes]
        self._write: Callable[[bytes], object]
        self._close: Callable[[], None]
        if sys.platform == "win32":
            import socket

            rsock, wsock = socket.socketpair()
            wsock.setblocking(False)
            self.reader = rsock
            self._fd = wsock.fileno()
            self._read = lambda: rsock.recv(64)
            self._write = wsock.send

            def close() -> None:
                rsock.close()
                wsock.close()

        else:
            rfd, wfd = os.pipe()
            os.set_blocking(wfd, False)
            self.reader = rfd
            self._fd = wfd
            self._read = lambda: os.read(rfd, 64)
            self._write = lambda data: os.write(wfd, data)

            def close() -> None:
                os.close(rfd)
                os.close(wfd)

        self._close = close

    def fileno(self) -> int:
        """Return the write end, for `signal.set_wakeup_fd`."""
        return self._fd

    def read(self) -> bytes:
        """Read the bytes waiting on the read end."""
        return self._read()

    def write(self, data: bytes) -> None:
        """Write to the write end, as a signal would."""
        self._write(data)

    def close(self) -> None:
        """Close both ends."""
        self._close()


def _finish(state: "State", warning: str) -> None:
    """Warn, flush the streams & exit with the signal's code."""
    code = exit_code(state)
    _say(lambda: notice(state.err, level="warning", message=warning))
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.flush()
    for handler in logging.getLogger(state.package).handlers:
        with contextlib.suppress(Exception):
            handler.flush()
    _exit(code)


def _exit(code: int) -> None:
    """Exit the process at once; a seam the tests patch."""
    os._exit(code)


def _say(speak: Callable[[], object]) -> None:
    """Print through a helper thread, in case the console is held."""
    helper = threading.Thread(target=speak, daemon=True)
    helper.start()
    helper.join(_SAY_TIMEOUT)


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
        watcher = state.watcher
        if watcher is not None:
            if not watcher.owns_fd:
                watcher.notify(signum)
            return
        if state.signal is None:
            state.signal = signum
            _announce(state, signum)
        raise KeyboardInterrupt

    return handle


def _announce(state: "State", signum: int) -> None:
    """Print the notice, ending a terminal's `^C` line first."""
    import signal

    state.announced = True
    if signum == signal.SIGINT and state.err.is_terminal:
        state.err.line()
    notice(state.err, level="warning", message=message(state))


def _hint(state: "State") -> None:
    """Print the clean-up hint; after SIGTERM there is no key to press."""
    import signal

    text = "cleaning up"
    if state.signal != signal.SIGTERM:
        text += " - press Ctrl-C again to skip"
    hint(state.err, message=text)
