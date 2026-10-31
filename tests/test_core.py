"""Tests for `pyclig._core` - help, `-d`, `-v` & the group runner."""

import re
import subprocess
import sys
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

import pyclig
from pyclig import Group
from pyclig.testing import invoke
from tests.conftest import SAMPLE, InterruptingInput, RunSample, sample_env

DEBUG_TIME = re.compile(r"\[\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4}\]")


def test_bare_invocation_prints_concise_help(sample: Group) -> None:
    """Assert a bare invocation prints concise help to STDOUT, exit 0."""
    result = invoke(sample)
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0] == "Sample data manager [sample 0.0.0+unknown]"
    for heading in ("USAGE:", "COMMANDS:", "EXAMPLES:"):
        assert heading in lines
    assert lines[-1] == "Try 'sample --help' for more information."
    assert "OPTIONS:" not in result.stdout
    assert "example.com/sample" not in result.stdout
    assert result.stderr == ""


def test_bare_invocation_with_debug_prints_concise_help(sample: Group) -> None:
    """Assert `prog -d` still prints the concise help."""
    result = invoke(sample, ["-d"])
    assert result.exit_code == 0
    assert result.stdout.startswith("Sample data manager")


def _headings(help_text: str) -> list[str]:
    """Return the upper-case section headings of a help text, in order."""
    return [
        line
        for line in help_text.splitlines()
        if line.endswith(":") and line.isupper()
    ]


def test_full_help_layout(sample: Group) -> None:
    """Assert `--help` lists usage, options, commands, examples & epilog."""
    result = invoke(sample, ["--help"])
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[:2] == ["USAGE:", "  sample [options] <command>"]
    assert _headings(result.stdout) == [
        "USAGE:",
        "OPTIONS:",
        "COMMANDS:",
        "EXAMPLES:",
    ]
    assert lines.index("EXAMPLES:") < lines.index(
        "  For more information see https://example.com/sample."
    )


def test_command_help_lists_examples_before_epilog(sample: Group) -> None:
    """Assert a command's `--help` lists its examples after the options."""
    result = invoke(sample, ["list", "--help"])
    assert result.exit_code == 0
    assert _headings(result.stdout) == ["USAGE:", "OPTIONS:", "EXAMPLES:"]
    lines = result.stdout.splitlines()
    start = lines.index("EXAMPLES:")
    assert lines[start + 1 : start + 3] == [
        "  sample list --start 2026",
        "  sample list --json",
    ]
    assert lines.index("  Items are listed oldest first.") > start + 2


def test_command_help_without_examples(sample: Group) -> None:
    """Assert a command without `examples=` has no `EXAMPLES:` section."""
    result = invoke(sample, ["download", "--help"])
    assert _headings(result.stdout) == ["USAGE:", "OPTIONS:"]


def test_click_command_with_pyclig_class_takes_examples() -> None:
    """Assert `click.command(cls=pyclig.Command)` accepts `examples=`."""

    @click.command("tool", cls=pyclig.Command, examples=["tool --debug"])
    def tool() -> None:
        """Run the tool."""

    result = CliRunner().invoke(tool, ["--help"])
    assert result.exit_code == 0
    assert "EXAMPLES:\n  tool --debug\n" in result.stdout


def test_commands_listed_in_definition_order(sample: Group) -> None:
    """Assert `COMMANDS:` keeps the order the commands were defined in."""
    lines = invoke(sample).stdout.splitlines()
    start = lines.index("COMMANDS:") + 1
    names = [line.split()[0] for line in lines[start : start + 3]]
    assert names == ["list", "download", "process"]


def test_short_help_option(sample: Group) -> None:
    """Assert `-h` is an alias of `--help`, on commands too."""
    assert invoke(sample, ["-h"]).stdout == invoke(sample, ["--help"]).stdout
    result = invoke(sample, ["list", "-h"])
    assert result.stdout.startswith("USAGE:\n  sample list [options]\n")


@pytest.mark.parametrize("flag", ["-v", "--version"])
def test_version_without_metadata(sample: Group, flag: str) -> None:
    """Assert `-v` prints `prog version`, falling back without metadata."""
    result = invoke(sample, [flag])
    assert result.exit_code == 0
    assert result.stdout == "sample 0.0.0+unknown\n"


def test_version_follows_program_name(
    sample: Group, capsys: pytest.CaptureFixture[str]
) -> None:
    """Assert runs with different program names do not share a version line."""
    for prog in ("alpha", "beta"):
        with pytest.raises(SystemExit):
            sample.main(["-v"], prog_name=prog)
        assert capsys.readouterr().out == f"{prog} 0.0.0+unknown\n"


@pytest.mark.parametrize(
    "args",
    [
        ["-d", "log"],
        ["log", "-d"],
        ["-d", "log", "-d"],
        ["--debug", "grp", "leaf"],
        ["grp", "leaf", "-d"],
        ["grp", "-d", "leaf"],
    ],
)
def test_debug_before_or_after_command(sample: Group, args: list[str]) -> None:
    """Assert `-d` enables debug logging wherever it is placed."""
    result = invoke(sample, args)
    assert result.exit_code == 0
    assert "debug record" in result.stderr
    assert DEBUG_TIME.search(result.stderr)


def test_debug_absent_logs_warnings_only(sample: Group) -> None:
    """Assert warnings & errors print as notices without `-d`."""
    result = invoke(sample, ["log"])
    assert result.stderr == "warning: warning record\nerror: error record\n"


def test_debug_after_invalid_option(sample: Group) -> None:
    """Assert an eager `-d` applies even when a preceding option is invalid."""
    result = invoke(sample, ["list", "--start", "nope", "-d"])
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert "converting 'nope'" in result.stderr


def test_debug_listed_in_command_help(sample: Group) -> None:
    """Assert every command's help lists `-d, --debug`."""
    for args in (["list"], ["grp", "leaf"]):
        assert "-d, --debug" in invoke(sample, [*args, "--help"]).stdout


def test_nested_group_is_pyclig_group(sample: Group) -> None:
    """Assert `@cli.group()` creates a `pyclig.Group` of `pyclig.Command`s."""
    nested = sample.commands["grp"]
    assert isinstance(nested, pyclig.Group)
    assert isinstance(nested.commands["leaf"], pyclig.Command)


def test_application_obj_kept(sample: Group) -> None:
    """Assert pyclig leaves `ctx.obj` to the application."""
    result = invoke(sample, ["-d", "grp", "leaf"])
    assert result.stdout == "set by the group\n"


def test_pass_context_requires_pyclig_command() -> None:
    """Assert `pass_context` rejects a command of a plain click group."""

    @click.group()
    def plain() -> None:
        """Group commands without pyclig."""

    @plain.command()
    @pyclig.pass_context
    def cmd(ctx: pyclig.Context) -> None:
        """Expect a pyclig context."""

    with pytest.raises(TypeError, match="must be a command of a pyclig.Group"):
        CliRunner().invoke(plain, ["cmd"], catch_exceptions=False)


CONFIRM_PROMPT = "Delete every sample item? [y/N]: "
CONFIRM_ERROR = (
    "error: confirmation needed, but STDIN is not a terminal - "
    "pass `--force` to proceed"
)


def test_confirm_skipped_with_force(sample: Group) -> None:
    """Assert `--force` proceeds without a prompt, even off a terminal."""
    result = invoke(sample, ["purge", "--force"])
    assert result.exit_code == 0
    assert result.stdout == "purged\n"
    assert result.stderr == ""


@pytest.mark.parametrize("answer", [None, "y\n"], ids=["empty", "yes"])
def test_confirm_fails_without_terminal_stdin(
    sample: Group, answer: str | None
) -> None:
    """Assert a piped STDIN is a usage error naming `--force`, not a prompt."""
    result = invoke(sample, ["purge"], input=answer)
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert result.stderr.splitlines() == [
        CONFIRM_ERROR,
        "",
        "USAGE:",
        "  sample purge [options]",
        "",
        "Try 'sample purge --help' for more information.",
    ]


def test_confirm_detects_piped_stdin() -> None:
    """Assert a real piped STDIN is detected, even when it holds `y`."""
    result = subprocess.run(
        [sys.executable, str(SAMPLE), "purge"],
        input="y\n",
        capture_output=True,
        text=True,
        env=sample_env(),
        check=False,
    )
    assert result.returncode == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert result.stderr.startswith(f"{CONFIRM_ERROR}\n")


def test_confirm_accepted_on_terminal(sample: Group) -> None:
    """Assert `y` at the STDERR prompt proceeds."""
    result = invoke(sample, ["purge"], in_tty=True, input="y\n")
    assert result.exit_code == 0
    assert result.stdout == "purged\n"
    assert result.stderr == f"{CONFIRM_PROMPT}y\n"


@pytest.mark.parametrize(
    "answer", ["n\n", "\n", ""], ids=["no", "empty", "eof"]
)
def test_confirm_declined_on_terminal(sample: Group, answer: str) -> None:
    """Assert `n`, an empty answer or EOF aborts, exit 1."""
    result = invoke(sample, ["purge"], in_tty=True, input=answer)
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert result.stdout == ""
    assert result.stderr.startswith(CONFIRM_PROMPT)
    assert result.stderr.endswith("error: aborted\n")


@pytest.mark.parametrize(
    ("err_tty", "answer", "stderr"),
    [
        (True, "", f"{CONFIRM_PROMPT}\nerror: aborted\n"),
        (True, "n\n", f"{CONFIRM_PROMPT}n\nerror: aborted\n"),
        (False, "", f"{CONFIRM_PROMPT}error: aborted\n"),
    ],
    ids=["eof-terminal", "no-terminal", "eof-piped"],
)
def test_confirm_aborted_after_the_prompt_line(
    sample: Group, err_tty: bool, answer: str, stderr: str
) -> None:
    """Assert EOF ends a terminal's prompt line before `error: aborted`."""
    result = invoke(
        sample, ["purge"], in_tty=True, err_tty=err_tty, input=answer
    )
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert result.stderr == stderr


def test_confirm_interrupted_on_terminal(sample: Group) -> None:
    """Assert Ctrl-C at the prompt is an interrupt, exit 130."""
    result = invoke(sample, ["purge"], in_tty=True, input=InterruptingInput())
    assert result.exit_code == pyclig.ExitCode.INTERRUPT
    assert result.stdout == ""
    assert result.stderr.endswith("warning: interrupted\n")
    assert "aborted" not in result.stderr


def test_consoles_require_a_run(sample: Group) -> None:
    """Assert `ctx.out` outside a `Group.main` run raises."""
    ctx = pyclig.Context(sample)
    with pytest.raises(RuntimeError, match="only within a pyclig.Group run"):
        _ = ctx.out


def test_shell_completion(run_sample: RunSample) -> None:
    """Assert click's shell completion works through `Group.main`."""
    result = run_sample(
        env={
            "_SAMPLE_COMPLETE": "bash_complete",
            "COMP_WORDS": "sample l",
            "COMP_CWORD": "1",
        }
    )
    assert result.returncode == 0
    assert "plain,list" in result.stdout.splitlines()
    assert "plain,log" in result.stdout.splitlines()


def test_program_name_under_python_m() -> None:
    """Assert the program name is the group name under `python -m`."""
    result = subprocess.run(
        [sys.executable, "-m", "tests.sample_cli", "--help"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[1],
        env=sample_env(),
        check=False,
    )
    assert result.stdout.startswith("USAGE:\n  sample [options] <command>\n")


@pytest.mark.parametrize("value", ["*", "~", "%PATH%", "$HOME"])
def test_arguments_reach_commands_as_typed(
    run_sample: RunSample, value: str
) -> None:
    """Assert globs & variables are never expanded, even on Windows."""
    result = run_sample("show", "--value", value)
    assert result.stdout.splitlines() == [value]
