"""Tests for `pyclig.testing` - the in-process harness."""

import pytest

from pyclig import Group
from pyclig.testing import invoke


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
    assert result.stderr == f"out={out_tty} err={err_tty} live=False\n"


@pytest.mark.parametrize(("err_tty", "live"), [(True, True), (False, False)])
def test_interactive_applies_to_terminal_streams(
    sample: Group, err_tty: bool, live: bool
) -> None:
    """Assert `interactive=True` makes terminal streams interactive only."""
    result = invoke(sample, ["streams"], err_tty=err_tty, interactive=True)
    assert result.stderr.endswith(f"live={live}\n")


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
