"""Tests for `pyclig._conformance` - the CLIG conformance kit."""

import click
import pytest

import pyclig
from pyclig import Group
from pyclig.testing import Finding, assert_conforms, check

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


@pytest.fixture(autouse=True)
def _no_callbacks() -> None:
    """Reset the callback record before every test."""
    calls.clear()


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
        ("ARG-6", "adv cp"),
        ("ARG-16", "adv cp"),
        ("ENV-15", "adv cp"),
        ("HELP-3", "adv download"),
        ("SUB-3", "adv plain"),
    }


def test_own_help_spelling_is_not_probed() -> None:
    """Assert a command taking `-h` gets ARG-6 only, not a false HELP-1."""
    found = {(f.rule, f.command) for f in check(hosted)}
    assert found == {("ARG-6", "hosted serve")}
    assert calls == []


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
    assert lines[0] == "6 CLIG findings:"
    assert "ARG-2    adv cp            `-x` has no long form" in lines
    assert not any("HELP-9" in line for line in lines)


def test_sample_findings(sample: Group) -> None:
    """Assert the sample CLI's known deviations are reported."""
    found = {(f.rule, f.command) for f in check(sample)}
    assert ("ARG-6", "sample copy") in found
    assert ("ARG-16", "sample login") in found
    assert ("HELP-3", "sample download") in found
