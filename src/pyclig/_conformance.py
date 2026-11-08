"""Check a CLI against the CLI guidelines, reporting by rule ID.

The IDs are the rows of `docs/clig-coverage.md`. The kit never runs a
command body: parameters are read from the command objects, and each
command is probed as its own root with a help flag or an unknown flag,
which click answers before any callback runs. Rules needing a run with
real input are out of its reach.

| Rule    | Finding                                                     |
| ------- | ----------------------------------------------------------- |
| HELP-9  | No `examples=` on the root command                          |
| HELP-3  | A flag without help text                                    |
| ARG-2   | A flag with no long form                                    |
| ARG-6   | A standard short flag with a non-standard long form         |
| ARG-16  | A value-taking option whose name ends in a secret word      |
| ENV-15  | An option reading an env var whose name ends in a secret    |
| SUB-3   | A plain click command, outside the run flags & help layout  |
| HELP-1  | A help flag not answered on STDOUT with exit 0              |
| BAS-2   | An unknown flag not answered with exit 2                    |
| BAS-5   | An unknown flag answered on STDOUT                          |

License:
    SPDX-License-Identifier: Apache-2.0
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

import click
from click.testing import CliRunner

from pyclig import _config, _run
from pyclig._core import Command
from pyclig._exit import ExitCode

STANDARD_SHORT: dict[str, tuple[str, ...]] = {
    "-a": ("--all",),
    "-d": ("--debug",),
    "-f": ("--force",),
    "-h": ("--help",),
    "-n": ("--dry-run",),
    "-o": ("--output",),
    "-p": ("--port",),
    "-q": ("--quiet",),
    "-u": ("--user",),
    "-v": ("--version", "--verbose"),
}
"""The standard short flags & the long forms the guidelines give them."""

_SECRET = _config._SECRET
"""A name ending in a secret word - shared with `.env`, which skips them."""
_UNKNOWN_FLAG = "--pyclig-no-such-flag"
_CLEARED = ("COLUMNS", "FORCE_COLOR", "NO_COLOR", "TTY_COMPATIBLE")


@dataclass(frozen=True)
class Finding:
    """One deviation from the guidelines.

    Attributes:
        rule: The coverage table ID, e.g. `ARG-2`.
        command: The command path, e.g. `dkais download`.
        message: What deviates, naming the flag or probe.
    """

    rule: str
    command: str
    message: str

    def __str__(self) -> str:
        """Return one aligned line: rule, command & message."""
        return f"{self.rule:<8} {self.command:<17} {self.message}"


def check(
    cli: click.Command, *, ignore: Mapping[str, str] | None = None
) -> list[Finding]:
    """Return the findings for `cli` & every command below it.

    Args:
        cli: The CLI, usually a `pyclig.Group`.
        ignore: Rule IDs to leave out, each with the reason.

    Returns:
        The findings, in command order.

    Raises:
        ValueError: When an ignored rule has no reason.
    """
    ignored = ignore or {}
    for rule, reason in ignored.items():
        if not reason.strip():
            raise ValueError(f"ignore[{rule!r}] needs a reason")
    settings = cli.context_settings.get("help_option_names")
    help_names = list(settings) if settings else ["-h", "--help"]
    findings: list[Finding] = []
    if not getattr(cli, "examples", ()):
        findings.append(Finding("HELP-9", cli.name or "", _NO_EXAMPLES))
    for path, command in _walk(cli, cli.name or ""):
        if not isinstance(command, Command):
            findings.append(Finding("SUB-3", path, _PLAIN_CLICK))
            continue
        findings += _check_params(path, command)
        findings += _probe(path, command, help_names)
    return [f for f in findings if f.rule not in ignored]


def assert_conforms(
    cli: click.Command, *, ignore: Mapping[str, str] | None = None
) -> None:
    """Assert `cli` has no findings, listing them otherwise.

    Args:
        cli: The CLI, usually a `pyclig.Group`.
        ignore: Rule IDs to leave out, each with the reason.

    Raises:
        AssertionError: Listing every finding, one per line.
    """
    findings = check(cli, ignore=ignore)
    if findings:
        lines = [f"{len(findings)} CLIG findings:", *map(str, findings)]
        raise AssertionError("\n".join(lines))


_NO_EXAMPLES = "no examples= on the root command"
_PLAIN_CLICK = "plain click command: no run flags, help layout or concise help"


def _walk(
    command: click.Command, path: str
) -> Iterator[tuple[str, click.Command]]:
    """Yield `command` & every command below it with its command path."""
    yield path, command
    if isinstance(command, click.Group):
        for name, sub in command.commands.items():
            yield from _walk(sub, f"{path} {name}")


def _check_params(path: str, command: click.Command) -> list[Finding]:
    """Return the findings for the command's own options."""
    findings: list[Finding] = []
    for param in command.params:
        if not isinstance(param, click.Option) or param.hidden:
            continue
        shorts = [o for o in param.opts if not o.startswith("--")]
        longs = [o for o in param.opts if o.startswith("--")]
        name = longs[0] if longs else shorts[0]
        if not longs:
            findings.append(
                Finding("ARG-2", path, f"`{name}` has no long form")
            )
        if not param.help:
            findings.append(
                Finding("HELP-3", path, f"`{name}` has no help text")
            )
        for short in shorts:
            expected = STANDARD_SHORT.get(short)
            if expected and longs and not set(longs) & set(expected):
                message = (
                    f"`{short}` is conventionally `{expected[0]}`, "
                    f"here `{longs[0]}`"
                )
                findings.append(Finding("ARG-6", path, message))
        if param.is_flag:
            continue
        if any(_SECRET.search(o) for o in longs):
            message = (
                f"`{name}` takes a secret on the command line - "
                "read it from a file or STDIN"
            )
            findings.append(Finding("ARG-16", path, message))
        envvars = (
            [param.envvar]
            if isinstance(param.envvar, str)
            else list(param.envvar or ())
        )
        for envvar in filter(_SECRET.search, envvars):
            message = (
                f"`{name}` reads a secret from `{envvar}` - "
                "use a file, pipe or secret store"
            )
            findings.append(Finding("ENV-15", path, message))
    return findings


def _probe(
    path: str, command: Command, help_names: list[str]
) -> list[Finding]:
    """Return the findings from running `command` as its own root.

    NOTE: Only a help flag or an unknown flag is passed, so click exits
    while parsing & no callback runs - the group's included, because the
    command is not reached through it.
    """
    findings: list[Finding] = []
    runner = CliRunner()
    # The developer's `<PROG>_LOG_FILE` or `_DEBUG` would change the output
    env: dict[str, str | None] = dict.fromkeys(_CLEARED)
    env.update(_run.cleared(command.callback, path))
    taken = {o for p in command.params for o in (*p.opts, *p.secondary_opts)}
    for flag in (name for name in help_names if name not in taken):
        result = runner.invoke(
            command,
            [flag],
            env=env,
            prog_name=path,
            help_option_names=help_names,
        )
        if result.exit_code != 0 or result.stderr or not result.stdout:
            message = f"`{flag}` exits {result.exit_code}"
            if result.stderr:
                message += ", printing to STDERR"
            findings.append(Finding("HELP-1", path, message))
    result = runner.invoke(
        command,
        [_UNKNOWN_FLAG],
        env=env,
        prog_name=path,
        help_option_names=help_names,
    )
    if result.exit_code != ExitCode.USAGE:
        usage = int(ExitCode.USAGE)
        message = f"an unknown flag exits {result.exit_code}, not {usage}"
        findings.append(Finding("BAS-2", path, message))
    if result.stdout:
        findings.append(
            Finding("BAS-5", path, "an unknown flag prints to STDOUT")
        )
    return findings
