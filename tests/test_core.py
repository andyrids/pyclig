"""Tests for `pyclig._core` - help, `-d`, `-v` & the group runner."""

import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

import pyclig
from pyclig import Group
from pyclig.testing import invoke
from tests.conftest import SAMPLE, InterruptingInput, RunSample, sample_env

DEBUG_TIME = re.compile(r"\[\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4}\]")

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """An expected failure of the standalone tool."""


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
    """Assert `--help` lists usage, examples, commands, options & epilog."""
    result = invoke(sample, ["--help"])
    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[:2] == ["USAGE:", "  sample [options] <command>"]
    assert _headings(result.stdout) == [
        "USAGE:",
        "EXAMPLES:",
        "COMMANDS:",
        "OPTIONS:",
        "GLOBAL OPTIONS:",
    ]
    assert lines.index("GLOBAL OPTIONS:") < lines.index(
        "  For more information see https://example.com/sample."
    )


def test_command_help_lists_examples_first(sample: Group) -> None:
    """Assert a command's `--help` lists its examples before the options."""
    result = invoke(sample, ["list", "--help"])
    assert result.exit_code == 0
    assert _headings(result.stdout) == [
        "USAGE:",
        "EXAMPLES:",
        "OPTIONS:",
        "GLOBAL OPTIONS:",
    ]
    lines = result.stdout.splitlines()
    start = lines.index("EXAMPLES:")
    assert lines[start + 1 : start + 3] == [
        "  sample list --start 2026",
        "  sample list --json",
    ]
    assert lines.index("  Items are listed oldest first.") > lines.index(
        "GLOBAL OPTIONS:"
    )


def test_command_help_without_examples(sample: Group) -> None:
    """Assert a command without `examples=` has no `EXAMPLES:` section."""
    result = invoke(sample, ["download", "--help"])
    assert _headings(result.stdout) == [
        "USAGE:",
        "OPTIONS:",
        "GLOBAL OPTIONS:",
    ]


def _section(help_text: str, heading: str) -> list[str]:
    """Return the lines of one section of a help text, up to the blank line."""
    lines = help_text.splitlines()
    start = lines.index(heading) + 1
    end = lines.index("", start) if "" in lines[start:] else len(lines)
    return lines[start:end]


def test_global_options_listed_in_full_at_the_root(sample: Group) -> None:
    """Assert the root's `GLOBAL OPTIONS:` lists run flags & its own."""
    help_text = invoke(sample, ["--help"]).stdout
    options = "\n".join(_section(help_text, "OPTIONS:"))
    assert "--debug" not in options
    assert "--audit" not in options
    globals_ = _section(help_text, "GLOBAL OPTIONS:")
    assert globals_[0].startswith("  --audit ")
    assert globals_[1].startswith("  -v, --version ")
    assert globals_[2].startswith("  -d, --debug ")


@pytest.mark.parametrize(
    ("command", "line"),
    [
        (
            "list",
            (
                "--audit, -v/--version, -d/--debug, -q/--quiet, --no-color, "
                "--no-input - see 'sample --help'."
            ),
        ),
        (
            "copy",
            (
                "--audit, -v/--version, --debug, -q/--quiet, --no-color, "
                "--no-input - see 'sample --help'."
            ),
        ),
    ],
)
def test_global_options_one_line_on_subcommands(
    sample: Group, command: str, line: str
) -> None:
    """Assert a subcommand's `GLOBAL OPTIONS:` names the flags briefly."""
    help_text = invoke(sample, [command, "--help"]).stdout
    section = _section(help_text, "GLOBAL OPTIONS:")
    assert " ".join(part.strip() for part in section) == line
    assert "-d, --debug" not in help_text


def test_app_flag_wins_over_a_run_flag(sample: Group) -> None:
    """Assert a command's own `-d` reaches it while `--debug` still works."""
    result = invoke(sample, ["copy", "-d", "/tmp"])
    assert result.exit_code == 0
    assert result.stdout == "dir=/tmp\n"
    assert result.stderr == ""
    result = invoke(sample, ["copy", "--debug", "-d", "/tmp"])
    assert result.stdout == "dir=/tmp\n"
    assert "copy debug record" in result.stderr


@pytest.mark.parametrize(
    "args",
    [
        ["--audit", "audit"],
        ["audit", "--audit"],
        ["--audit", "grp", "leaf"],
        ["grp", "leaf", "--audit"],
    ],
)
def test_global_option_before_or_after_command(
    sample: Group, args: list[str]
) -> None:
    """Assert an app's `GlobalOption` is accepted wherever it is placed."""
    result = invoke(sample, args)
    assert result.exit_code == 0
    assert "audited" in result.stdout.splitlines()


trace_calls: list[tuple[str | None, bool]] = []
"""Every `(command, value)` the `--trace` callback below was called with."""


def _record(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Record a `--trace` callback call."""
    trace_calls.append((ctx.info_name, value))


@pyclig.group("traced", examples=["traced other"])
@click.option(
    "-t",
    "--trace",
    cls=pyclig.GlobalOption,
    callback=_record,
    envvar="TRACED_TRACE",
    hidden=True,
    help="Trace the run.",
)
def traced_cli() -> None:
    """Group commands under a hidden, env-backed global option."""


@traced_cli.command()
@click.option("-t", "--tag", help="A tag, taking `-t` for itself.")
def tagged(tag: str | None) -> None:
    """Print `--tag`."""
    click.echo(f"tag={tag}")


@traced_cli.command()
def other() -> None:
    """Do nothing."""


@pytest.fixture
def traced() -> Group:
    """Return the traced CLI with its callback record cleared."""
    trace_calls.clear()
    return traced_cli


def test_global_option_callback_runs_only_when_given(traced: Group) -> None:
    """Assert the callback never runs with False, whatever the position."""
    invoke(traced, ["--trace", "other"])
    assert trace_calls == [("traced", True)]
    trace_calls.clear()
    invoke(traced, ["other", "--trace"])
    assert trace_calls == [("other", True)]
    trace_calls.clear()
    invoke(traced, ["other"])
    assert trace_calls == []


def test_global_option_from_env_runs_at_each_level(traced: Group) -> None:
    """Assert an `envvar=` flag runs the callback once per level, given."""
    invoke(traced, ["other"], env={"TRACED_TRACE": "1"})
    assert trace_calls == [("traced", True), ("other", True)]


def test_trimmed_global_option_keeps_its_attributes(traced: Group) -> None:
    """Assert a flag trimmed of a taken name keeps `envvar`, `hidden` etc."""
    result = invoke(traced, ["tagged"], env={"TRACED_TRACE": "1"})
    assert result.stdout == "tag=None\n"
    assert trace_calls == [("traced", True), ("tagged", True)]
    assert "--trace" not in invoke(traced, ["tagged", "--help"]).stdout
    trace_calls.clear()
    assert invoke(traced, ["tagged", "--trace"]).exit_code == 0
    assert trace_calls == [("tagged", True)]


region_calls: list[tuple[str | None, str]] = []
"""Every `(command, value)` the `--region` callback below was called with."""


def _set_region(
    ctx: click.Context, param: click.Parameter, value: str
) -> None:
    """Record a `--region` callback call & share the value with commands."""
    region_calls.append((ctx.info_name, value))
    ctx.meta["app.region"] = value


@pyclig.group("regional", examples=["regional --region eu where"])
@click.option(
    "--region",
    cls=pyclig.GlobalOption,
    type=str,
    default="us",
    callback=_set_region,
    envvar="REGIONAL_REGION",
    help="The region to act in.",
)
def regional_cli() -> None:
    """Group commands under a global option taking a value."""


@regional_cli.command()
@pyclig.pass_context
def where(ctx: pyclig.Context) -> None:
    """Print the region the callback shared."""
    click.echo(f"region={ctx.meta.get('app.region')}")


@pytest.fixture
def regional() -> Group:
    """Return the regional CLI with its callback record cleared."""
    region_calls.clear()
    return regional_cli


def test_value_global_option_runs_when_given(regional: Group) -> None:
    """Assert a value option's callback gets the value, at either position."""
    result = invoke(regional, ["--region", "eu", "where"])
    assert result.stdout == "region=eu\n"
    assert region_calls == [("regional", "eu")]
    region_calls.clear()
    result = invoke(regional, ["where", "--region", "ap"])
    assert result.stdout == "region=ap\n"
    assert region_calls == [("where", "ap")]


def test_value_global_option_never_runs_for_its_default(
    regional: Group,
) -> None:
    """Assert `default=` is not "given", so the callback stays silent."""
    result = invoke(regional, ["where"])
    assert result.stdout == "region=None\n"
    assert region_calls == []


def test_value_global_option_from_env_runs_at_each_level(
    regional: Group,
) -> None:
    """Assert `envvar=` counts as given, once per level."""
    result = invoke(regional, ["where"], env={"REGIONAL_REGION": "eu"})
    assert result.stdout == "region=eu\n"
    assert region_calls == [("regional", "eu"), ("where", "eu")]


def test_value_global_option_from_default_map_counts_as_given(
    regional: Group,
) -> None:
    """Assert a `default_map` value runs the callback, as config will."""
    result = CliRunner().invoke(
        regional, ["where"], default_map={"region": "ap"}
    )
    assert result.stdout == "region=ap\n"
    assert region_calls == [("regional", "ap")]


def test_value_global_option_help(regional: Group) -> None:
    """Assert the root shows the option's metavar & a subcommand its name."""
    assert (
        "--region TEXT  The region to act in."
        in invoke(regional, ["--help"]).stdout
    )
    assert (
        "--region, -v/--version, -d/--debug"
        in invoke(regional, ["where", "--help"]).stdout
    )


def test_global_option_is_flag_rules() -> None:
    """Assert no `type=` means a flag & an explicit `is_flag=` wins."""

    def ignore(ctx: click.Context, param: click.Parameter, value: Any) -> None:
        pass

    assert pyclig.GlobalOption(["--a"], callback=ignore).is_flag is True
    assert pyclig.GlobalOption(["--b"], callback=ignore, type=int).is_flag is (
        False
    )
    assert (
        pyclig.GlobalOption(["--c"], callback=ignore, is_flag=False).is_flag
        is False
    )
    assert (
        pyclig.GlobalOption(
            ["--d"], callback=ignore, type=bool, is_flag=True
        ).is_flag
        is True
    )


def test_global_option_reaches_added_command(sample: Group) -> None:
    """Assert `add_command` gives a command the group's global options."""

    @click.command(cls=pyclig.Command)
    @click.pass_context
    def added(ctx: click.Context) -> None:
        """Print whether the run is audited."""
        click.echo(ctx.meta.get("audit", False))

    sample.add_command(added, "added")
    try:
        assert invoke(sample, ["added", "--audit"]).stdout == "True\n"
    finally:
        del sample.commands["added"]


def test_click_command_with_pyclig_class_takes_examples() -> None:
    """Assert `click.command(cls=pyclig.Command)` accepts `examples=`."""

    @click.command("tool", cls=pyclig.Command, examples=["tool --debug"])
    def tool() -> None:
        """Run the tool."""

    result = CliRunner().invoke(tool, ["--help"])
    assert result.exit_code == 0
    assert "EXAMPLES:\n  tool --debug\n" in result.stdout


@pyclig.command("tool", examples=["tool --debug"], errors=(ToolError,))
@click.option("--fail", is_flag=True, help="Raise the expected error.")
@pyclig.pass_context
def tool(ctx: pyclig.Context, fail: bool) -> None:
    """Run the standalone tool."""
    logger.debug("tool debug record")
    if fail:
        raise ToolError("tool failed")
    ctx.out.print("ran")


def test_standalone_command_has_consoles() -> None:
    """Assert a `pyclig.command()` run gives `ctx.out` without a group."""
    result = invoke(tool)
    assert result.exit_code == 0
    assert result.stdout == "ran\n"


def test_standalone_command_debug_logs() -> None:
    """Assert `-d` enables debug logging on a standalone command."""
    result = invoke(tool, ["-d"])
    assert result.exit_code == 0
    assert "tool debug record" in result.stderr
    assert DEBUG_TIME.search(result.stderr)


def test_standalone_command_maps_errors() -> None:
    """Assert a standalone command's `errors=` print `error:`, exit 1."""
    result = invoke(tool, ["--fail"])
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert result.stderr == "error: tool failed\n"


def test_standalone_command_short_help() -> None:
    """Assert `-h` shows a standalone command's help with its examples."""
    result = invoke(tool, ["-h"])
    assert result.exit_code == 0
    assert result.stdout.startswith("USAGE:\n  tool [options]\n")
    assert "EXAMPLES:\n  tool --debug\n" in result.stdout


def test_command_decorator_adds_version() -> None:
    """Assert `pyclig.command()` adds `-v/--version`."""
    assert invoke(tool, ["-v"]).stdout == "tool 0.0.0+unknown\n"


def test_version_after_a_subcommand(sample: Group) -> None:
    """Assert `-v/--version` is global: `prog show -v` prints the version."""
    for args in (["list", "-v"], ["grp", "leaf", "--version"]):
        result = invoke(sample, args)
        assert result.exit_code == 0
        assert result.stdout == "sample 0.0.0+unknown\n"
        assert result.stderr == ""


def test_version_is_a_global_option_in_help(sample: Group) -> None:
    """Assert the root lists `-v/--version` under `GLOBAL OPTIONS:`."""
    help_text = invoke(sample, ["--help"]).stdout
    assert "--version" not in "\n".join(_section(help_text, "OPTIONS:"))
    globals_ = "\n".join(_section(help_text, "GLOBAL OPTIONS:"))
    assert "  -v, --version " in globals_


def test_version_does_nothing_under_resilient_parsing(
    sample: Group, capsys: pytest.CaptureFixture[str]
) -> None:
    """Assert completion can parse `-v` without printing or exiting."""
    for args in (["-v"], ["list", "-v"]):
        with sample.make_context("sample", args, resilient_parsing=True):
            pass
    assert capsys.readouterr().out == ""


def test_subcommand_verbose_wins_over_version_short() -> None:
    """Assert a subcommand's own `-v` reaches it; `--version` still works."""

    @pyclig.group("tool", examples=["tool show"])
    def cli() -> None:
        """Group commands."""

    @cli.command(examples=["tool show -v"])
    @click.option("-v", "--verbose", is_flag=True, help="Say more.")
    def show(verbose: bool) -> None:
        """Show things."""
        click.echo(f"verbose={verbose}")

    assert invoke(cli, ["show", "-v"]).stdout == "verbose=True\n"
    assert invoke(cli, ["show", "--version"]).stdout == "tool 0.0.0+unknown\n"


def test_app_verbose_wins_over_version_short() -> None:
    """Assert an app's `-v/--verbose` keeps `--version` as long form only."""

    @pyclig.command("loud", examples=["loud -v"])
    @click.option("-v", "--verbose", is_flag=True, help="Say more.")
    def loud(verbose: bool) -> None:
        """Run loudly."""
        click.echo(f"verbose={verbose}")

    assert invoke(loud, ["-v"]).stdout == "verbose=True\n"
    assert invoke(loud, ["--version"]).stdout == "loud 0.0.0+unknown\n"
    help_text = invoke(loud, ["--help"]).stdout
    assert "-v, --verbose" in help_text
    assert "  --version  " in help_text
    assert "-v, --version" not in help_text


def test_app_version_flag_replaces_pyclig_version() -> None:
    """Assert an app's own `-v/--version` leaves no pyclig version option."""

    @pyclig.group("own", examples=["own"])
    @click.option("-v", "--version", is_flag=True, help="The app's own.")
    def own(version: bool) -> None:
        """Group commands with an app version flag."""
        click.echo(f"own={version}")

    assert invoke(own, ["--version"]).stdout.startswith("own=True\n")
    assert "Show the version and exit." not in invoke(own, ["--help"]).stdout


def test_custom_help_names_reach_subcommands() -> None:
    """Assert a group's own `help_option_names` replace `-h` below it."""

    @pyclig.group("aided", context_settings={"help_option_names": ["--aide"]})
    def aided() -> None:
        """Group commands with a custom help flag."""

    @aided.command()
    def sub() -> None:
        """Do nothing."""

    result = invoke(aided, ["sub", "--aide"])
    assert result.exit_code == 0
    assert result.stdout.startswith("USAGE:\n  aided sub [options]\n")
    assert invoke(aided, ["sub", "-h"]).exit_code == pyclig.ExitCode.USAGE


def test_nested_errors_rejected(sample: Group) -> None:
    """Assert `errors=` on a subcommand or nested group is a `TypeError`."""
    with pytest.raises(TypeError, match="errors="):

        @sample.group(errors=(ToolError,))
        def nested() -> None:
            """Group commands with its own errors."""

    with pytest.raises(TypeError, match="errors="):
        sample.add_command(tool, "tool")
    assert "tool" not in sample.commands


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


@pytest.mark.parametrize(
    ("args", "path"),
    [
        (["list", "-h", "--strt", "1"], "sample list"),
        (["list", "--strt", "1", "-h"], "sample list"),
        (["list", "--json=1", "--help"], "sample list"),
        (["list", "--start", "-h"], "sample list"),
        (["--typo", "-h"], "sample"),
        (["nosuch", "-h"], "sample"),
    ],
    ids=["before", "after", "flag-value", "as-value", "root-typo", "command"],
)
def test_help_wins_over_a_usage_error(
    sample: Group, args: list[str], path: str
) -> None:
    """Assert a help flag shows help, exit 0, whatever else is wrong."""
    result = invoke(sample, args)
    assert result.exit_code == 0
    assert result.stdout.startswith(f"USAGE:\n  {path} [options]")
    assert result.stderr == ""


@pyclig.group("hosted", examples=["hosted serve -h 0.0.0.0"])
@click.option("-h", "--host", help="The root's own host.")
def hosted(host: str | None) -> None:
    """Group commands whose `-h` means host."""


@hosted.command()
@click.option("-h", "--host", help="The host to serve on.")
def serve(host: str | None) -> None:
    """Serve on `--host`."""
    click.echo(f"host={host}")


@pytest.mark.parametrize(
    "args",
    [["serve", "-h", "x", "--bogus"], ["nosuch", "-h"]],
    ids=["command", "root"],
)
def test_app_help_spelling_is_not_help(args: list[str]) -> None:
    """Assert a command's own `-h` never triggers help, even after an error."""
    result = invoke(hosted, args)
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert "USAGE:\n" in result.stderr
    assert result.stderr.startswith("error: No such ")


def test_app_help_spelling_reaches_the_app() -> None:
    """Assert `-h` reaches a command that declares it, `--help` still helps."""
    assert invoke(hosted, ["serve", "-h", "x"]).stdout == "host=x\n"
    result = invoke(hosted, ["serve", "--bogus", "--help"])
    assert result.exit_code == 0
    assert result.stdout.startswith("USAGE:\n  hosted serve [options]\n")


def test_help_after_double_dash_still_errors(sample: Group) -> None:
    """Assert `-h` after `--` is an argument, so the usage error stands."""
    result = invoke(sample, ["list", "--strt", "1", "--", "-h"])
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert "No such option '--strt'" in result.stderr


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


@pytest.mark.parametrize(
    "args",
    [
        ["--no-color", "fail", "--kind", "mapped"],
        ["fail", "--no-color", "--kind", "mapped"],
    ],
    ids=["before", "after"],
)
def test_no_color_flag_drops_colour_keeps_bold(
    sample: Group, args: list[str]
) -> None:
    """Assert `--no-color` removes colour from both consoles, keeping bold."""
    result = invoke(sample, args, err_tty=True, color=True)
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert "\x1b[1;31m" not in result.stderr
    assert result.stderr.startswith("\x1b[1merror:\x1b[0m")


@pytest.mark.parametrize(
    "args",
    [["-q", "chatter"], ["chatter", "--quiet"]],
    ids=["before", "after"],
)
def test_quiet_drops_info_and_animation(
    sample: Group, args: list[str]
) -> None:
    """Assert `-q` drops `info` from any thread & animation, nothing else."""
    result = invoke(sample, args, err_tty=True, interactive=True)
    assert result.exit_code == 0
    assert result.stdout == "quiet=True\n"
    assert result.stderr == "warning: kept warning\nlive=False\n"


def test_not_quiet_by_default(sample: Group) -> None:
    """Assert `info` & live displays stay without `-q`."""
    result = invoke(sample, ["chatter"], err_tty=True, interactive=True)
    assert result.stdout == "quiet=False\n"
    assert result.stderr == (
        "main info\nworker info\nwarning: kept warning\nlive=True\n"
    )


def test_quiet_keeps_hints(sample: Group) -> None:
    """Assert `-q` keeps the `--help` hint of a usage error & error hints."""
    result = invoke(sample, ["-q", "list", "--bogus"])
    assert result.stderr.endswith(
        "Try 'sample list --help' for more information.\n"
    )
    result = invoke(sample, ["-q", "fail", "--kind", "hinted"])
    assert result.stderr == "error: disk full\nFree some space, then re-run.\n"


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

    with pytest.raises(TypeError, match="not a plain click command") as info:
        CliRunner().invoke(plain, ["cmd"], catch_exceptions=False)
    assert "pyclig.Command" in str(info.value)
    assert "pyclig.Group" not in str(info.value)


CONFIRM_PROMPT = "Delete every sample item? [y/N]: "
CONFIRM_ERROR = (
    "error: confirmation needed, but there is no terminal to ask on - "
    "pass `--force` to proceed"
)
NO_INPUT_ERROR = (
    "error: confirmation needed, but `--no-input` was given - "
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
    result = invoke(sample, ["purge"], err_tty=True, width=120, input=answer)
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
    assert "STDIN is not a terminal" not in result.stderr


def test_confirm_fails_without_terminal_stderr(sample: Group) -> None:
    """Assert a redirected STDERR (`2>log`) fails rather than hide the ask."""
    result = invoke(sample, ["purge"], in_tty=True, input="y\n")
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert result.stderr.startswith(f"{CONFIRM_ERROR}\n")


@pytest.mark.parametrize(
    "args", [["--no-input", "purge"], ["purge", "--no-input"]]
)
def test_confirm_fails_with_no_input(sample: Group, args: list[str]) -> None:
    """Assert `--no-input` fails naming itself & `--force`, even on a TTY."""
    result = invoke(
        sample, args, in_tty=True, err_tty=True, width=120, input="y\n"
    )
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert result.stderr.startswith(f"{NO_INPUT_ERROR}\n")


def test_prompt_option_asks_on_a_terminal(sample: Group) -> None:
    """Assert a `prompt=` option prompts when both terminals are there."""
    result = invoke(
        sample, ["login"], in_tty=True, err_tty=True, input="abc\n"
    )
    assert result.exit_code == 0
    assert result.stdout == "token=abc\n"
    assert result.stderr == "Token: abc\n"


PROMPT_ERROR = (
    "error: '--token' needs a value, but {reason} - "
    "pass it on the command line"
)


@pytest.mark.parametrize(
    ("args", "ttys", "reason"),
    [
        (["login"], False, "there is no terminal to ask on"),
        (["login", "--no-input"], True, "`--no-input` was given"),
        (["--no-input", "login"], True, "`--no-input` was given"),
    ],
    ids=["piped", "flag-after", "flag-before"],
)
def test_prompt_option_fails_instead_of_prompting(
    sample: Group, args: list[str], ttys: bool, reason: str
) -> None:
    """Assert a `prompt=` option fails naming itself when it cannot prompt."""
    result = invoke(
        sample, args, in_tty=ttys, err_tty=ttys, width=120, input="abc\n"
    )
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert result.stderr.startswith(PROMPT_ERROR.format(reason=reason) + "\n")
    assert "Token:" not in result.stderr


@pytest.mark.parametrize(
    ("args", "ttys"),
    [(["greet"], False), (["greet", "--no-input"], True)],
    ids=["piped", "no-input"],
)
def test_prompt_option_with_default_uses_it(
    sample: Group, args: list[str], ttys: bool
) -> None:
    """Assert a `prompt=` option with a default takes it when it cannot ask."""
    result = invoke(sample, args, in_tty=ttys, err_tty=ttys)
    assert result.exit_code == 0
    assert result.stdout == "me now\n"
    assert result.stderr == ""


def test_prompt_option_with_default_still_asks_on_a_terminal(
    sample: Group,
) -> None:
    """Assert a `prompt=` option with a default prompts on a terminal."""
    result = invoke(sample, ["greet"], in_tty=True, err_tty=True, input="\n\n")
    assert result.exit_code == 0
    assert result.stdout == "me now\n"
    assert result.stderr == "Name [me]: \nWhen [now]: \n"


def test_prompt_option_with_none_default_still_fails() -> None:
    """Assert `default=None` counts as no default, so the run fails."""

    @pyclig.command("ask")
    @click.option("--who", prompt="Who", default=None, help="Who.")
    def ask(who: str | None) -> None:
        """Ask who."""
        click.echo(f"who={who}")

    result = invoke(ask, ["--no-input"], in_tty=True, err_tty=True, width=120)
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stderr.startswith("error: '--who' needs a value, but ")


def test_prompt_option_given_needs_no_prompt(sample: Group) -> None:
    """Assert a `prompt=` option given on the command line never prompts."""
    result = invoke(sample, ["login", "--token", "x", "--no-input"])
    assert result.exit_code == 0
    assert result.stdout == "token=x\n"
    assert result.stderr == ""


def test_can_prompt_needs_both_terminals_and_no_flag(sample: Group) -> None:
    """Assert `ctx.can_prompt` is True only with STDIN & STDERR terminals."""
    result = invoke(sample, ["streams"], in_tty=True, err_tty=True)
    assert result.stderr.endswith(" prompt=True\n")
    result = invoke(
        sample, ["--no-input", "streams"], in_tty=True, err_tty=True
    )
    assert result.stderr.endswith(" prompt=False\n")
    result = invoke(sample, ["streams"], in_tty=True)
    assert result.stderr.endswith(" prompt=False\n")


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
    result = invoke(sample, ["purge"], in_tty=True, err_tty=True, input="y\n")
    assert result.exit_code == 0
    assert result.stdout == "purged\n"
    assert result.stderr == f"{CONFIRM_PROMPT}y\n"


@pytest.mark.parametrize(
    "answer", ["n\n", "\n", ""], ids=["no", "empty", "eof"]
)
def test_confirm_declined_on_terminal(sample: Group, answer: str) -> None:
    """Assert `n`, an empty answer or EOF aborts, exit 1."""
    result = invoke(sample, ["purge"], in_tty=True, err_tty=True, input=answer)
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert result.stdout == ""
    assert result.stderr.startswith(CONFIRM_PROMPT)
    assert result.stderr.endswith("error: aborted\n")


@pytest.mark.parametrize(
    ("platform", "answer", "stderr"),
    [
        ("linux", "", f"{CONFIRM_PROMPT}\nerror: aborted\n"),
        # The console echoes the Enter of Ctrl-Z + Enter, not CliRunner
        ("win32", "", f"{CONFIRM_PROMPT}error: aborted\n"),
        ("linux", "n\n", f"{CONFIRM_PROMPT}n\nerror: aborted\n"),
    ],
    ids=["eof-terminal", "eof-windows-console", "no-terminal"],
)
def test_confirm_aborted_after_the_prompt_line(
    sample: Group,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    answer: str,
    stderr: str,
) -> None:
    """Assert EOF ends a terminal's prompt line before `error: aborted`."""
    monkeypatch.setattr(sys, "platform", platform)
    result = invoke(sample, ["purge"], in_tty=True, err_tty=True, input=answer)
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert result.stderr == stderr


def test_confirm_interrupted_on_terminal(sample: Group) -> None:
    """Assert Ctrl-C at the prompt is an interrupt, exit 130."""
    result = invoke(
        sample, ["purge"], in_tty=True, err_tty=True, input=InterruptingInput()
    )
    assert result.exit_code == pyclig.ExitCode.INTERRUPT
    assert result.stdout == ""
    assert result.stderr.endswith("warning: interrupted\n")
    assert "aborted" not in result.stderr


def test_consoles_require_a_run(sample: Group) -> None:
    """Assert `ctx.out` outside a run started by `main()` raises."""
    ctx = pyclig.Context(sample)
    with pytest.raises(RuntimeError, match="started by .*main") as info:
        _ = ctx.out
    assert "pyclig.Group run" not in str(info.value)


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


def test_global_options_offered_by_completion(run_sample: RunSample) -> None:
    """Assert completion on a subcommand offers the global options."""
    result = run_sample(
        env={
            "_SAMPLE_COMPLETE": "bash_complete",
            "COMP_WORDS": "sample list --",
            "COMP_CWORD": "2",
        }
    )
    offered = set(result.stdout.splitlines())
    assert {"plain,--json", "plain,--audit", "plain,--debug"} <= offered


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


_GLOBS = """
import click

import pyclig


@pyclig.command("globs")
@click.argument("names", nargs=-1)
def main(names: tuple[str, ...]) -> None:
    click.echo(" ".join(names))


main()
"""


def test_several_arguments_arrive_as_typed(tmp_path: Path) -> None:
    """Assert `nargs=-1` gets `*.txt` itself, beside files it would match.

    NOTE: No shell is involved, so only the program could expand the glob:
    click does on Windows unless told not to, as `pyclig.Command.main` does.
    """
    for name in ("a.txt", "b.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    script = tmp_path / "globs.py"
    script.write_text(_GLOBS, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), "*.txt", "c.txt", "?.txt"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=sample_env(),
        check=False,
    )
    assert result.stderr == ""
    assert result.stdout == "*.txt c.txt ?.txt\n"


_RECORDS: list[dict[str, object]] = [
    {"key": "a", "size": 1, "ok": True, "note": None},
    {"key": "b\tc\n\nd", "size": 2, "ok": False, "note": "x"},
]


def _emitter(
    records: list[dict[str, object]], **kwargs: Any
) -> pyclig.Command:
    """Return a command that emits `records` with `kwargs`."""

    @pyclig.command("emit")
    @pyclig.options.json_output()
    @pyclig.options.plain()
    @pyclig.pass_context
    def emit(ctx: pyclig.Context, json_output: bool) -> None:
        """Emit the records."""
        ctx.emit(records, **kwargs)

    return emit


def test_emit_json_dumps_records_and_drops_caption() -> None:
    """Assert `--json` prints an indented list & no caption anywhere."""
    result = invoke(_emitter(_RECORDS, caption="2 rows"), ["--json"])
    assert result.stdout == json.dumps(_RECORDS, indent=2) + "\n"
    assert result.stderr == ""


def test_emit_json_stringifies_other_values() -> None:
    """Assert values JSON cannot encode print as `str()`, as plain does."""
    cli = _emitter([{"path": Path("a") / "b", "day": date(2026, 1, 2)}])
    assert json.loads(invoke(cli, ["--json"]).stdout) == [
        {"path": str(Path("a") / "b"), "day": "2026-01-02"}
    ]


def test_emit_plain_is_tsv_with_the_caption_on_stderr() -> None:
    """Assert plain is headerless TSV: blanks, lowercase bools, no breaks."""
    result = invoke(_emitter(_RECORDS, caption="2 rows"))
    assert result.stdout == "a\t1\ttrue\t\nb c d\t2\tfalse\tx\n"
    assert result.stderr == "2 rows\n"


def test_emit_plain_columns_come_from_the_first_record() -> None:
    """Assert later records follow the first's keys, blank when missing."""
    cli = _emitter([{"a": 1, "b": 2}, {"b": 3, "c": 4}])
    assert invoke(cli).stdout == "1\t2\n\t3\n"


def test_emit_plain_caption_dropped_when_quiet() -> None:
    """Assert `-q` keeps the rows & drops the caption, which is `info`."""
    result = invoke(_emitter(_RECORDS, caption="2 rows"), ["-q"])
    assert result.stdout.count("\n") == 2
    assert result.stderr == ""


def test_emit_human_prints_a_default_table_with_caption() -> None:
    """Assert a terminal gets a headed table, its caption below it."""
    result = invoke(_emitter(_RECORDS, caption="2 rows"), out_tty=True)
    lines = result.stdout.splitlines()
    head = next(i for i, line in enumerate(lines) if "key" in line)
    assert lines[head].split() == ["key", "size", "ok", "note"]
    assert lines[head + 1].strip().startswith("─")
    assert lines[head + 2].split() == ["a", "1", "true"]
    assert lines[head + 3].split() == ["b", "c", "d", "2", "false", "x"]
    assert lines[-1].strip() == "2 rows"
    assert "\t" not in result.stdout
    assert result.stderr == ""


def test_emit_human_uses_the_table_factory() -> None:
    """Assert `table=` builds the table, which still takes the caption."""

    def table() -> Any:
        from rich.table import Table

        custom = Table("Custom")
        custom.add_row("made")
        return custom

    cli = _emitter(_RECORDS, table=table, caption="cap")
    result = invoke(cli, out_tty=True)
    assert "Custom" in result.stdout
    assert "made" in result.stdout
    assert "key" not in result.stdout
    assert result.stdout.splitlines()[-1].strip() == "cap"


@pytest.mark.parametrize(
    "cell", ["[/b]", "[red]x", ":warning:", "a\x1b[2Jb\x9b"]
)
def test_emit_human_prints_cells_literally(cell: str) -> None:
    """Assert cells print markup & emoji codes as written, controls gone."""
    result = invoke(_emitter([{cell: cell}]), out_tty=True)
    shown = cell.replace("\x1b", "").replace("\x9b", "")
    assert result.stdout.count(shown) == 2


def test_emit_empty_records() -> None:
    """Assert no records give `[]`, nothing, or the caption via `info`."""
    assert invoke(_emitter([], caption="none"), ["--json"]).stdout == "[]\n"
    for out_tty in (False, True):
        result = invoke(_emitter([], caption="none"), out_tty=out_tty)
        assert result.stdout == ""
        assert result.stderr == "none\n"


def _nested(**kwargs: Any) -> tuple[pyclig.Group, list[str]]:
    """Return a two-level group & the list its callbacks append to."""
    calls: list[str] = []

    @pyclig.group("prog", **kwargs)
    def prog() -> None:
        """Run the program."""
        calls.append("root")

    @prog.group()
    def grp() -> None:
        """Run the nested group."""
        calls.append("grp")

    @grp.command()
    @click.option("--value", required=True, help="A value.")
    def leaf(value: str) -> None:
        """Run the nested command."""
        calls.append("leaf")

    @prog.command()
    @click.option("--value", required=True, help="A value.")
    def req(value: str) -> None:
        """Run with a required option."""
        calls.append("req")

    return prog, calls


def test_help_command_prints_full_help_without_the_callback() -> None:
    """Assert `prog help` is `prog --help`, exit 0, & no callback runs."""
    prog, calls = _nested()
    result = invoke(prog, ["help"])
    assert result.exit_code == 0
    assert calls == []
    assert result.stdout == invoke(_nested()[0], ["--help"]).stdout
    assert result.stderr == ""


def test_help_command_on_an_empty_group() -> None:
    """Assert `help` works on a group with no commands."""

    @pyclig.group("empty")
    def empty() -> None:
        """Run the empty program."""

    result = invoke(empty, ["help"])
    assert result.exit_code == 0
    assert result.stdout == invoke(empty, ["--help"]).stdout


@pytest.mark.parametrize(
    ("args", "path"),
    [
        (["help", "grp", "leaf"], ["grp", "leaf"]),
        (["help", "grp"], ["grp"]),
        (["-d", "help", "req"], ["req"]),
        (["help", "-d", "req"], ["req"]),
        (["help", "help"], []),
    ],
)
def test_help_command_names_a_command(
    args: list[str], path: list[str]
) -> None:
    """Assert `help NAME...` is that command's `--help`, with no callback."""
    prog, calls = _nested()
    result = invoke(prog, args)
    assert result.exit_code == 0
    assert calls == []
    assert result.stdout == invoke(_nested()[0], [*path, "--help"]).stdout


def test_help_command_inside_a_group_runs_the_root_callback() -> None:
    """Assert `prog grp help leaf` is `prog grp leaf --help`: root runs."""
    prog, calls = _nested()
    result = invoke(prog, ["grp", "help", "leaf"])
    assert result.exit_code == 0
    assert calls == ["root"]
    expected = invoke(_nested()[0], ["grp", "leaf", "--help"]).stdout
    assert result.stdout == expected


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["help", "nosuch"], "No such command 'nosuch'"),
        (["help", "req", "x"], "Got unexpected extra argument (x)"),
        (["help", "grp", "nosuch"], "No such command 'nosuch'"),
    ],
)
def test_help_command_unknown_name_is_a_usage_error(
    args: list[str], message: str
) -> None:
    """Assert a name `help` cannot resolve is a usage error, exit 2."""
    prog, _ = _nested()
    result = invoke(prog, args)
    assert result.exit_code == 2
    assert message in result.stderr
    assert result.stdout == ""


def test_help_command_yields_to_the_apps_own() -> None:
    """Assert a group's own `help` command wins over the built-in."""
    prog, _ = _nested()

    @prog.command("help")
    def help_() -> None:
        """Print the app's own help."""
        click.echo("mine")

    assert invoke(prog, ["help", "anything"]).exit_code == 2
    assert invoke(prog, ["help"]).stdout == "mine\n"


def test_help_command_is_not_listed_and_errors_after_root_options() -> None:
    """Assert `help` is absent from COMMANDS & a required root option wins."""
    prog, _ = _nested()
    listed = [
        line.split()[0]
        for line in invoke(prog, ["--help"]).stdout.splitlines()
        if line.startswith("  ")
    ]
    assert "help" not in listed
    assert "req" in listed

    @pyclig.group("strict")
    @click.option("--token", required=True)
    def strict(token: str) -> None:
        """Run with a required root option."""

    @strict.command()
    def sub() -> None:
        """Run the command."""

    result = invoke(strict, ["help", "sub"])
    assert result.exit_code == 2
    assert "Missing option '--token'" in result.stderr


def test_help_command_is_not_intercepted_for_completion() -> None:
    """Assert resilient parsing, as in tab completion, resolves normally."""
    prog, _ = _nested()
    ctx = prog.make_context("prog", ["help"], resilient_parsing=True)
    assert prog.resolve_command(ctx, ["help", "x"]) == (None, None, ["x"])


def _pager_cli(body: Callable[[pyclig.Context], None]) -> pyclig.Command:
    """Return a command running `body` inside `ctx.pager()`."""

    @pyclig.command("page")
    @pyclig.options.json_output()
    @pyclig.options.plain()
    @pyclig.pass_context
    def page(ctx: pyclig.Context, json_output: bool) -> None:
        """Page the body's output."""
        with ctx.pager():
            body(ctx)

    return page


@pytest.fixture
def less_pager(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name `less` as the pager with `LESS` unset, whatever the host."""
    monkeypatch.setenv("PAGER", "less")
    monkeypatch.delenv("LESS", raising=False)


@pytest.mark.usefixtures("less_pager")
def test_pager_is_a_no_op_unless_human() -> None:
    """Assert plain & JSON output never go near a pager."""
    cli = _pager_cli(lambda ctx: ctx.emit(_RECORDS))
    with patch("click.echo_via_pager") as spy:
        plain, as_json = invoke(cli), invoke(cli, ["--json"])
    spy.assert_not_called()
    assert plain.stdout == invoke(_emitter(_RECORDS)).stdout
    assert as_json.stdout == invoke(_emitter(_RECORDS), ["--json"]).stdout


@pytest.mark.usefixtures("less_pager")
def test_pager_pages_human_output_once_without_its_newline() -> None:
    """Assert the block's console output is one page, click adding `\\n`."""
    cli = _pager_cli(lambda ctx: ctx.emit(_RECORDS, caption="2 rows"))
    with patch("click.echo_via_pager") as spy:
        result = invoke(cli, out_tty=True)
    assert result.exit_code == 0
    spy.assert_called_once()
    expected = invoke(_emitter(_RECORDS, caption="2 rows"), out_tty=True)
    assert spy.call_args[0][0] == expected.stdout.rstrip("\n")
    assert "2 rows" in spy.call_args[0][0].splitlines()[-1]


@pytest.mark.usefixtures("less_pager")
def test_pager_holds_console_output_but_not_click_echo() -> None:
    """Assert `click.echo` bypasses the page, which prints at block end."""

    def body(ctx: pyclig.Context) -> None:
        ctx.out.print("buffered")
        click.echo("direct")

    result = invoke(_pager_cli(body), out_tty=True)
    assert result.stdout == "direct\nbuffered\n"


@pytest.mark.usefixtures("less_pager")
def test_pager_flushes_output_unpaged_when_the_body_raises() -> None:
    """Assert a raise skips the pager but what was printed still prints."""

    def body(ctx: pyclig.Context) -> None:
        ctx.out.print("partial")
        raise RuntimeError("boom")

    with patch("click.echo_via_pager") as spy:
        result = invoke(_pager_cli(body), out_tty=True)
    spy.assert_not_called()
    assert result.stdout == "partial\n"
    assert result.exit_code == pyclig.ExitCode.INTERNAL


@pytest.mark.usefixtures("less_pager")
def test_pager_keeps_styles_for_the_pager() -> None:
    """Assert styled console output reaches the pager with its codes."""
    cli = _pager_cli(lambda ctx: pyclig.summary(ctx.out, message="done"))
    with patch("click.echo_via_pager") as spy:
        invoke(cli, out_tty=True, color=True)
    assert spy.call_args[0][0] == "\x1b[32m✓\x1b[0m done"


@pytest.mark.usefixtures("less_pager")
def test_pager_sets_less_flags_for_the_call_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assert `LESS=-FIRX` applies to the pager call only, unless set."""
    seen: list[str | None] = []
    cli = _pager_cli(lambda ctx: ctx.out.print("x"))
    record = lambda *a, **k: seen.append(os.environ.get("LESS"))  # noqa: E731
    with patch("click.echo_via_pager", side_effect=record):
        invoke(cli, out_tty=True)
        assert "LESS" not in os.environ
        monkeypatch.setenv("LESS", "-X")
        invoke(cli, out_tty=True)
    assert seen == ["-FIRX", "-X"]


@pytest.mark.parametrize(
    ("platform", "paged"), [("win32", False), ("linux", True)]
)
def test_pager_is_opt_in_on_windows(
    monkeypatch: pytest.MonkeyPatch, platform: str, paged: bool
) -> None:
    """Assert a blank `PAGER` prints directly on Windows, pages elsewhere."""
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv("PAGER", " ")
    cli = _pager_cli(lambda ctx: ctx.emit(_RECORDS))
    with patch("click.echo_via_pager") as spy:
        result = invoke(cli, out_tty=True)
    assert spy.call_count == int(paged)
    expected = invoke(_emitter(_RECORDS), out_tty=True).stdout
    assert result.stdout == ("" if paged else expected)


@pytest.mark.parametrize(
    ("platform", "pager", "less", "color"),
    [
        ("win32", "less", None, True),
        ("win32", "LESS.EXE", None, True),
        ("win32", r'"C:\Program Files\Git\usr\bin\less.exe"', None, True),
        ("win32", "more", None, None),
        ("win32", "less", "-X", None),
        ("linux", "less", None, True),
        ("linux", "/usr/bin/less -S", None, True),
        ("linux", "cat", None, None),
        ("linux", " ", None, None),
    ],
)
def test_pager_forces_colour_only_for_less_in_raw_mode(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    pager: str,
    less: str | None,
    color: bool | None,
) -> None:
    """Assert colour is on only for `less` with pyclig's own `LESS` flags."""
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setenv("PAGER", pager)
    if less is None:
        monkeypatch.delenv("LESS", raising=False)
    else:
        monkeypatch.setenv("LESS", less)
    cli = _pager_cli(lambda ctx: ctx.out.print("x"))
    with patch("click.echo_via_pager") as spy:
        invoke(cli, out_tty=True)
    assert spy.call_args[1]["color"] is color


def test_emit_json_refuses_nan() -> None:
    """Assert a NaN record is a bug, exit 70, never bare `NaN` on STDOUT."""
    result = invoke(_emitter([{"x": float("nan")}]), ["--json"])
    assert result.exit_code == pyclig.ExitCode.INTERNAL
    assert result.stdout == ""


@pyclig.group("sever")
def sever_cli() -> None:
    """Run severe actions."""


@sever_cli.command()
@pyclig.options.force()
@pyclig.options.confirm()
@pyclig.pass_context
def drop(ctx: pyclig.Context, force: bool, confirmed: str | None) -> None:
    """Drop the `prod` database."""
    pyclig.confirm_name(
        ctx, message="Drop prod?", name="prod", confirmed=confirmed
    )
    click.echo("dropped")


SEVERE_PROMPT = "Drop prod? Type 'prod' to confirm: "


def test_confirm_name_matching_flag_proceeds() -> None:
    """Assert `--confirm=NAME` returns without a prompt."""
    result = invoke(sever_cli, ["drop", "--confirm=prod"])
    assert result.exit_code == 0
    assert result.stdout == "dropped\n"
    assert result.stderr == ""


def test_confirm_name_mismatch_is_a_usage_error() -> None:
    """Assert a wrong `--confirm` names the expected name, exit 2."""
    result = invoke(
        sever_cli, ["drop", "--confirm=dev"], in_tty=True, err_tty=True
    )
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert "`prod`" in result.stderr


def test_confirm_name_cannot_prompt_names_the_flag() -> None:
    """Assert no terminal fails naming `--confirm=NAME`, exit 2."""
    result = invoke(sever_cli, ["drop"])
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert "there is no terminal to ask on" in result.stderr
    assert "pass `--confirm=prod` to proceed" in result.stderr


def test_confirm_name_no_input_names_the_flag() -> None:
    """Assert `--no-input` fails naming itself & `--confirm=NAME`."""
    result = invoke(
        sever_cli, ["--no-input", "drop"], in_tty=True, err_tty=True
    )
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert "`--no-input` was given" in result.stderr
    assert "--confirm=prod" in result.stderr


def test_confirm_name_force_does_not_bypass() -> None:
    """Assert `--force` neither skips nor satisfies the confirmation."""
    result = invoke(sever_cli, ["drop", "--force"])
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""


def test_confirm_name_typed_match_proceeds() -> None:
    """Assert typing the name at the STDERR prompt proceeds."""
    result = invoke(
        sever_cli, ["drop"], in_tty=True, err_tty=True, input="prod\n"
    )
    assert result.exit_code == 0
    assert result.stdout == "dropped\n"
    assert result.stderr == f"{SEVERE_PROMPT}prod\n"


@pytest.mark.parametrize(
    "answer", ["dev\n", "\n", ""], ids=["mismatch", "empty", "eof"]
)
def test_confirm_name_typed_otherwise_aborts(answer: str) -> None:
    """Assert a wrong name, an empty answer or EOF aborts, exit 1."""
    result = invoke(
        sever_cli, ["drop"], in_tty=True, err_tty=True, input=answer
    )
    assert result.exit_code == pyclig.ExitCode.FAILURE
    assert result.stdout == ""
    assert result.stderr.startswith(SEVERE_PROMPT)
    assert result.stderr.endswith("error: aborted\n")


def test_confirm_name_interrupted_on_terminal() -> None:
    """Assert Ctrl-C at the prompt is an interrupt, exit 130."""
    result = invoke(
        sever_cli,
        ["drop"],
        in_tty=True,
        err_tty=True,
        input=InterruptingInput(),
    )
    assert result.exit_code == pyclig.ExitCode.INTERRUPT
    assert result.stderr.endswith("warning: interrupted\n")


@pyclig.group("files")
def files_cli() -> None:
    """Read & write files."""


@files_cli.command()
@click.argument("source", type=click.File("r"), default="-")
def count(source: Any) -> None:
    """Count the lines of SOURCE."""
    click.echo(len(source.readlines()))


@files_cli.command()
@click.option("--from", "sources", type=click.File("r"), multiple=True)
@click.option("--to", "target", type=click.File("w"), default="-")
def join(sources: tuple[Any, ...], target: Any) -> None:
    """Join the files into one."""
    target.write("".join(source.read() for source in sources))


@pytest.mark.parametrize(
    "args",
    [["count", "-"], ["count"], ["join", "--from", "-"]],
    ids=["dash", "default", "multiple"],
)
def test_file_refuses_a_terminal_stdin(args: list[str]) -> None:
    """Assert `-` for a file to read is a usage error on a terminal."""
    result = invoke(files_cli, args, in_tty=True, input="never read\n")
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""
    assert (
        "STDIN is a terminal - pipe the input in or name a file"
        in result.stderr
    )
    assert f"Try 'files {args[0]} --help'" in result.stderr


def test_file_reads_a_piped_stdin_or_a_named_file(tmp_path: Path) -> None:
    """Assert a pipe, a named file & a file to write are left alone."""
    assert invoke(files_cli, ["count"], input="a\nb\n").stdout == "2\n"
    named = tmp_path / "three.txt"
    named.write_text("a\nb\nc\n", encoding="utf-8")
    result = invoke(files_cli, ["count", str(named)], in_tty=True)
    assert result.stdout == "3\n"
    result = invoke(files_cli, ["join", "--from", str(named)], in_tty=True)
    assert result.stdout == "a\nb\nc\n"


def test_file_help_and_completion_ignore_a_terminal_stdin() -> None:
    """Assert `--help` & resilient parsing never fail on the default `-`."""
    result = invoke(files_cli, ["count", "--help"], in_tty=True)
    assert result.exit_code == 0
    with patch("pyclig._run.is_tty", return_value=True):
        with count.make_context("count", [], resilient_parsing=True):
            pass
        with pytest.raises(click.BadParameter, match="STDIN is a terminal"):
            count.make_context("count", [])


@pyclig.group("dep")
def dep_cli() -> None:
    """Keep old spellings working."""


@dep_cli.command(deprecated="use 'dep new'")
@pyclig.pass_context
def old(ctx: pyclig.Context) -> None:
    """Do it the old way."""
    click.echo(ctx.get_help().splitlines()[3])


@dep_cli.command(deprecated=True)
def older() -> None:
    """Do it the older way."""
    click.echo("ran")


@dep_cli.group(deprecated="use 'dep'")
def legacy() -> None:
    """Group the old commands."""


@legacy.command()
def leaf() -> None:
    """Run below a deprecated group."""
    click.echo("leaf")


@dep_cli.command()
@click.option("--from", "source", deprecated="use --source")
@click.option("--source", default="here")
@click.option("--fast", is_flag=True, deprecated=True, envvar="DEP_FAST")
@click.argument("extra", required=False, deprecated=True)
def new(source: str, fast: bool, extra: str | None) -> None:
    """Do it the new way."""
    click.echo(f"{source} {fast} {extra}")


@pytest.mark.parametrize(
    ("args", "stdout", "stderr"),
    [
        (
            ["old"],
            "  Do it the old way. (DEPRECATED: use 'dep new')\n",
            "warning: command 'old' is deprecated - use 'dep new'\n",
        ),
        (["older"], "ran\n", "warning: command 'older' is deprecated\n"),
        (
            ["legacy", "leaf"],
            "leaf\n",
            "warning: command 'legacy' is deprecated - use 'dep'\n",
        ),
        (
            ["new", "--from", "there"],
            "there False None\n",
            "warning: option '--from' is deprecated - use --source\n",
        ),
        (
            ["new", "--fast", "more"],
            "here True more\n",
            (
                "warning: option '--fast' is deprecated\n"
                "warning: argument 'EXTRA' is deprecated\n"
            ),
        ),
        (["new"], "here False None\n", ""),
    ],
    ids=["reason", "bare", "group", "option", "flag-argument", "not-given"],
)
def test_deprecated_use_warns_on_stderr(
    args: list[str], stdout: str, stderr: str
) -> None:
    """Assert a deprecated command or parameter prints one `warning:` line.

    NOTE: `old` prints its own help while it runs, so the deprecation label
    must already be back in place inside the callback.
    """
    result = invoke(dep_cli, args)
    assert result.exit_code == 0
    assert result.stdout == stdout
    assert result.stderr == stderr
    assert "DeprecationWarning" not in result.output


def test_deprecated_parameter_from_the_environment_warns() -> None:
    """Assert an env var counts as given, as click decides."""
    result = invoke(dep_cli, ["new"], env={"DEP_FAST": "1"})
    assert result.stdout == "here True None\n"
    assert result.stderr == "warning: option '--fast' is deprecated\n"


def test_deprecated_stays_marked_in_help() -> None:
    """Assert help keeps `(DEPRECATED)` & prints no warning."""
    result = invoke(dep_cli, ["--help"])
    assert "(DEPRECATED: use 'dep new')" in result.stdout
    assert "(DEPRECATED)" in result.stdout
    result = invoke(dep_cli, ["new", "--help"])
    assert "(DEPRECATED: use --source)" in result.stdout
    assert "[EXTRA!]" in result.stdout
    assert result.stderr == ""
    assert old.deprecated == "use 'dep new'"


def test_deprecated_parameter_silent_while_completing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Assert resilient parsing prints no warning."""
    with new.make_context("new", ["--fast"], resilient_parsing=True):
        pass
    assert capsys.readouterr().err == ""


def _concise(count: int) -> str:
    """Return the concise help of a command with `count` visible options."""

    @pyclig.command("few", examples=["few --opt-0 x"], no_args_is_help=True)
    @click.option("--secret", hidden=True)
    @click.option("--trace", cls=pyclig.GlobalOption, callback=print)
    def few(**kwargs: Any) -> None:
        """Take a few options."""

    for index in range(count):
        few.params.append(click.Option([f"--opt-{index}"], help="An option."))
    result = invoke(few)
    assert result.exit_code == pyclig.ExitCode.USAGE
    return result.stderr


@pytest.mark.parametrize("count", [1, 6])
def test_concise_help_lists_a_few_options(count: int) -> None:
    """Assert concise help lists 1 to 6 own options after the examples."""
    lines = _concise(count).splitlines()
    start = lines.index("OPTIONS:")
    assert lines.index("EXAMPLES:") < start
    assert lines[start + 1 : start + 1 + count] == [
        f"  --opt-{index} TEXT  An option." for index in range(count)
    ]
    assert lines[start + 1 + count] == ""
    assert lines[-1] == "Try 'few --help' for more information."
    for absent in ("--secret", "--trace", "--help", "--debug", "--version"):
        assert absent not in "\n".join(lines[:-1])


@pytest.mark.parametrize("count", [0, 7])
def test_concise_help_omits_no_or_many_options(count: int) -> None:
    """Assert concise help has no `OPTIONS:` for none or more than 6."""
    assert "OPTIONS:" not in _concise(count)


@pyclig.group(
    "learn",
    docs="https://example.com/learn",
    epilog="Good luck.",
    examples=["learn more"],
)
def learn_cli() -> None:
    """Point at the documentation."""


@learn_cli.command(docs="https://example.com/learn/more", no_args_is_help=True)
@click.argument("topic")
def more(topic: str) -> None:
    """Read more about TOPIC."""


@learn_cli.command()
def less() -> None:
    """Read less."""


def test_learn_more_is_the_last_section() -> None:
    """Assert `docs=` & the bug tracker close the root's full help."""
    with patch("pyclig._run._project_url", return_value="https://x.test/bugs"):
        result = invoke(learn_cli, ["--help"])
    assert _headings(result.stdout)[-1] == "LEARN MORE:"
    assert result.stdout.endswith(
        "\n  Good luck.\n"
        "\n"
        "LEARN MORE:\n"
        "  Docs    https://example.com/learn\n"
        "  Issues  https://x.test/bugs\n"
    )


def test_learn_more_on_a_subcommand_is_its_own_docs() -> None:
    """Assert a subcommand shows its `docs=` & never the bug tracker."""
    with patch("pyclig._run._project_url", return_value="https://x.test/bugs"):
        result = invoke(learn_cli, ["more", "--help"])
        assert (
            "LEARN MORE:" not in invoke(learn_cli, ["less", "--help"]).stdout
        )
    assert result.stdout.endswith(
        "\nLEARN MORE:\n  Docs  https://example.com/learn/more\n"
    )
    assert "Issues" not in result.stdout


def test_learn_more_absent_without_links_and_from_concise_help(
    sample: Group,
) -> None:
    """Assert no section without a link, & none in concise help at all."""
    assert "LEARN MORE:" not in invoke(sample, ["--help"]).stdout
    with patch("pyclig._run._project_url", return_value="https://x.test/bugs"):
        assert "LEARN MORE:" not in invoke(learn_cli).stdout
        assert "LEARN MORE:" not in invoke(learn_cli, ["more"]).stderr


@pyclig.group("ex")
def ex_cli() -> None:
    """Show examples."""


@ex_cli.command(
    examples=[
        "ex mixed --count\n3 items\n\n1 skipped\n",
        "ex mixed --json",
        "ex mixed --all\n4 items",
    ],
    no_args_is_help=True,
)
@click.argument("item")
def mixed(item: str) -> None:
    """Show examples with their output."""


@ex_cli.command(examples=["ex single --count", "ex single --json"])
def single() -> None:
    """Show examples without output."""


def test_multi_line_example_shows_its_output() -> None:
    """Assert the lines after an invocation are its output, indented more.

    NOTE: Examples are parted by a blank line once any of them has output;
    a blank line of the output itself carries no trailing spaces.
    """
    expected = (
        "EXAMPLES:\n"
        "  ex mixed --count\n"
        "    3 items\n"
        "\n"
        "    1 skipped\n"
        "\n"
        "  ex mixed --json\n"
        "\n"
        "  ex mixed --all\n"
        "    4 items\n"
        "\n"
    )
    assert expected in invoke(ex_cli, ["mixed", "--help"]).stdout
    assert expected in invoke(ex_cli, ["mixed"]).stderr


def test_single_line_examples_are_unchanged() -> None:
    """Assert one-line examples stay one per line, with nothing between."""
    help_text = invoke(ex_cli, ["single", "--help"]).stdout
    assert (
        "EXAMPLES:\n  ex single --count\n  ex single --json\n\n" in help_text
    )


def test_nested_global_option_points_at_its_group() -> None:
    """Assert a subcommand's pointer names the group declaring each flag."""

    @pyclig.group("tool")
    def cli() -> None:
        """Group commands."""

    @cli.group()
    @click.option("--trace", cls=pyclig.GlobalOption, callback=print)
    def grp() -> None:
        """Group traced commands."""

    @grp.command()
    def leaf() -> None:
        """Run traced."""

    help_text = invoke(cli, ["grp", "leaf", "--help"]).stdout
    section = _section(help_text, "GLOBAL OPTIONS:")
    assert " ".join(part.strip() for part in section[:2]) == (
        "-v/--version, -d/--debug, -q/--quiet, --no-color, --no-input - "
        "see 'tool --help'."
    )
    assert section[2:] == ["  --trace - see 'tool grp --help'."]
    assert "  --trace\n" in invoke(cli, ["grp", "--help"]).stdout
    assert "--trace" not in invoke(cli, ["--help"]).stdout
