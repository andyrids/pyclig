"""Tests for `pyclig.options` - the standard flags."""

from pathlib import Path

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


@pyclig.group("vault")
def vault() -> None:
    """Read secrets from files or STDIN."""


@vault.command()
@pyclig.options.secret("token")
@pyclig.options.secret("api-key", required=True, help="The API key file.")
def login(token: str | None, api_key: str) -> None:
    """Print the secrets read."""
    click.echo(f"token={token!r} api_key={api_key!r}")


def test_secret_from_file_strips_one_line_ending(tmp_path: Path) -> None:
    """Assert a secret file's text loses one trailing newline, CRLF or LF."""
    key = tmp_path / "key"
    key.write_bytes(b"s3cret\r\n")
    result = invoke(vault, ["login", "--api-key-file", str(key)])
    assert result.stdout == "token=None api_key='s3cret'\n"
    key.write_bytes(b"two\n\n")
    token = tmp_path / "token"
    token.write_text("t\n")
    args = ["login", "--api-key-file", str(key), "--token-file", str(token)]
    expected = f"token='t' api_key={'two' + chr(10)!r}"
    assert invoke(vault, args).stdout.splitlines() == [expected]


def test_secret_from_stdin(tmp_path: Path) -> None:
    """Assert `-` reads a piped STDIN, with the same newline rule."""
    result = invoke(vault, ["login", "--api-key-file", "-"], input="s3cret\n")
    assert result.stdout == "token=None api_key='s3cret'\n"


def test_secret_refuses_a_terminal_stdin() -> None:
    """Assert `-` on a terminal is a usage error, never a blocking read."""
    result = invoke(vault, ["login", "--api-key-file", "-"], in_tty=True)
    assert result.exit_code == 2
    assert "pipe" in result.stderr
    assert "Try 'vault login --help'" in result.stderr


def test_secret_usage_errors(tmp_path: Path) -> None:
    """Assert missing, empty, absent & directory inputs exit 2."""
    result = invoke(vault, ["login"])
    assert result.exit_code == 2
    assert "Missing option '--api-key-file'" in result.stderr
    empty = tmp_path / "empty"
    empty.write_text("\n")
    result = invoke(vault, ["login", "--api-key-file", str(empty)])
    assert result.exit_code == 2
    assert "empty" in result.stderr
    result = invoke(vault, ["login", "--api-key-file", str(tmp_path / "no")])
    assert result.exit_code == 2
    assert "does not exist" in result.stderr
    result = invoke(vault, ["login", "--api-key-file", str(tmp_path)])
    assert result.exit_code == 2
    assert "is a directory" in result.stderr


def test_secret_help() -> None:
    """Assert the option is `--<name>-file FILE` with a default help text."""
    text = invoke(vault, ["login", "--help"]).stdout
    assert "--api-key-file FILE  The API key file." in text
    assert "--token-file FILE" in text
    assert "Read the token from FILE, or from STDIN with `-`." in text
