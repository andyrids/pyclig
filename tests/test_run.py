"""Tests for `pyclig._run` - exit codes & error rendering."""

import io
import logging
import subprocess
import sys
from typing import Any

import pytest

import pyclig
from pyclig import Group, _run
from pyclig.testing import invoke
from tests.conftest import SAMPLE, RunSample, sample_env

# (args, message, failing command path)
USAGE_ERRORS = [
    (
        ["list", "--start", "nope"],
        "error: Invalid value for '--start': invalid year `nope` - use YYYY",
        "sample list",
    ),
    (["list", "--nope"], "error: No such option '--nope'.", "sample list"),
    (
        ["list", "--start"],
        "error: Option '--start' requires an argument.",
        "sample list",
    ),
    (
        ["lst"],
        "error: No such command 'lst'. Did you mean 'list'?",
        "sample",
    ),
    (
        ["list", "--strt", "2026"],
        "error: No such option '--strt'. Did you mean '--start'?",
        "sample list",
    ),
    (
        ["fail", "--kind", "usage"],
        "error: --kind usage cannot be combined",
        "sample fail",
    ),
]


@pytest.mark.parametrize(("args", "message", "path"), USAGE_ERRORS)
def test_usage_error_on_stderr_with_failing_command_usage(
    sample: Group, args: list[str], message: str, path: str
) -> None:
    """Assert a usage error prints message, usage & hint to STDERR only."""
    result = invoke(sample, args)
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        message,
        "",
        "USAGE:",
        f"  {path} [options]{' <command>' if path == 'sample' else ''}",
        "",
        f"Try '{path} --help' for more information.",
    ]


@pytest.mark.parametrize("value", ["[/b]", "[red]x", ":warning:"])
def test_usage_error_prints_user_input_literally(
    sample: Group, value: str
) -> None:
    """Assert markup & emoji codes in user input print as typed."""
    result = invoke(sample, ["list", "--start", value])
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert f"invalid year `{value}`" in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_required_option_names_env_var(sample: Group) -> None:
    """Assert a missing `envvar` option names its variable (`show_envvar`)."""
    result = invoke(sample, ["download"])
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert (
        "error: Missing option '--data-dir' (env var: 'SAMPLE_DATA_DIR')."
        in result.stderr
    )


def test_no_args_is_help_prints_help_to_stderr(sample: Group) -> None:
    """Assert a `no_args_is_help` command prints its help to STDERR, exit 2."""
    result = invoke(sample, ["process"])
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert result.stderr.startswith("USAGE:\n  sample process [options]")
    assert "error:" not in result.stderr


def test_mapped_error_without_traceback(sample: Group) -> None:
    """Assert an `errors` type prints `error: message` only, exit 1."""
    result = invoke(sample, ["fail", "--kind", "mapped"])
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert result.stderr == "error: disk full [/b] :warning:\n"


def test_mapped_error_with_debug_prints_traceback(sample: Group) -> None:
    """Assert `-d` prints the traceback of an expected error first."""
    result = invoke(sample, ["fail", "--kind", "mapped", "-d"])
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert result.stderr.startswith("Traceback (most recent call last):")
    assert result.stderr.endswith("error: disk full [/b] :warning:\n")


def _traceback_frames(stderr: str) -> list[str]:
    """Return the `File ...` lines of a printed traceback."""
    return [line for line in stderr.splitlines() if line.startswith("  File")]


def test_unexpected_error_trimmed_traceback(sample: Group) -> None:
    """Assert a crash prints a traceback starting at the command, exit 70."""
    result = invoke(sample, ["fail", "--kind", "crash"])
    assert result.exit_code == pyclig.ExitCode.INTERNAL
    frames = _traceback_frames(result.stderr)
    assert frames
    assert "sample_cli.py" in frames[0]
    assert "error: unexpected RuntimeError: boom" in result.stderr


def test_traceback_rich_on_a_terminal(sample: Group) -> None:
    """Assert a traceback is rendered by Rich when STDERR is a terminal."""
    result = invoke(sample, ["fail", "--kind", "crash"], err_tty=True)
    assert "Traceback (most recent call last)" in result.stderr
    assert "╭" in result.stderr


def test_unexpected_error_while_parsing(sample: Group) -> None:
    """Assert a bug in a parameter type is a crash, not a usage error."""
    result = invoke(sample, ["list", "--start", "crash"])
    assert result.exit_code == pyclig.ExitCode.INTERNAL
    assert "unexpected TypeError: the year type is broken" in result.stderr
    assert "sample_cli.py" in _traceback_frames(result.stderr)[0]


def test_eof_error_is_a_crash(sample: Group) -> None:
    """Assert an `EOFError` from command code exits 70, not 'aborted'."""
    result = invoke(sample, ["fail", "--kind", "eof"])
    assert result.exit_code == pyclig.ExitCode.INTERNAL
    assert "unexpected EOFError: truncated" in result.stderr
    assert "aborted" not in result.stderr


def test_unrelated_pipe_error_is_a_crash(sample: Group) -> None:
    """Assert an EPIPE from another pipe exits 70 while STDOUT still works."""
    result = invoke(sample, ["fail", "--kind", "oserror"])
    assert result.exit_code == pyclig.ExitCode.INTERNAL
    assert "a child process pipe broke" in result.stderr


def test_bug_hint_names_issues_url(
    sample: Group, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert a crash hints at the distribution's `Issues` project URL."""
    monkeypatch.setattr(_run, "_distribution", lambda package: "pyclig")
    result = invoke(sample, ["fail", "--kind", "crash"])
    assert result.stderr.rstrip().endswith(
        "please report it at https://github.com/andyrids/pyclig/issues, "
        "with the output above."
    )


def test_bug_hint_absent_without_project_url(sample: Group) -> None:
    """Assert no bug hint is printed when no tracker URL is known."""
    result = invoke(sample, ["fail", "--kind", "crash"])
    assert "please report" not in result.stderr


def test_keyboard_interrupt_in_command(sample: Group) -> None:
    """Assert Ctrl-C prints one warning line & exits 130."""
    result = invoke(sample, ["fail", "--kind", "interrupt"])
    assert result.exit_code == pyclig.ExitCode.INTERRUPT
    assert result.stderr == "warning: interrupted\n"


class _InterruptingInput(io.BytesIO):
    """STDIN that raises `KeyboardInterrupt` on the first read."""

    def read(self, size: int | None = -1) -> bytes:
        if size == 0:
            return b""
        raise KeyboardInterrupt

    def read1(self, size: int | None = -1) -> bytes:
        return self.read(size)


def test_keyboard_interrupt_at_prompt(sample: Group) -> None:
    """Assert Ctrl-C at a prompt is an interrupt, not a declined prompt."""
    result = invoke(sample, ["confirm"], input=_InterruptingInput())
    assert result.exit_code == pyclig.ExitCode.INTERRUPT
    assert result.stderr == "warning: interrupted\n"


def test_declined_confirmation_aborts(sample: Group) -> None:
    """Assert a declined `confirm(abort=True)` prints `error: aborted`."""
    result = invoke(sample, ["confirm"], input="n\n")
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert result.stderr == "error: aborted\n"


def test_returned_code_passes_through(sample: Group) -> None:
    """Assert a command returning 130 adds no message."""
    result = invoke(sample, ["fail", "--kind", "code"])
    assert result.exit_code == pyclig.ExitCode.INTERRUPT
    assert result.stderr == ""


def _close_early(*args: str, delay: bool) -> tuple[int, str]:
    """Run the sample with a reader that leaves early, like `| head -1`.

    Args:
        *args: The sample arguments.
        delay: Close the pipe before the sample writes, else after a line.

    Returns:
        The exit code & STDERR.
    """
    with subprocess.Popen(
        [sys.executable, str(SAMPLE), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=sample_env(),
    ) as proc:
        assert proc.stdout is not None
        assert proc.stderr is not None
        if not delay:
            proc.stdout.readline()
        proc.stdout.close()
        stderr = proc.stderr.read().decode("utf-8", "replace")
    return proc.returncode, stderr


@pytest.mark.parametrize(
    "args",
    [
        ["echo", "--lines", "100000"],
        ["echo", "--lines", "20000", "--rich"],
        ["echo", "--lines", "3", "--delay", "0.5"],
        ["echo", "--lines", "3", "--delay", "0.5", "--rich"],
    ],
    ids=["echo-large", "rich-large", "echo-small", "rich-small"],
)
def test_broken_stdout_pipe_exits_quietly(args: list[str]) -> None:
    """Assert a reader leaving early gives exit 1 & an empty STDERR."""
    code, stderr = _close_early(*args, delay="--delay" in args)
    assert (code, stderr) == (pyclig.ExitCode.FAILURE, "")


@pytest.mark.parametrize("var", ["FORCE_COLOR", "TTY_COMPATIBLE"])
def test_piped_output_styled_when_forced(
    run_sample: RunSample, var: str
) -> None:
    """Assert `FORCE_COLOR` / `TTY_COMPATIBLE` style piped output."""
    result = run_sample("fail", "--kind", "mapped", env={var: "1"})
    assert "\x1b[1;31merror:" in result.stderr


def test_no_color_removes_colour(run_sample: RunSample) -> None:
    """Assert `NO_COLOR` drops colour, even when styling is forced."""
    result = run_sample(
        "fail", "--kind", "mapped", env={"FORCE_COLOR": "1", "NO_COLOR": "1"}
    )
    assert "\x1b[1;31m" not in result.stderr
    assert "\x1b[1merror:" in result.stderr


def test_piped_output_plain_by_default(run_sample: RunSample) -> None:
    """Assert piped output carries no ANSI codes."""
    result = run_sample("fail", "--kind", "mapped")
    assert result.stderr == "error: disk full [/b] :warning:\n"


def test_piped_output_encodes_any_text() -> None:
    """Assert glyphs print as UTF-8 when piped, whatever the locale."""
    result = subprocess.run(
        [sys.executable, str(SAMPLE), "show", "--value", "✓ → ·"],
        capture_output=True,
        env=sample_env(),
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.decode("utf-8").splitlines() == ["✓ → ·"]


def test_explicit_io_encoding_replaces_unencodable(
    run_sample: RunSample,
) -> None:
    """Assert `PYTHONIOENCODING=cp1252` replaces glyphs instead of failing."""
    result = run_sample(
        "show", "--value", "✓ → ·", env={"PYTHONIOENCODING": "cp1252"}
    )
    assert result.returncode == 0
    assert "UnicodeEncodeError" not in result.stderr


def _run_hook(
    func: Any, capsys: pytest.CaptureFixture[str], **kwargs: Any
) -> tuple[int, str]:
    """Call `pyclig.run(func)` & return the exit code & STDERR."""
    with pytest.raises(SystemExit) as exc_info:
        pyclig.run(func, **kwargs)
    code = exc_info.value.code
    assert isinstance(code, int)
    return code, capsys.readouterr().err


def test_run_passes_returned_code(capsys: pytest.CaptureFixture[str]) -> None:
    """Assert `run` exits with the returned code, or 0 for None."""
    assert _run_hook(lambda: 3, capsys) == (3, "")
    assert _run_hook(lambda: None, capsys) == (0, "")


class _HookError(Exception):
    """An expected hook failure."""


def _raise(error: BaseException) -> None:
    """Raise `error`."""
    raise error


def test_run_maps_errors(capsys: pytest.CaptureFixture[str]) -> None:
    """Assert `run` maps expected errors, Ctrl-C & crashes."""
    expected = _run_hook(
        lambda: _raise(_HookError("bad config")), capsys, errors=(_HookError,)
    )
    assert expected == (1, "error: bad config\n")
    assert _run_hook(lambda: _raise(KeyboardInterrupt()), capsys) == (
        130,
        "warning: interrupted\n",
    )
    code, stderr = _run_hook(lambda: _raise(ValueError("oops")), capsys)
    assert code == pyclig.ExitCode.INTERNAL
    assert "error: unexpected ValueError: oops" in stderr


def test_run_logs_warnings(capsys: pytest.CaptureFixture[str]) -> None:
    """Assert a warning logged by a hook is printed to STDERR."""

    def hook() -> int:
        logging.getLogger("tests").warning("config is stale")
        return 0

    assert _run_hook(hook, capsys) == (0, "warning: config is stale\n")
