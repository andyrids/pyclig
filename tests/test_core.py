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
from tests.conftest import RunSample, sample_env

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


def test_full_help_layout(sample: Group) -> None:
    """Assert `--help` lists usage, options, commands, examples & epilog."""
    result = invoke(sample, ["--help"])
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[:2] == ["USAGE:", "  sample [options] <command>"]
    headings = [
        line for line in lines if line.endswith(":") and line.isupper()
    ]
    assert headings == ["USAGE:", "OPTIONS:", "COMMANDS:", "EXAMPLES:"]
    assert lines.index("EXAMPLES:") < lines.index(
        "  For more information see https://example.com/sample."
    )


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
