"""Tests for `pyclig._signals` - per-run handlers, notices & exit codes."""

import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any

import click
import pytest

import pyclig
from pyclig import _run
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


def test_signal_inside_cleaning_does_not_raise() -> None:
    """Assert a first signal inside a clean-up block only records & prints."""

    def body(ctx: pyclig.Context) -> None:
        state = _state(ctx)
        state.cleaning = 1
        signal.raise_signal(signal.SIGTERM)
        click.echo("finished")
        assert state.signal == signal.SIGTERM

    result = invoke(_cli(body), [])
    assert result.exit_code == 0
    assert result.stdout == "finished\n"
    assert result.stderr == "warning: terminated\n"


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
