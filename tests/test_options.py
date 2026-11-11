"""Tests for `pyclig.options` - the standard flags."""

from pathlib import Path

import click
import pytest

import pyclig
from pyclig import Group
from pyclig.testing import assert_conforms, invoke
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


@cli.command()
@pyclig.options.output(help="Where to write.")
@pyclig.options.port(default=8080)
@pyclig.options.user(envvar="FLAGS_USER")
def serve(output: Path | None, port: int, user: str | None) -> None:
    """Print the value options."""
    click.echo(f"output={output} port={port!r} user={user!r}")


def test_value_options_defaults_and_values() -> None:
    """Assert `-o`, `-p` & `-u` take values with the standard long forms."""
    result = invoke(cli, ["serve"])
    assert result.stdout == "output=None port=8080 user=None\n"
    result = invoke(cli, ["serve", "-o", "out.txt", "-p", "1", "-u", "bob"])
    assert result.stdout == "output=out.txt port=1 user='bob'\n"
    args = ["serve", "--output", "-", "--port", "65535", "--user", "ann"]
    assert invoke(cli, args).stdout == "output=- port=65535 user='ann'\n"
    assert invoke(cli, ["serve"], env={"FLAGS_USER": "env"}).stdout.endswith(
        "user='env'\n"
    )


def test_port_range_is_checked() -> None:
    """Assert a port outside 1-65535 is a usage error."""
    result = invoke(cli, ["serve", "--port", "70000"])
    assert result.exit_code == 2
    assert "65535" in result.stderr
    assert invoke(cli, ["serve", "-p", "0"]).exit_code == 2


def test_value_options_help() -> None:
    """Assert the metavars & help texts of the value options."""
    text = invoke(cli, ["serve", "--help"]).stdout
    assert "-o, --output FILE  Where to write." in text
    assert "-p, --port PORT" in text
    assert "-u, --user NAME" in text


def test_kit_is_clean_on_every_factory() -> None:
    """Assert `assert_conforms` is clean on a CLI using every factory."""

    @pyclig.group("kit", examples=["kit every -o out.txt -p 8080"])
    def kit() -> None:
        """Use every standard option factory."""

    @kit.command()
    @pyclig.options.json_output()
    @pyclig.options.plain()
    @pyclig.options.select_all()
    @pyclig.options.force()
    @pyclig.options.dry_run()
    @pyclig.options.output()
    @pyclig.options.port()
    @pyclig.options.user()
    @pyclig.options.secret("token")
    def every(**kwargs: object) -> None:
        """Accept every standard option."""

    assert_conforms(kit)


@pyclig.group("net")
def net_cli() -> None:
    """Fetch things."""


@net_cli.command()
@pyclig.options.timeout(envvar="NET_TIMEOUT")
def fetch(timeout: float) -> None:
    """Print the timeout."""
    click.echo(repr(timeout))


def test_timeout_default_shown_in_help() -> None:
    """Assert `--timeout SECONDS` shows its 30.0 default in help."""
    help_text = invoke(net_cli, ["fetch", "--help"]).stdout
    assert "--timeout SECONDS" in help_text
    assert "30.0" in help_text


def test_timeout_default_and_float_parsing() -> None:
    """Assert the default is 30.0 & a value parses as a float."""
    assert invoke(net_cli, ["fetch"]).stdout == "30.0\n"
    assert invoke(net_cli, ["fetch", "--timeout", "2.5"]).stdout == "2.5\n"
    assert invoke(net_cli, ["fetch", "--timeout", "5"]).stdout == "5.0\n"


@pytest.mark.parametrize("value", ["0", "-1", "-0.5", "abc"])
def test_timeout_rejects_non_positive(value: str) -> None:
    """Assert zero, negative & non-numeric values are usage errors."""
    result = invoke(net_cli, ["fetch", "--timeout", value])
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert result.stdout == ""


def test_timeout_envvar() -> None:
    """Assert `envvar=` supplies the value."""
    result = invoke(net_cli, ["fetch"], env={"NET_TIMEOUT": "7"})
    assert result.stdout == "7.0\n"


def test_timeout_custom_default_and_help() -> None:
    """Assert `default=` & `help=` override the defaults."""

    @pyclig.command("one")
    @pyclig.options.timeout(default=5.0, help="Give up after SECONDS.")
    def one(timeout: float) -> None:
        """Print the timeout."""
        click.echo(repr(timeout))

    assert invoke(one, []).stdout == "5.0\n"
    assert "Give up after SECONDS." in invoke(one, ["--help"]).stdout


@pyclig.command("fetch")
@click.option("--limit", type=pyclig.options.NoneOr(int), envvar="FETCH_LIMIT")
@click.option(
    "--mode",
    type=pyclig.options.NoneOr(click.Choice(["fast", "slow"]), word="off"),
    default="fast",
)
@click.option("--tag", type=pyclig.options.NoneOr())
def none_or(limit: int | None, mode: str | None, tag: str | None) -> None:
    """Print the values."""
    click.echo(f"{limit!r} {mode!r} {tag!r}")


@pytest.mark.parametrize(
    ("args", "line"),
    [
        ([], "None 'fast' None"),
        (["--limit", "5", "--tag", "x"], "5 'fast' 'x'"),
        (["--limit", "none", "--tag", "None"], "None 'fast' None"),
        (["--limit", "NONE", "--mode", "Off"], "None None None"),
        (["--mode", "slow", "--tag", "off"], "None 'slow' 'off'"),
    ],
)
def test_none_or_word_means_none(args: list[str], line: str) -> None:
    """Assert the word, in any case, is None & anything else is converted."""
    result = invoke(none_or, args)
    assert result.exit_code == 0
    assert result.stdout == f"{line}\n"


def test_none_or_rejects_what_the_inner_type_rejects() -> None:
    """Assert a value that is neither the word nor valid is a usage error."""
    result = invoke(none_or, ["--limit", "many"])
    assert result.exit_code == pyclig.ExitCode.USAGE
    assert "'many' is not a valid integer" in result.stderr
    assert invoke(none_or, ["--mode", "none"]).exit_code == 2


def test_none_or_metavar_names_the_word() -> None:
    """Assert help shows `INNER|none`, so the word is discoverable."""
    help_text = invoke(none_or, ["--help"]).stdout
    assert "--limit INTEGER|none" in help_text
    assert "--mode [fast|slow]|off" in help_text
    assert "--tag TEXT|none" in help_text


def test_none_or_from_the_environment_and_config() -> None:
    """Assert an env var or a config value of the word is None too."""
    result = invoke(none_or, [], env={"FETCH_LIMIT": "None"})
    assert result.stdout == "None 'fast' None\n"
    result = invoke(none_or, [], env={"FETCH_LIMIT": "3"})
    assert result.stdout == "3 'fast' None\n"

    @pyclig.command(
        "mapped", context_settings={"default_map": {"limit": 7, "mode": "OFF"}}
    )
    @click.option("--limit", type=pyclig.options.NoneOr(int))
    @click.option("--mode", type=pyclig.options.NoneOr(word="off"))
    def mapped(limit: int | None, mode: str | None) -> None:
        """Print the values a config file supplied."""
        click.echo(f"{limit!r} {mode!r}")

    assert invoke(mapped, []).stdout == "7 None\n"
