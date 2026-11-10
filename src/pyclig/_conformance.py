"""Check a CLI against the CLI guidelines, reporting by rule ID.

The IDs are the rows of `docs/clig-coverage.md`. The kit never runs a
command body unless given samples: parameters are read from the command
objects, and each command is probed as its own root with a help flag or
an unknown flag, which click answers before any callback runs. Rules
needing a run with real input are checked on `samples=`, the command
lines the caller knows to be safe & expected to succeed.

| Rule    | Finding                                                     |
| ------- | ----------------------------------------------------------- |
| HELP-9  | No `examples=` on the root command                          |
| HELP-3  | A flag without help text                                    |
| ARG-1   | An argument typed as a setting: a number, choice or boolean |
| ARG-2   | A flag with no long form                                    |
| ARG-3   | A one-letter flag outside the standard ones                 |
| ARG-5   | Two or more arguments of differing types                    |
| ARG-6   | A standard short or long flag paired with another name      |
| ARG-16  | A value-taking option whose name ends in a secret word      |
| ENV-2   | An env var name a shell cannot export                       |
| ENV-4   | An env var that already has a meaning, e.g. `HOME`          |
| ENV-15  | An option reading an env var whose name ends in a secret    |
| SUB-3   | A plain click command, or one flag declared two ways        |
| SUB-4   | Sibling names mixing `-` & `_`, or not lower-case           |
| SUB-5   | Sibling names easily confused, e.g. `update` & `upgrade`    |
| HELP-1  | A help flag not answered on STDOUT with exit 0              |
| BAS-2   | An unknown flag not answered with exit 2                    |
| BAS-5   | An unknown flag answered on STDOUT                          |
| BAS-4   | A sample exiting non-zero, or `--json` printing no JSON     |
| BAS-5   | A sample printing an `error:` or `warning:` line to STDOUT  |
| ERR-2   | A sample printing a traceback to STDERR                     |

License:
    SPDX-License-Identifier: Apache-2.0
"""

import json
import re
import shlex
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass

import click
from click.testing import CliRunner

from pyclig import _config, _run
from pyclig._core import Command
from pyclig._exit import ExitCode
from pyclig._flags import GlobalOption

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

COMMON_ENV = frozenset(
    "HOME PATH USER SHELL TERM TMPDIR LANG TZ EDITOR VISUAL PAGER COLUMNS "
    "LINES DEBUG NO_COLOR FORCE_COLOR".split()
)
"""Variables with a meaning already, as is any name ending in `_PROXY`."""

_STANDARD_LONG = {
    long: short for short, longs in STANDARD_SHORT.items() for long in longs
}
_SETTING = (
    click.Choice,
    click.types.BoolParamType,
    click.types.IntParamType,
    click.types.FloatParamType,
)
"""Argument types that hold a setting; the ranges subclass the numbers."""
_PORTABLE = re.compile(r"[A-Z_][A-Z0-9_]*")
_CONFUSABLE = ({"update", "upgrade"}, {"remove", "delete"})
_NEAR_LENGTH = 4
"""The shortest names one edit apart that are reported: `ls` & `ps` are not."""

_SECRET = _config._SECRET
"""A name ending in a secret word - shared with `.env`, which skips them."""
_UNKNOWN_FLAG = "--pyclig-no-such-flag"
_CLEARED = ("COLUMNS", "FORCE_COLOR", "NO_COLOR", "TTY_COMPATIBLE")
_MESSAGE = ("error:", "warning:")
_TRACEBACK = "Traceback (most recent call last)"


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
    cli: click.Command,
    *,
    ignore: Mapping[str, str] | None = None,
    samples: Iterable[Sequence[str]] = (),
) -> list[Finding]:
    """Return the findings for `cli` & every command below it.

    Args:
        cli: The CLI, usually a `pyclig.Group`.
        ignore: Rule IDs to leave out, each with the reason.
        samples: Command lines to run for real, without the program name,
            e.g. `[["list", "--json"]]` - each is expected to exit 0.

    Returns:
        The findings, in command order, then in sample order.

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
    seen: dict[str, tuple[str, click.Option]] = {}
    if not getattr(cli, "examples", ()):
        findings.append(Finding("HELP-9", cli.name or "", _NO_EXAMPLES))
    for path, command in _walk(cli, cli.name or ""):
        if isinstance(command, click.Group):
            findings += _check_names(path, command)
        if not isinstance(command, Command):
            findings.append(Finding("SUB-3", path, _PLAIN_CLICK))
            continue
        findings += _check_arguments(path, command)
        findings += _check_params(path, command)
        findings += _check_consistency(path, command, seen)
        findings += _probe(path, command, help_names)
    for sample in samples:
        findings += _run_sample(cli, list(sample))
    return [f for f in findings if f.rule not in ignored]


def assert_conforms(
    cli: click.Command,
    *,
    ignore: Mapping[str, str] | None = None,
    samples: Iterable[Sequence[str]] = (),
) -> None:
    """Assert `cli` has no findings, listing them otherwise.

    Args:
        cli: The CLI, usually a `pyclig.Group`.
        ignore: Rule IDs to leave out, each with the reason.
        samples: Command lines to run for real, without the program name.

    Raises:
        AssertionError: Listing every finding, one per line.
    """
    findings = check(cli, ignore=ignore, samples=samples)
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


def _one_edit(a: str, b: str) -> bool:
    """Return whether one insertion, deletion or substitution makes `a` `b`."""
    if len(a) > len(b):
        a, b = b, a
    if a == b or len(b) - len(a) > 1:
        return False
    at = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), len(a))
    return a[at + (len(a) == len(b)) :] == b[at + 1 :]


def _check_names(path: str, group: click.Group) -> list[Finding]:
    """Return the findings for the names of the group's subcommands.

    NOTE: Two names for one command object are aliases, never confusable.
    """
    findings: list[Finding] = []
    names = list(group.commands)
    hyphen = next((n for n in names if "-" in n), "")
    underscore = next((n for n in names if "_" in n), "")
    if hyphen and underscore:
        message = f"subcommands mix `-` & `_`: `{hyphen}`, `{underscore}`"
        findings.append(Finding("SUB-4", path, message))
    for name in names:
        if name != name.lower():
            message = f"`{name}` is not lower-case"
            findings.append(Finding("SUB-4", path, message))
    for at, a in enumerate(names):
        for b in names[at + 1 :]:
            if group.commands[a] is group.commands[b]:
                continue
            near = min(len(a), len(b)) >= _NEAR_LENGTH and _one_edit(a, b)
            if near or {a, b} in _CONFUSABLE:
                message = f"`{a}` & `{b}` are easily confused"
                findings.append(Finding("SUB-5", path, message))
    return findings


def _envvars(param: click.Parameter) -> list[str]:
    """Return the environment variables `param` reads."""
    if isinstance(param.envvar, str):
        return [param.envvar]
    return list(param.envvar or ())


def _check_arguments(path: str, command: click.Command) -> list[Finding]:
    """Return the findings for the command's positional arguments."""
    findings: list[Finding] = []
    arguments = [p for p in command.params if isinstance(p, click.Argument)]
    for param in arguments:
        name = param.human_readable_name
        if isinstance(param.type, _SETTING):
            message = f"`{name}` is a setting ({param.type.name}) - use a flag"
            findings.append(Finding("ARG-1", path, message))
        findings += _check_envvars(path, name, param, ())
    if len({p.type.name for p in arguments}) > 1:
        listed = ", ".join(
            f"`{p.human_readable_name}` ({p.type.name})" for p in arguments
        )
        message = f"arguments of differing types: {listed}"
        findings.append(Finding("ARG-5", path, message))
    return findings


def _check_envvars(
    path: str, name: str, param: click.Parameter, own: tuple[str, ...]
) -> list[Finding]:
    """Return the findings for the names of the variables `param` reads.

    Args:
        path: The command path.
        name: The parameter, as the finding names it.
        param: The parameter.
        own: The variable names the parameter's long forms spell, which
            may be common: `--editor` reading `EDITOR` is the convention.

    Returns:
        The ENV-2 & ENV-4 findings.
    """
    findings: list[Finding] = []
    for envvar in _envvars(param):
        if not _PORTABLE.fullmatch(envvar):
            message = f"`{name}` reads `{envvar}` - name it `[A-Z_][A-Z0-9_]*`"
            findings.append(Finding("ENV-2", path, message))
        common = envvar in COMMON_ENV or envvar.endswith("_PROXY")
        if common and envvar not in own:
            message = f"`{name}` reads `{envvar}`, which already has a meaning"
            findings.append(Finding("ENV-4", path, message))
    return findings


def _check_consistency(
    path: str,
    command: click.Command,
    seen: dict[str, tuple[str, click.Option]],
) -> list[Finding]:
    """Return the findings for flags an earlier command declared otherwise.

    Args:
        path: The command path.
        command: The command.
        seen: Each long name's first command path & option, added to here.

    Returns:
        The SUB-3 findings.
    """
    findings: list[Finding] = []
    for param in command.params:
        if not isinstance(param, click.Option) or param.hidden:
            continue
        if isinstance(param, GlobalOption):
            continue
        shorts = sorted(o for o in param.opts if not o.startswith("--"))
        for long in (o for o in param.opts if o.startswith("--")):
            first, other = seen.setdefault(long, (path, param))
            theirs = sorted(o for o in other.opts if not o.startswith("--"))
            if param.is_flag != other.is_flag:
                kinds = ("is a flag", "takes a value")
                here, there = kinds if param.is_flag else kinds[::-1]
                message = f"`{long}` {here} here, {there} on `{first}`"
                findings.append(Finding("SUB-3", path, message))
            elif shorts and theirs and shorts != theirs:
                message = (
                    f"`{long}` has `{'`, `'.join(shorts)}` here, "
                    f"`{'`, `'.join(theirs)}` on `{first}`"
                )
                findings.append(Finding("SUB-3", path, message))
    return findings


def _check_standard(
    path: str, shorts: list[str], longs: list[str]
) -> list[Finding]:
    """Return the findings for an option's names against the standard ones."""
    findings: list[Finding] = []
    for short in shorts:
        expected = STANDARD_SHORT.get(short)
        if expected and longs and not set(longs) & set(expected):
            message = (
                f"`{short}` is conventionally `{expected[0]}`, "
                f"here `{longs[0]}`"
            )
            findings.append(Finding("ARG-6", path, message))
        if not expected:
            message = f"`{short}` is not a standard one-letter flag"
            findings.append(Finding("ARG-3", path, message))
    for long in longs:
        short = _STANDARD_LONG.get(long, "")
        # A standard short on another name is reported above
        if short and shorts and not STANDARD_SHORT.keys() & set(shorts):
            message = (
                f"`{long}` is conventionally `{short}`, here `{shorts[0]}`"
            )
            findings.append(Finding("ARG-6", path, message))
    return findings


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
        findings += _check_standard(path, shorts, longs)
        own = tuple(o[2:].upper().replace("-", "_") for o in longs)
        findings += _check_envvars(path, name, param, own)
        if param.is_flag:
            continue
        if any(_SECRET.search(o) for o in longs):
            message = (
                f"`{name}` takes a secret on the command line - "
                "read it from a file or STDIN"
            )
            findings.append(Finding("ARG-16", path, message))
        for envvar in filter(_SECRET.search, _envvars(param)):
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


def _run_sample(cli: click.Command, sample: list[str]) -> list[Finding]:
    """Return the findings from running `cli` with the sample's arguments."""
    root = cli.name or ""
    command = shlex.join([root, *sample])
    env: dict[str, str | None] = dict.fromkeys(_CLEARED)
    env.update(_run.cleared(cli.callback, root))
    result = CliRunner().invoke(cli, sample, env=env, prog_name=root)
    findings: list[Finding] = []
    if result.exit_code != 0:
        message = f"exits {result.exit_code}, not 0"
        findings.append(Finding("BAS-4", command, message))
    elif "--json" in sample and not _is_json(result.stdout):
        findings.append(Finding("BAS-4", command, "`--json` prints no JSON"))
    for line in result.stdout.splitlines():
        if line.startswith(_MESSAGE):
            message = f"prints `{line}` to STDOUT"
            findings.append(Finding("BAS-5", command, message))
    if _TRACEBACK in result.stderr:
        message = "prints a traceback to STDERR"
        findings.append(Finding("ERR-2", command, message))
    return findings


def _is_json(text: str) -> bool:
    """Return whether `text` is one JSON document."""
    try:
        json.loads(text)
    except ValueError:
        return False
    return True
