"""Tests for `pyclig._conformance` - the CLIG conformance kit."""

import inspect
import re
from pathlib import Path

import click
import pytest

import pyclig
from pyclig import Group, _conformance
from pyclig.testing import Finding, assert_conforms, check

COVERAGE = Path(__file__).parents[1] / "docs" / "clig-coverage.md"

calls: list[str] = []
"""Every callback the fixture CLIs run - the kit must leave it empty."""


@pyclig.group("clean", examples=["clean ship --tag v1"])
def clean() -> None:
    """Group commands with nothing to report."""
    calls.append("clean")


@clean.command()
@click.option("--tag", help="The tag to ship.")
@click.option("-f", "--force", is_flag=True, help="Ship over an existing tag.")
def ship(tag: str | None, force: bool) -> None:
    """Ship a tag."""
    calls.append("ship")


@clean.command()
@click.argument("src")
@click.argument("dst")
@click.argument("extra", nargs=-1)
@click.option("--tag", help="The tag to copy under.")
@click.option("-o", "--output", help="Where to report.")
@click.option("--editor", envvar="EDITOR", help="The editor, as $EDITOR.")
@click.option("--proxy", envvar="CLEAN_PROXY_URL", help="The proxy to use.")
def copy(**kwargs: object) -> None:
    """Copy, within every static rule."""
    calls.append("copy")


@pyclig.group("adv")
@click.option("--site", required=True, help="The site to act on.")
def adv() -> None:
    """Group commands breaking one rule each."""
    calls.append("adv")


def _eager(ctx: click.Context, param: click.Parameter, value: bool) -> bool:
    """Record that an eager callback ran."""
    calls.append("eager")
    return value


def _default() -> str:
    """Record that a callable default was evaluated."""
    calls.append("default")
    return "x"


@adv.command()
@click.argument("src")
@click.argument("dst")
@click.option("-x", is_flag=True, help="A flag with no long form.")
@click.option("--file", "-f", help="A short flag with a non-standard meaning.")
@click.option("--api-token", help="A secret on the command line.")
@click.option(
    "--user", envvar="SERVICE_PASSWORD", help="A secret from the environment."
)
@click.option("--quiet-mode", default=_default, help="Has a callable default.")
@click.option(
    "--eager", is_flag=True, is_eager=True, callback=_eager, help="Eager."
)
def cp(**kwargs: object) -> None:
    """Copy, breaking the flag rules."""
    calls.append("cp")


@adv.command()
@click.option("--data-dir")
def download(data_dir: str | None) -> None:
    """Download, with an undescribed flag."""
    calls.append("download")


@click.command()
def plain() -> None:
    """Run a plain click command added to the group."""
    calls.append("plain")


adv.add_command(plain)


@pyclig.group("aided", context_settings={"help_option_names": ["--aide"]})
def aided() -> None:
    """Group commands under custom help flags."""
    calls.append("aided")


@aided.command()
def sub() -> None:
    """Do nothing."""
    calls.append("sub")


@pyclig.group("hosted", examples=["hosted serve"])
def hosted() -> None:
    """Group a command whose own `-h` means host."""
    calls.append("hosted")


@hosted.command()
@click.option("-h", "--host", help="The host to serve on.")
def serve(host: str | None) -> None:
    """Serve on `--host`."""
    calls.append("serve")


@pyclig.group("vault", examples=["vault open"])
def vault() -> None:
    """Group a command mixing secret-looking & innocent names."""
    calls.append("vault")


@vault.command("open")
@click.option("--password-file", type=click.Path(), help="The remedy itself.")
@click.option("--token-limit", type=int, help="A limit, not a token.")
@click.option("--show-secrets", is_flag=True, help="A flag takes no value.")
@click.option(
    "--token-path", envvar="MY_TOKEN_FILE", help="A path, not a token."
)
@click.option("--password", help="A secret.")
@click.option("--api-key", help="A secret.")
@click.option("--client-secret", help="A secret.")
@click.option("--credentials", help="A secret.")
@click.option("--github", envvar="GITHUB_TOKEN", help="A secret from env.")
def open_(**kwargs: object) -> None:
    """Open the vault."""
    calls.append("open")


@pyclig.group("lax", examples=["lax scale 3"])
def lax() -> None:
    """Group commands breaking one static flag rule each."""
    calls.append("lax")


@lax.command()
@click.argument("count", type=int)
def scale(count: int) -> None:
    """Scale, taking a setting as an argument."""
    calls.append("scale")


@lax.command()
@click.argument("name")
@click.argument("target", type=click.Path())
def tag(name: str, target: str) -> None:
    """Tag, taking two different things as arguments."""
    calls.append("tag")


@lax.command()
@click.option("-j", "--jobs", type=int, help="A one-letter flag of its own.")
@click.option("--all", "select_all", is_flag=True, help="A flag here.")
def build(jobs: int | None, select_all: bool) -> None:
    """Build, with a non-standard short flag."""
    calls.append("build")


@lax.command()
@click.option("-F", "--force", is_flag=True, help="A standard name.")
@click.option("--all", "select_all", help="A value here.")
def push(force: bool, select_all: str | None) -> None:
    """Push, with `--all` meaning something else."""
    calls.append("push")


@lax.command()
@click.option("--region", envvar="lax-region", help="A name no shell exports.")
@click.option("--workdir", envvar="HOME", help="A variable with a meaning.")
@click.option("--via", envvar="HTTPS_PROXY", help="Another one.")
def env(**kwargs: object) -> None:
    """Read badly named environment variables."""
    calls.append("env")


@pyclig.group("named", examples=["named status"])
def named() -> None:
    """Group commands whose names break the naming rules."""
    calls.append("named")


def _named(ctx: click.Context) -> None:
    """Record that a `named` command ran."""
    calls.append(ctx.info_name or "")


for _name in (
    "add_item",
    "list-items",
    "Push",
    "update",
    "upgrade",
    "remove",
    "delete",
    "status",
    "stats",
    "ls",
    "ps",
):
    named.command(_name, help=f"Run {_name}.")(click.pass_context(_named))
named.add_command(named.commands["remove"], "rm")


@pytest.fixture(autouse=True)
def _no_callbacks() -> None:
    """Reset the callback record before every test."""
    calls.clear()


def test_kit_rule_ids_are_coverage_table_rows() -> None:
    """Assert every rule ID the kit can emit is a row of the coverage table."""
    if not COVERAGE.is_file():
        pytest.skip("docs/clig-coverage.md is not part of this install")
    text = COVERAGE.read_text(encoding="utf-8")
    rows = set(re.findall(r"^\| ([A-Z]+-\d+[a-z]?) \|", text, re.MULTILINE))
    source = inspect.getsource(_conformance)
    emitted = set(re.findall(r'Finding\("([A-Z]+-\d+[a-z]?)"', source))
    assert emitted
    assert emitted <= rows, sorted(emitted - rows)


def test_clean_cli_has_no_findings() -> None:
    """Assert a conforming CLI passes `assert_conforms`."""
    assert_conforms(clean)
    assert check(clean) == []


def test_findings_by_rule_and_command() -> None:
    """Assert each broken rule is reported once, by its coverage ID."""
    found = {(f.rule, f.command) for f in check(adv)}
    assert found == {
        ("HELP-9", "adv"),
        ("ARG-2", "adv cp"),
        ("ARG-3", "adv cp"),
        ("ARG-6", "adv cp"),
        ("ARG-16", "adv cp"),
        ("ENV-15", "adv cp"),
        ("HELP-3", "adv download"),
        ("SUB-3", "adv plain"),
    }


def test_flag_rules_by_rule_and_command() -> None:
    """Assert each static flag rule is reported by its coverage ID."""
    found = {(f.rule, f.command) for f in check(lax)}
    assert found == {
        ("ARG-1", "lax scale"),
        ("ARG-5", "lax tag"),
        ("ARG-3", "lax build"),
        ("ARG-3", "lax push"),
        ("ARG-6", "lax push"),
        ("SUB-3", "lax push"),
        ("ENV-2", "lax env"),
        ("ENV-4", "lax env"),
    }
    assert calls == []


def test_flag_rule_messages_name_the_parameter() -> None:
    """Assert each static flag finding names what deviates, once each."""
    messages = [f.message for f in check(lax)]
    assert messages == [
        "`COUNT` is a setting (integer) - use a flag",
        "arguments of differing types: `NAME` (text), `TARGET` (path)",
        "`-j` is not a standard one-letter flag",
        "`-F` is not a standard one-letter flag",
        "`--force` is conventionally `-f`, here `-F`",
        "`--all` takes a value here, is a flag on `lax build`",
        "`--region` reads `lax-region` - name it `[A-Z_][A-Z0-9_]*`",
        "`--workdir` reads `HOME`, which already has a meaning",
        "`--via` reads `HTTPS_PROXY`, which already has a meaning",
    ]


def test_same_flag_with_another_short_is_found() -> None:
    """Assert one long name with two shorts is a SUB-3 finding."""

    @pyclig.group("twice", examples=["twice a"])
    def twice() -> None:
        """Group two commands spelling `--all` differently."""

    @twice.command()
    @click.option("-a", "--all", "select_all", is_flag=True, help="All.")
    def a(select_all: bool) -> None:
        """Take `-a`."""

    @twice.command()
    @click.option("-u", "--all", "select_all", is_flag=True, help="All.")
    @click.option("--user", help="No short at all, so no finding.")
    def b(select_all: bool, user: str | None) -> None:
        """Take `-u`."""

    found = [(f.rule, f.message) for f in check(twice) if f.command != "twice"]
    assert found == [
        ("ARG-6", "`-u` is conventionally `--user`, here `--all`"),
        ("SUB-3", "`--all` has `-u` here, `-a` on `twice a`"),
    ]


def test_naming_rules_by_rule_and_command() -> None:
    """Assert mixed, upper-case & confusable subcommand names are found."""
    found = [(f.rule, f.command, f.message) for f in check(named)]
    assert found == [
        (
            "SUB-4",
            "named",
            "subcommands mix `-` & `_`: `list-items`, `add_item`",
        ),
        ("SUB-4", "named", "`Push` is not lower-case"),
        ("SUB-5", "named", "`update` & `upgrade` are easily confused"),
        ("SUB-5", "named", "`remove` & `delete` are easily confused"),
        ("SUB-5", "named", "`status` & `stats` are easily confused"),
    ]
    assert calls == []


def test_own_help_spelling_is_not_probed() -> None:
    """Assert a command taking `-h` gets ARG-6 only, not a false HELP-1."""
    found = {(f.rule, f.command) for f in check(hosted)}
    assert found == {("ARG-6", "hosted serve")}
    assert calls == []


def test_secret_findings_only_for_secret_values() -> None:
    """Assert only value-taking names ending in a secret word are flagged."""
    flags = sorted(
        f.message.split("`")[1] for f in check(vault) if f.rule == "ARG-16"
    )
    assert flags == [
        "--api-key",
        "--client-secret",
        "--credentials",
        "--password",
    ]
    envs = [
        f.message.split("`")[3] for f in check(vault) if f.rule == "ENV-15"
    ]
    assert envs == ["GITHUB_TOKEN"]


def test_finding_messages_name_the_flag() -> None:
    """Assert a finding names the offending flag & the convention."""
    messages = {f.rule: f.message for f in check(adv) if f.command == "adv cp"}
    assert messages["ARG-2"] == "`-x` has no long form"
    assert (
        messages["ARG-6"] == "`-f` is conventionally `--force`, here `--file`"
    )
    assert messages["ARG-16"].startswith("`--api-token` takes a secret")
    assert messages["ENV-15"].startswith(
        "`--user` reads a secret from `SERVICE_PASSWORD`"
    )


def test_probes_never_run_a_callback() -> None:
    """Assert no group, command, eager or default callback runs."""
    check(adv)
    check(clean)
    check(aided)
    check(lax)
    assert calls == []


def test_probes_use_the_root_help_names() -> None:
    """Assert subcommands are probed with the root's custom help flags."""
    assert check(aided) == [
        Finding("HELP-9", "aided", "no examples= on the root command")
    ]


def test_probe_findings_for_a_misbehaving_command() -> None:
    """Assert help off STDOUT & a wrong exit code for a bad flag are found."""

    @pyclig.group("odd", examples=["odd"])
    def odd() -> None:
        """Group a command that prints help to STDERR."""

    @odd.command(cls=_Odd)
    def sub() -> None:
        """Misbehave."""

    found = {(f.rule, f.command) for f in check(odd)}
    assert found == {("HELP-1", "odd sub"), ("BAS-2", "odd sub")}


class _Odd(pyclig.Command):
    """A command that prints help to STDERR & exits 1 on an unknown flag."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Misbehave on purpose.

        Args:
            ctx: The command's context.
            args: The arguments.

        Returns:
            Nothing - it always exits.
        """
        if set(args) & set(ctx.help_option_names):
            click.echo(ctx.get_help(), err=True)
            ctx.exit(0)
        ctx.exit(1)


def test_ignore_requires_a_reason() -> None:
    """Assert `ignore` rejects an empty reason."""
    with pytest.raises(ValueError, match="ARG-16"):
        check(adv, ignore={"ARG-16": " "})


def test_ignore_drops_the_rule() -> None:
    """Assert an ignored rule is left out of the findings."""
    rules = {f.rule for f in check(adv, ignore={"ARG-16": "it prompts too"})}
    assert "ARG-16" not in rules
    assert "ARG-2" in rules


def test_assert_conforms_lists_findings() -> None:
    """Assert the assertion message lists every finding, one per line."""
    with pytest.raises(AssertionError) as info:
        assert_conforms(adv, ignore={"HELP-9": "sample"})
    lines = str(info.value).splitlines()
    assert lines[0] == "7 CLIG findings:"
    assert "ARG-2    adv cp            `-x` has no long form" in lines
    assert not any("HELP-9" in line for line in lines)


def test_sample_findings(sample: Group) -> None:
    """Assert the sample CLI's known deviations are reported."""
    found = {(f.rule, f.command) for f in check(sample)}
    assert ("ARG-6", "sample copy") in found
    assert ("ARG-16", "sample login") in found
    assert ("HELP-3", "sample download") in found


def test_run_variables_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert a developer's `<PROG>_` variables add no findings & no file."""
    monkeypatch.setenv("TESTS_LOG_FILE", str(tmp_path))
    monkeypatch.setenv("TESTS_DEBUG", "1")
    log = tmp_path / "debug.log"
    assert check(clean) == []
    monkeypatch.setenv("TESTS_LOG_FILE", str(log))
    assert check(clean) == []
    assert not log.exists()
