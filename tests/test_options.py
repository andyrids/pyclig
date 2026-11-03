"""Tests for `pyclig.options` - the standard flags."""

import click
import pytest

import pyclig
from pyclig import Group
from pyclig.testing import invoke
from tests.conftest import RunSample


@pyclig.group("flags")
def cli() -> None:
    """Accept every standard flag."""


@cli.command()
@pyclig.options.json_output()
@pyclig.options.select_all(help="Select every archive.")
@pyclig.options.force()
@pyclig.options.dry_run()
def run(
    json_output: bool, select_all: bool, force: bool, dry_run: bool
) -> None:
    """Print the flag values."""
    click.echo(f"{json_output} {select_all} {force} {dry_run}")


def test_flags_default_off() -> None:
    """Assert the standard flags default to False."""
    assert invoke(cli, ["run"]).stdout == "False False False False\n"


def test_flags_short_and_long_names() -> None:
    """Assert `--json`, `-a/--all`, `-f/--force` & `-n/--dry-run` work."""
    result = invoke(cli, ["run", "--json", "-a", "-f", "-n"])
    assert result.stdout == "True True True True\n"
    result = invoke(cli, ["run", "--all", "--force", "--dry-run"])
    assert result.stdout == "False True True True\n"


def test_flag_help_override() -> None:
    """Assert `help=` replaces a flag's default help text."""
    help_text = invoke(cli, ["run", "--help"]).stdout
    assert "Select every archive." in help_text
    assert "Select all items." not in help_text
    assert "Output as JSON." in help_text


def test_dry_run_default_help() -> None:
    """Assert `-n, --dry-run` is listed with its default help text."""
    help_text = invoke(cli, ["run", "--help"]).stdout
    assert "-n, --dry-run" in help_text
    assert "Show what would be done, without doing it." in help_text


def test_format_follows_stdout_by_default(sample: Group) -> None:
    """Assert `ctx.format` is `human` on a terminal, else `plain`."""
    assert invoke(sample, ["rows"], out_tty=True).stdout == (
        "format=human json=False\n"
    )
    assert invoke(sample, ["rows"]).stdout == "format=plain json=False\n"


def test_plain_flag_on_a_terminal(sample: Group) -> None:
    """Assert `--plain` asks for plain output even on a terminal."""
    result = invoke(sample, ["rows", "--plain"], out_tty=True)
    assert result.exit_code == 0
    assert result.stdout == "format=plain json=False\n"


@pytest.mark.parametrize(
    "args",
    [["--json"], ["--plain", "--json"], ["--json", "--plain"]],
    ids=["json", "plain-then-json", "json-then-plain"],
)
def test_json_wins_over_plain(sample: Group, args: list[str]) -> None:
    """Assert `--json` sets the format whatever its position."""
    result = invoke(sample, ["rows", *args], out_tty=True)
    assert result.stdout == "format=json json=True\n"


def test_plain_listed_in_help(sample: Group) -> None:
    """Assert `--plain` is listed with its default help text."""
    help_text = invoke(sample, ["rows", "--help"]).stdout
    assert "  --plain  " in help_text
    assert "Print plain, one record per line." in help_text


def test_forced_colour_keeps_plain_format(run_sample: RunSample) -> None:
    """Assert `FORCE_COLOR` on a pipe leaves the format plain."""
    result = run_sample("rows", env={"FORCE_COLOR": "1"})
    assert result.stdout == "format=plain json=False\n"


def test_plain_overrides_tty_compatible(run_sample: RunSample) -> None:
    """Assert `--plain` wins when `TTY_COMPATIBLE=1` claims a terminal."""
    assert run_sample("rows", env={"TTY_COMPATIBLE": "1"}).stdout == (
        "format=human json=False\n"
    )
    result = run_sample("rows", "--plain", env={"TTY_COMPATIBLE": "1"})
    assert result.stdout == "format=plain json=False\n"
