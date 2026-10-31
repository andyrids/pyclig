"""Tests for `pyclig.options` - the standard flags."""

import click

import pyclig
from pyclig.testing import invoke


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
