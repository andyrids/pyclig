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
def run(json_output: bool, select_all: bool, force: bool) -> None:
    """Print the flag values."""
    click.echo(f"{json_output} {select_all} {force}")


def test_flags_default_off() -> None:
    """Assert the standard flags default to False."""
    assert invoke(cli, ["run"]).stdout == "False False False\n"


def test_flags_short_and_long_names() -> None:
    """Assert `--json`, `-a/--all` & `-f/--force` set their values."""
    assert (
        invoke(cli, ["run", "--json", "-a", "-f"]).stdout == "True True True\n"
    )
    assert (
        invoke(cli, ["run", "--all", "--force"]).stdout == "False True True\n"
    )


def test_flag_help_override() -> None:
    """Assert `help=` replaces a flag's default help text."""
    help_text = invoke(cli, ["run", "--help"]).stdout
    assert "Select every archive." in help_text
    assert "Select all items." not in help_text
    assert "Output as JSON." in help_text
