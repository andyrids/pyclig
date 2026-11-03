"""Tests for `pyclig._core` - help, `-d`, `-v` & the group runner."""

import logging
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
    assert globals_[1].startswith("  -d, --debug ")


@pytest.mark.parametrize(
    ("command", "line"),
    [
        (
            "list",
            (
                "  --audit, -d/--debug, -q/--quiet, --no-color, --no-input - "
                "see 'sample --help'."
            ),
        ),
        (
            "copy",
            (
                "  --audit, --debug, -q/--quiet, --no-color, --no-input - "
                "see 'sample --help'."
            ),
        ),
    ],
)
def test_global_options_one_line_on_subcommands(
    sample: Group, command: str, line: str
) -> None:
    """Assert a subcommand's `GLOBAL OPTIONS:` is one line naming the flags."""
    help_text = invoke(sample, [command, "--help"]).stdout
    assert _section(help_text, "GLOBAL OPTIONS:") == [line]
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
