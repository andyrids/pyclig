"""Tests for `pyclig.testing` - the in-process harness."""

import os

import click
import pytest

import pyclig
from pyclig import Group
from pyclig.testing import invoke

# The `<PROG>_` variables a run reads, cleared by `invoke`
_PREFIXED = ("DEBUG", "NO_COLOR", "CONFIG", "PROFILE")


def test_echo_and_console_output_keep_order(sample: Group) -> None:
    """Assert `click.echo` & `ctx.out` writes are captured in order."""
    result = invoke(sample, ["streams"])
    assert result.stdout == "one\ntwo\nthree\n"


@pytest.mark.parametrize(
    ("out_tty", "err_tty"), [(False, True), (True, False)]
)
def test_stream_tty_flags_independent(
    sample: Group, out_tty: bool, err_tty: bool
) -> None:
    """Assert STDOUT & STDERR are terminals independently."""
    result = invoke(sample, ["streams"], out_tty=out_tty, err_tty=err_tty)
    assert result.stderr == (
        f"out={out_tty} err={err_tty} live=False prompt=False\n"
    )


@pytest.mark.parametrize(("err_tty", "live"), [(True, True), (False, False)])
def test_interactive_applies_to_terminal_streams(
    sample: Group, err_tty: bool, live: bool
) -> None:
    """Assert `interactive=True` makes terminal streams interactive only."""
    result = invoke(sample, ["streams"], err_tty=err_tty, interactive=True)
    assert result.stderr.endswith(f"live={live} prompt=False\n")


def test_colour_variables_cleared(
    sample: Group, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert a developer's `NO_COLOR` does not leak into a run."""
    monkeypatch.setenv("NO_COLOR", "1")
    args = ["fail", "--kind", "mapped"]
    result = invoke(sample, args, err_tty=True, color=True)
    assert "\x1b[1;31m" in result.stderr
    result = invoke(
        sample, args, err_tty=True, color=True, env={"NO_COLOR": "1"}
    )
    assert "\x1b[1;31m" not in result.stderr


def test_colour_flag_styles_terminal_output(sample: Group) -> None:
    """Assert `color=True` emits ANSI codes on a terminal stream."""
    result = invoke(
        sample, ["fail", "--kind", "mapped"], err_tty=True, color=True
    )
    assert result.stderr.startswith("\x1b[1;31merror:")


def test_prefixed_variables_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    """Assert a developer's `TESTS_DEBUG` & friends do not leak into a run."""

    @pyclig.command("probe")
    def probe() -> None:
        """Print the run's `<PROG>_` variables."""
        for var in _PREFIXED:
            click.echo(f"{var}={os.environ.get(f'TESTS_{var}')}")

    for var in _PREFIXED:
        monkeypatch.setenv(f"TESTS_{var}", "1")
    result = invoke(probe)
    assert result.stdout == "".join(f"{var}=None\n" for var in _PREFIXED)
    result = invoke(probe, env={"TESTS_CONFIG": "app.toml"})
    assert "CONFIG=app.toml\n" in result.stdout
