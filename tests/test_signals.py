"""Tests for `pyclig._signals` - per-run handlers, notices & exit codes."""

import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

import click
import pytest

import pyclig
from pyclig import _run, _signals
from pyclig.testing import invoke
from tests.conftest import sample_env

SIGNALS = [signal.SIGINT, signal.SIGTERM]
if sys.platform == "win32":
    SIGNALS.append(signal.SIGBREAK)

_CHILD = """
import socket
import pyclig


@pyclig.command()
def main() -> None:
    a, b = socket.socketpair()
    a.settimeout({timeout})
    print("ready", flush=True)
    while True:
        try:
            a.recv(1)
        except TimeoutError:
            pass


main()
"""


def _cli(body: Callable[[pyclig.Context], Any]) -> pyclig.Command:
    """Return a one-command CLI running `body` with its context."""

    @pyclig.command()
    @pyclig.pass_context
    def main(ctx: pyclig.Context) -> Any:
        return body(ctx)

    return main


def _state(ctx: pyclig.Context) -> _run.State:
    state = _run.state_of(ctx)
    assert state is not None
    return state


def _handlers() -> dict[int, Any]:
    return {sig: signal.getsignal(sig) for sig in SIGNALS}


def _raising(signum: int) -> pyclig.Command:
    def body(ctx: pyclig.Context) -> None:
        signal.raise_signal(signum)
        click.echo("not reached")

    return _cli(body)


@pytest.mark.parametrize(
    ("signum", "code", "message"),
    [
        pytest.param(signal.SIGINT, 130, "interrupted", id="sigint"),
        pytest.param(signal.SIGTERM, 143, "terminated", id="sigterm"),
        pytest.param(
            getattr(signal, "SIGBREAK", None),
            130,
            "interrupted",
            id="sigbreak",
            marks=pytest.mark.skipif(
                sys.platform != "win32", reason="Windows only"
            ),
        ),
    ],
)
def test_signal_notice_and_exit_code(
    signum: int, code: int, message: str
) -> None:
    """Assert a signal prints its notice & maps to 130 or 143."""
    result = invoke(_raising(signum), [])
    assert result.exit_code == code
    assert result.stderr == f"warning: {message}\n"
    assert result.stdout == ""


def test_terminate_code() -> None:
    """Assert `ExitCode.TERMINATE` is 128 + SIGTERM."""
    assert pyclig.ExitCode.TERMINATE == 143


def test_notice_is_printed_before_unwinding() -> None:
    """Assert the handler prints at once: a swallowed interrupt keeps it."""

    def body(ctx: pyclig.Context) -> None:
        try:
            signal.raise_signal(signal.SIGINT)
        except KeyboardInterrupt:
            click.echo("caught")
        state = _state(ctx)
        assert state.signal == signal.SIGINT
        assert state.announced

    result = invoke(_cli(body), [])
    assert result.exit_code == 0
    assert result.stdout == "caught\n"
    assert result.stderr == "warning: interrupted\n"


def test_second_signal_raises_without_a_second_notice() -> None:
    """Assert a later signal raises again & prints nothing more."""

    def body(ctx: pyclig.Context) -> None:
        try:
            signal.raise_signal(signal.SIGINT)
        except KeyboardInterrupt:
            pass
        signal.raise_signal(signal.SIGINT)
        click.echo("not reached")

    result = invoke(_cli(body), [])
    assert result.exit_code == 130
    assert result.stderr == "warning: interrupted\n"
    assert result.stdout == ""


def test_signal_while_reporting_exits_with_its_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assert a signal during the runner's report exits with the code."""
    original = _run.notice

    def notice(*args: Any, **kwargs: Any) -> None:
        monkeypatch.setattr(_run, "notice", original)
        signal.raise_signal(signal.SIGTERM)
        original(*args, **kwargs)  # pragma: no cover - the handler raises

    monkeypatch.setattr(_run, "notice", notice)

    def body(ctx: pyclig.Context) -> None:
        raise KeyboardInterrupt

    result = invoke(_cli(body), [])
    assert result.exit_code == 143
    assert result.stderr == "warning: terminated\n"


def test_code_raised_interrupt_prints_after_unwinding() -> None:
    """Assert a `KeyboardInterrupt` raised by code is still reported."""

    def body(ctx: pyclig.Context) -> None:
        raise KeyboardInterrupt

    result = invoke(_cli(body), [])
    assert result.exit_code == 130
    assert result.stderr == "warning: interrupted\n"


def test_handlers_installed_for_the_run_and_restored() -> None:
    """Assert the run installs handlers & puts the previous ones back."""
    seen: list[dict[int, Any]] = []

    def body(ctx: pyclig.Context) -> None:
        seen.append(_handlers())

    before = _handlers()
    assert before[signal.SIGINT] is signal.default_int_handler
    for _ in range(2):
        result = invoke(_cli(body), [])
        assert result.exit_code == 0
        assert _handlers() == before
    assert len(seen) == 2
    for handlers in seen:
        for sig in SIGNALS:
            assert callable(handlers[sig])
            assert handlers[sig] is not before[sig]


def test_run_on_another_thread_leaves_handlers_alone() -> None:
    """Assert a run off the main thread installs nothing & still works."""
    seen: list[dict[int, Any]] = []
    results: list[Any] = []

    def body(ctx: pyclig.Context) -> None:
        seen.append(_handlers())
        click.echo("plain")

    before = _handlers()
    thread = threading.Thread(
        target=lambda: results.append(invoke(_cli(body), []))
    )
    thread.start()
    thread.join(10)
    assert not thread.is_alive()
    assert results[0].exit_code == 0
    assert results[0].stdout == "plain\n"
    assert seen == [before]
    assert _handlers() == before


def _spawn(timeout: str, **kwargs: Any) -> subprocess.Popen[str]:
    child = subprocess.Popen(
        [sys.executable, "-c", _CHILD.format(timeout=timeout)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=sample_env(),
        **kwargs,
    )
    assert child.stdout is not None
    assert child.stdout.readline() == "ready\n"
    return child


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize(
    ("signum", "code", "message"),
    [
        pytest.param(signal.SIGINT, 130, "interrupted", id="sigint"),
        pytest.param(signal.SIGTERM, 143, "terminated", id="sigterm"),
    ],
)
def test_posix_signal_to_a_blocked_child(
    signum: int, code: int, message: str
) -> None:
    """Assert a signal to a child blocked in `recv` is reported at once."""
    child = _spawn("None")
    child.send_signal(signum)
    _, stderr = child.communicate(timeout=10)
    assert child.returncode == code
    assert stderr == f"warning: {message}\n"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows console events")
def test_windows_ctrl_break_to_a_child() -> None:
    """Assert Ctrl-Break to a child in its own process group exits 130."""
    child = _spawn("0.1", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    child.send_signal(signal.CTRL_BREAK_EVENT)
    _, stderr = child.communicate(timeout=10)
    assert child.returncode == 130
    assert stderr == "warning: interrupted\n"


@pytest.mark.parametrize(
    ("signum", "expected"),
    [
        pytest.param(signal.SIGINT, "\nwarning: interrupted\n", id="sigint"),
        pytest.param(signal.SIGTERM, "warning: terminated\n", id="sigterm"),
    ],
)
def test_terminal_line_ended_for_ctrl_c_only(
    signum: int, expected: str
) -> None:
    """Assert the `^C` echo line is ended on a terminal for SIGINT only."""
    result = invoke(_raising(signum), [], err_tty=True)
    assert result.stderr == expected


# --- ctx.cleanup ------------------------------------------------------------

HINT = "cleaning up - press Ctrl-C again to skip"
STOP = signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGINT
FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

_CLEANUP_CHILD = """
import signal
import socket
import socket
import sys
import threading
import time
import time

import pyclig

MODE = sys.argv.pop(1)
TIMEOUT = {timeout}


@pyclig.command()
@pyclig.pass_context
def main(ctx: pyclig.Context) -> None:
    if MODE == "thread":
        def work() -> None:
            with ctx.cleanup(timeout=TIMEOUT):
                print("in thread", flush=True)

        worker = threading.Thread(target=work)
        worker.start()
        worker.join()
        return
    if MODE == "foreign":
        a, b = socket.socketpair()
        b.setblocking(False)
        signal.set_wakeup_fd(b.fileno())
    if MODE == "normal":
        with ctx.cleanup(timeout=TIMEOUT):
            print("ready", flush=True)
            threading.Event().wait()
    print("ready", flush=True)
    try:
        while True:
            time.sleep(0.05)
    except KeyboardInterrupt:
        try:
            if MODE == "nested":
                with ctx.cleanup(timeout=TIMEOUT), ctx.cleanup(timeout=None):
                    threading.Event().wait()
            elif MODE == "foreign":
                with ctx.cleanup(timeout=TIMEOUT):
                    time.sleep(0.3)
            else:
                with ctx.cleanup(timeout=TIMEOUT):
                    threading.Event().wait()
        finally:
            if MODE == "foreign":
                restored = signal.set_wakeup_fd(-1) == b.fileno()
                print("restored", restored, flush=True)
        raise


main()
"""


@pytest.fixture
def exits(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Patch `_signals._exit` & return the codes it was called with."""
    calls: list[int] = []
    monkeypatch.setattr(_signals, "_exit", calls.append)
    return calls


def _interrupt() -> None:
    """Raise SIGINT & swallow the `KeyboardInterrupt` it brings."""
    try:
        signal.raise_signal(signal.SIGINT)
    except KeyboardInterrupt:
        pass


def test_cleanup_entered_after_an_interrupt_hints(exits: list[int]) -> None:
    """Assert a block after an interrupt prints the hint & then exits 130."""

    def body(ctx: pyclig.Context) -> None:
        try:
            signal.raise_signal(signal.SIGINT)
        except KeyboardInterrupt:
            with ctx.cleanup():
                click.echo("cleaned")
            raise

    result = invoke(_cli(body), [])
    assert result.exit_code == 130
    assert result.stdout == "cleaned\n"
    assert result.stderr == f"warning: interrupted\n{HINT}\n"
    assert exits == []


@pytest.mark.parametrize(
    ("signum", "code", "stderr"),
    [
        pytest.param(
            signal.SIGINT, 130, f"warning: interrupted\n{HINT}\n", id="sigint"
        ),
        pytest.param(
            signal.SIGTERM,
            143,
            "warning: terminated\ncleaning up\n",
            id="sigterm",
        ),
    ],
)
def test_cleanup_signal_on_the_normal_path_finishes_the_block(
    exits: list[int], signum: int, code: int, stderr: str
) -> None:
    """Assert a signal inside a block prints notice & hint, then 130/143."""

    def body(ctx: pyclig.Context) -> None:
        with ctx.cleanup():
            signal.raise_signal(signum)
            time.sleep(0.3)
            click.echo("finished")
        click.echo("not reached")

    result = invoke(_cli(body), [])
    assert result.exit_code == code
    assert result.stdout == "finished\n"
    assert result.stderr == stderr
    assert exits == []


def test_cleanup_second_signal_skips_the_block(exits: list[int]) -> None:
    """Assert another signal inside a block prints `skipped` & exits 130."""

    def body(ctx: pyclig.Context) -> None:
        with ctx.cleanup():
            signal.raise_signal(signal.SIGINT)
            time.sleep(0.2)
            signal.raise_signal(signal.SIGINT)
            time.sleep(0.2)
            click.echo("finished")

    result = invoke(_cli(body), [])
    assert exits == [130]
    assert result.exit_code == 130
    assert result.stderr == (
        f"warning: interrupted\n{HINT}\nwarning: clean-up skipped\n"
    )


def test_cleanup_timeout_exits(exits: list[int]) -> None:
    """Assert the timer, counted from the interrupt, exits the block."""

    def body(ctx: pyclig.Context) -> None:
        _interrupt()
        with ctx.cleanup(timeout=0.2):
            time.sleep(0.6)

    result = invoke(_cli(body), [])
    assert exits == [130]
    assert result.stderr == (
        f"warning: interrupted\n{HINT}\n"
        "warning: clean-up timed out after 0.2s\n"
    )


def test_cleanup_block_raising_cancels_the_timer(exits: list[int]) -> None:
    """Assert an exception propagates & the timer is cancelled."""

    def body(ctx: pyclig.Context) -> None:
        _interrupt()
        try:
            with ctx.cleanup(timeout=0.1):
                raise ValueError("boom")
        finally:
            assert _state(ctx).watcher is None
        time.sleep(0.3)

    result = invoke(_cli(body), [])
    assert result.exit_code == 70
    assert "boom" in result.stderr
    assert exits == []
    assert signal.set_wakeup_fd(-1) == -1


def test_cleanup_without_an_interrupt_runs_plainly(exits: list[int]) -> None:
    """Assert a block with no signal prints nothing & restores the fd."""

    def body(ctx: pyclig.Context) -> None:
        with ctx.cleanup():
            assert _state(ctx).cleaning == 1
            owned = signal.set_wakeup_fd(-1)
            assert owned != -1
            signal.set_wakeup_fd(owned)
        assert _state(ctx).cleaning == 0
        click.echo("done")

    result = invoke(_cli(body), [])
    assert result.exit_code == 0
    assert result.stdout == "done\n"
    assert result.stderr == ""
    assert signal.set_wakeup_fd(-1) == -1


def test_cleanup_off_the_main_thread_runs_plainly(exits: list[int]) -> None:
    """Assert a block on another thread installs nothing & runs."""

    def body(ctx: pyclig.Context) -> None:
        state = _state(ctx)

        def work() -> None:
            with ctx.cleanup():
                assert state.cleaning == 0
                click.echo("in thread")

        worker = threading.Thread(target=work)
        worker.start()
        worker.join()

    result = invoke(_cli(body), [])
    assert result.exit_code == 0
    assert result.stdout == "in thread\n"
    assert result.stderr == ""


def test_cleanup_nested_blocks_share_the_outer_timer(
    exits: list[int],
) -> None:
    """Assert nesting counts depth, hints once & keeps the outer timeout."""

    def body(ctx: pyclig.Context) -> None:
        _interrupt()
        state = _state(ctx)
        with ctx.cleanup(timeout=0.2):
            with ctx.cleanup(timeout=None):
                assert state.cleaning == 2
                time.sleep(0.5)
            assert state.cleaning == 1

    result = invoke(_cli(body), [])
    assert exits == [130]
    assert result.stderr == (
        f"warning: interrupted\n{HINT}\n"
        "warning: clean-up timed out after 0.2s\n"
    )


def test_cleanup_foreign_wakeup_fd_is_restored(exits: list[int]) -> None:
    """Assert a wakeup fd set by others is kept & the handler steps in."""
    a, b = socket.socketpair()
    b.setblocking(False)
    signal.set_wakeup_fd(b.fileno())
    try:

        def body(ctx: pyclig.Context) -> None:
            with ctx.cleanup():
                assert signal.set_wakeup_fd(b.fileno()) == b.fileno()
                signal.raise_signal(signal.SIGINT)
                time.sleep(0.2)
                signal.raise_signal(signal.SIGINT)
                time.sleep(0.2)

        result = invoke(_cli(body), [])
        assert exits == [130]
        assert result.stderr == (
            f"warning: interrupted\n{HINT}\nwarning: clean-up skipped\n"
        )
        assert signal.set_wakeup_fd(-1) == b.fileno()
    finally:
        signal.set_wakeup_fd(-1)
        a.close()
        b.close()


def _spawn_cleanup(
    mode: str, timeout: str, *, ready: bool = True
) -> subprocess.Popen[str]:
    child = subprocess.Popen(
        [sys.executable, "-c", _CLEANUP_CHILD.format(timeout=timeout), mode],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=sample_env(),
        creationflags=FLAGS,
    )
    assert child.stdout is not None
    if ready:
        assert child.stdout.readline() == "ready\n"
    return child


def _announced(child: subprocess.Popen[str], hint: str = HINT) -> None:
    """Wait for the notice & hint lines on the child's STDERR."""
    assert child.stderr is not None
    assert child.stderr.readline().startswith("warning: ")
    assert child.stderr.readline() == f"{hint}\n"


@pytest.mark.parametrize("mode", ["normal", "after"])
def test_child_second_signal_skips_the_cleanup(mode: str) -> None:
    """Assert a second signal exits a stuck clean-up at once, code 130."""
    child = _spawn_cleanup(mode, "None")
    child.send_signal(STOP)
    _announced(child)
    started = time.monotonic()
    child.send_signal(STOP)
    _, stderr = child.communicate(timeout=10)
    elapsed = time.monotonic() - started
    assert child.returncode == 130
    assert stderr == "warning: clean-up skipped\n"
    assert elapsed < 0.5, elapsed


def test_child_timeout_bounds_the_cleanup() -> None:
    """Assert the timer exits a stuck clean-up, within 0.2 s of the bound."""
    child = _spawn_cleanup("after", "0.5")
    started = time.monotonic()
    child.send_signal(STOP)
    _, stderr = child.communicate(timeout=10)
    elapsed = time.monotonic() - started
    assert child.returncode == 130
    assert stderr.endswith("warning: clean-up timed out after 0.5s\n")
    assert 0.5 <= elapsed < 0.5 + 0.3, elapsed


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_child_sigterm_hints_cleaning_up_and_exits_143() -> None:
    """Assert SIGTERM's hint is plain & a second SIGTERM exits 143."""
    child = _spawn_cleanup("normal", "None")
    child.send_signal(signal.SIGTERM)
    _announced(child, hint="cleaning up")
    child.send_signal(signal.SIGTERM)
    _, stderr = child.communicate(timeout=10)
    assert child.returncode == 143
    assert stderr == "warning: clean-up skipped\n"


def test_child_nested_blocks_use_the_outer_timeout() -> None:
    """Assert the outer block's timeout applies to a nested block."""
    child = _spawn_cleanup("nested", "0.5")
    child.send_signal(STOP)
    _, stderr = child.communicate(timeout=10)
    assert child.returncode == 130
    assert stderr == (
        f"warning: interrupted\n{HINT}\n"
        "warning: clean-up timed out after 0.5s\n"
    )


def test_child_foreign_wakeup_fd_is_restored() -> None:
    """Assert a foreign wakeup fd survives the block in a real process."""
    child = _spawn_cleanup("foreign", "None")
    child.send_signal(STOP)
    stdout, stderr = child.communicate(timeout=10)
    assert child.returncode == 130
    assert stdout == "restored True\n"
    assert stderr == f"warning: interrupted\n{HINT}\n"


def test_child_cleanup_off_the_main_thread_runs_plainly() -> None:
    """Assert a block on a worker thread runs normally in a real process."""
    child = _spawn_cleanup("thread", "None", ready=False)
    stdout, stderr = child.communicate(timeout=10)
    assert child.returncode == 0
    assert stdout == "in thread\n"
    assert stderr == ""


def test_wakeup_fd_and_handlers_restored_after_a_run() -> None:
    """Assert a run with a clean-up block leaves no fd or handler behind."""
    before = _handlers()

    def body(ctx: pyclig.Context) -> None:
        with ctx.cleanup():
            pass

    assert invoke(_cli(body), []).exit_code == 0
    assert signal.set_wakeup_fd(-1) == -1
    assert _handlers() == before


def test_cleanup_detaches_the_watcher_before_stopping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assert `state.watcher` is None by the time the pair is closed."""
    seen: list[Any] = []
    original = _signals.Watcher.stop

    def stop(self: _signals.Watcher) -> None:
        seen.append(self.state.watcher)
        original(self)

    monkeypatch.setattr(_signals.Watcher, "stop", stop)

    def body(ctx: pyclig.Context) -> None:
        with ctx.cleanup():
            pass

    assert invoke(_cli(body), []).exit_code == 0
    assert seen == [None]


def test_signal_to_a_stopped_watcher_takes_the_plain_path() -> None:
    """Assert `notify` on closed ends raises nothing & the handler steps in."""

    def body(ctx: pyclig.Context) -> None:
        state = _state(ctx)
        with ctx.cleanup():
            watcher = state.watcher
        assert watcher is not None
        assert watcher.notify(signal.SIGINT) is False
        watcher.owns_fd = False
        state.watcher = watcher
        signal.raise_signal(signal.SIGINT)
        click.echo("not reached")

    result = invoke(_cli(body), [])
    assert result.exit_code == 130
    assert result.stderr == "warning: interrupted\n"
    assert result.stdout == ""
