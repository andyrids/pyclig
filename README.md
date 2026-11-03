# `pyclig`

A Python Click wrapper with Command Line Interface Guidelines (CLIG) paradigms.

> [!NOTE]
> `pyclig` is unofficial and not affiliated with the
> [Command Line Interface Guidelines](https://clig.dev/) or their authors.

click owns parsing, help, shell completion & the test runner. `pyclig` adds the conventions on
top: STDOUT for output & STDERR for messages, exit codes, error rendering, logging, output
primitives, run flags & standard flags. Options, arguments & types are plain click.

CLIG is treated as a contract: a CLI conforms with no application code wherever `pyclig` can do
it alone, gets one obvious interface for each rule that needs application input, and
`pyclig.testing.assert_conforms` reports the rest by rule ID. `docs/clig-coverage.md` has the
rule-by-rule status and `docs/roadmap.md` what each release adds. Pin `pyclig~=0.3.0` while it
is pre-1.0: a minor release may break, and `~=0.3` would admit 0.4.

## Usage

```python
import click
import pyclig

from dkais import exceptions


@pyclig.group(
    "dkais",
    short_help="DMA AIS data manager",
    examples=["dkais list --start 2026-10"],
    errors=(exceptions.Error,),
    epilog="For more information see https://github.com/andyrids/dkais.",
)
def cli() -> None:
    """Download DMA AIS archives and convert them to Parquet."""


@cli.command("list", examples=["dkais list --start 2026-10 --json"])
@pyclig.options.json_output()
@pyclig.options.plain()
@click.option("--start", metavar="DATE", help="The range start.")
@pyclig.pass_context
def list_(ctx: pyclig.Context, start: str | None, json_output: bool) -> int:
    """List bucket archives & local state."""
    if ctx.format == "human":
        ctx.out.print(f"from {start}")
    else:
        click.echo(f"start\t{start}")
    return pyclig.ExitCode.OK


if __name__ == "__main__":
    cli()
```

Point the entry point at the group: `[project.scripts] dkais = "dkais.__main__:cli"`. Always
name the group - the name is the program name, also under `python -m`, and sets the shell
completion variable (`_DKAIS_COMPLETE`). A single-command tool uses `pyclig.command()` instead,
and gets everything a command of a group does.

Commands take `examples=` too: their `--help` leads with them under `EXAMPLES:`.

## What every command gets

| Feature | Behaviour |
| --- | --- |
| `-h`, `--help` | Usage, description, examples, commands, options, global options & epilog |
| `-h` anywhere | Help, exit 0, even after a typo - anywhere before `--` |
| Bare `prog` | Concise help on STDOUT, exit 0 - `--help` without options & epilog |
| `prog cmd` needing arguments | Concise help on STDERR, exit 2 (`no_args_is_help=True`) |
| `-v`, `--version` | `prog version` from the metadata, else `0.0.0+unknown`; an app's `-v` wins |
| Run flags | `-d`, `-q`, `--no-color` & `--no-input`, before or after the command name |
| Subcommands | `@cli.command()` & `@cli.group()` create `pyclig.Command` & `pyclig.Group` |
| Arguments | Reach commands as typed - globs & variables are not expanded on Windows either |
| Streams | UTF-8 STDOUT & STDERR, so `✓` or `→` never fail on a cp1252 pipe |

`ctx.obj` is left to the application.

## Run flags

Run flags are about how a run behaves, never what a command does, so they are on every command
and act as soon as they are parsed - `-d` applies even when a later option is invalid:

| Flag | Effect | Read as |
| --- | --- | --- |
| `-d`, `--debug` | `DEBUG` logging, with times & call sites | - |
| `-q`, `--quiet` | Drops `info` lines & animation; notices, hints & STDOUT stay | `ctx.quiet` |
| `--no-color` | No colour on either console; bold & dim stay | - |
| `--no-input` | `confirm` & `prompt=` options fail instead of asking | `ctx.can_prompt` |

A command's own option with the same spelling wins: `copy -d /tmp` reaches the app, and
`--debug` still works there. The root's `--help` lists the run flags under `GLOBAL OPTIONS:`; a
subcommand's names them on one line.

An application declares its own with `cls=pyclig.GlobalOption` on the command whose subtree
accepts it, usually the root group. The callback is a plain click callback, called wherever the
flag is parsed:

```python
def _trace(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    if value:
        ctx.meta["trace"] = True


@pyclig.group("dkais")
@click.option(
    "--trace", cls=pyclig.GlobalOption, callback=_trace, help="Trace the run."
)
def cli() -> None: ...
```

## Errors & exit codes

Commands return an exit code (or None for 0). Anything else is mapped by the runner, with
messages on STDERR:

| Outcome | STDERR | Exit |
| --- | --- | --- |
| `return code` | - | code |
| `click.UsageError`, `ctx.fail()` | `error:`, the failing command's usage, a `--help` hint | 2 |
| Other `click.ClickException` | `error: message` | its code |
| Ctrl-C, in a command or at a prompt | `warning: interrupted` | 130 |
| Declined `click.confirm(abort=True)` | `error: aborted` | 1 |
| A type in `errors=` | `error: message`, the traceback first with `-d` | 1 |
| ... with a `hint` attribute | ... then the hint, dim, last | 1 |
| ... with an `exit_code` attribute | ... | that code |
| Broken STDOUT pipe (`prog \| head -1`) | - | 1 |
| Any other exception | trimmed traceback, `error:`, bug report hint | 70 |

`pyclig.ExitCode` names the codes: `OK`, `FAILURE`, `USAGE`, `INTERNAL` & `INTERRUPT`. The bug
report hint names the distribution's `Issues` project URL. Messages are never parsed as Rich
markup: user input such as `[/b]` or `:warning:` prints as typed.

`hint` & `exit_code` are read by attribute, so the application's exceptions need no `pyclig`
import - a class attribute on the exception type is enough:

```python
class ToolNotFoundError(Error):
    hint = "Run the hook in the environment pkgdx is installed in, e.g. via `uv run`"
```

A command may catch Ctrl-C or its own errors to print a tailored message first - a returned code
passes through untouched. Wrap third-party failures (e.g. network errors) in an `errors=` type, so
users see a message instead of a crash. `errors=` goes on the root; `add_command` rejects it on a
subcommand, where the runner would ignore it.

## Output

`ctx.out` (STDOUT) & `ctx.err` (STDERR) are Rich consoles created for each run, with markup,
emoji codes & highlighting off. Pass `ctx.err` to any `Progress` or `Status`, and gate animation
on `ctx.err.is_interactive`. Each console tells the truth about its own stream: `is_terminal` is
the real TTY check, so `FORCE_COLOR` means colour only - a piped console keeps its colour but
stays one line per message, never wraps and never animates. `NO_COLOR`, `TERM=dumb` &
`--no-color` drop colour; `TTY_COMPATIBLE=1` makes a pipe a terminal.

`ctx.format` says what a command producing records should print: `human` on a terminal,
otherwise `plain`; the per-command flags `--plain` (`pyclig.options.plain()`) & `--json`
(`pyclig.options.json_output()`) override it, `--json` winning in any order. Only commands that
produce records take the flags, so help never advertises a flag a command ignores.

| Primitive | On a terminal | Otherwise |
| --- | --- | --- |
| `notice(console, level=..., message=...)` | Bold red / yellow `level:`, wrapped | One line |
| `info(console, message=...)` | Dim; dropped with `-q` | Plain; dropped with `-q` |
| `hanging(console, head="✓", message=...)` | Wrapped under the message | Same |

Arguments after the console are keyword-only. Control characters, including terminal escapes,
are dropped from messages. Print machine-readable output - JSON, tab-separated rows - with
`click.echo`, which neither wraps nor expands tabs. Use `rich.text.Text` with a `style` for styled
output, and `TextColumn(markup=False)` in a Rich `Progress`.

## Standard flags

`pyclig.options` holds the flags with standard names, each taking a `help=` override:

| Factory | Flag | Parameter | Scope |
| --- | --- | --- | --- |
| `json_output()` | `--json` | `json_output`; sets `ctx.format` | Commands producing records |
| `plain()` | `--plain` | `ctx.format == "plain"` | Commands producing records |
| `select_all()` | `-a`, `--all` | `select_all` | Per command |
| `force()` | `-f`, `--force` | `force` | Per command |
| `dry_run()` | `-n`, `--dry-run` | `dry_run` | Per command |

## Prompts & confirmation

A prompt needs a terminal on STDIN to answer it and on STDERR to see it, and `--no-input` refuses
every prompt; `ctx.can_prompt` is that test. `pyclig.confirm()` asks before a large or
destructive action, and `--force` skips the question:

```python
@cli.command()
@pyclig.options.force()
@pyclig.pass_context
def purge(ctx: pyclig.Context, force: bool) -> None:
    """Delete every local archive."""
    pyclig.confirm(ctx, message="Delete every local archive?", force=force)
```

| Case | STDERR | Exit |
| --- | --- | --- |
| `force=True` | - | continues |
| STDIN or STDERR is not a terminal | `error:` naming `--force`, the usage, a `--help` hint | 2 |
| `--no-input` | `error:` naming `--no-input` & `--force`, the usage, a hint | 2 |
| `y` or `yes` | The `[y/N]` prompt | continues |
| `n`, an empty answer or EOF | `error: aborted` | 1 |
| Ctrl-C | `warning: interrupted` | 130 |

A script cannot answer the prompt, so the run fails rather than read an answer from a pipe, and
with `2>log` it fails rather than hide the question in the log. Call `confirm` before starting a
`Progress` or `Status`. A click option with `prompt=` follows the same rule: it prompts on STDERR,
and when the run cannot prompt it fails naming the option, so `--no-input` never lies.

## Logging

Log through the package logger - `logging.getLogger(__name__)` in any module of the package that
defines the group. Libraries add only a `NullHandler`, in the package `__init__.py`:

```python
logging.getLogger(__name__).addHandler(logging.NullHandler())
```

During a run, warnings & errors print as `warning:` / `error:` notices on `ctx.err`. With `-d`,
`DEBUG` records, times & call sites are added - laid out by a `RichHandler` when STDERR is a
terminal. Otherwise each record is one line that never wraps, with any traceback after it in plain
text:

```text
[2026-10-31T09:14:03+0000] DEBUG    [convert] converting 'nope'  types.py:47
```

The logger's handlers, level & propagation are restored when the run ends.

## Testing

```python
from pyclig.testing import assert_conforms, invoke


def test_list_rows_when_piped() -> None:
    """Assert `list` prints tab-separated rows when STDOUT is a pipe."""
    result = invoke(cli, ["list"], out_tty=False, err_tty=True)
    assert result.exit_code == 0
    assert "\t" in result.stdout


def test_cli_conforms() -> None:
    """Assert the CLI follows every guideline pyclig can check."""
    assert_conforms(cli, ignore={"ARG-16": "`--token` also reads a file"})
```

`invoke` runs any `pyclig.Command` or `Group` and returns click's `Result`, with `stdout` &
`stderr` apart. `out_tty`, `err_tty`, `color` & `width` set up each console; `env` sets (or, with
None, unsets) variables. Colour & terminal variables from the developer's shell are cleared. Never
patch Rich private attributes. `in_tty=True` & `err_tty=True` let `pyclig.confirm` & `prompt=`
options prompt and read their answer from `input`; click echoes that answer to STDERR after the
prompt (`... [y/N]: y`).

`assert_conforms` walks the CLI and reports deviations by the rule IDs of
`docs/clig-coverage.md`: flags without a long form or help text, standard short flags with
another meaning, secret-looking flags & environment variables, a root without examples, plain
click children, and help or unknown-flag probes that misuse exit codes or streams. It never runs
a command body. `check` returns the `Finding`s instead of asserting; `ignore` needs a reason per
rule.

## Parser-less entry points

`pyclig.run()` gives a pre-commit hook shim, which leaves `sys.argv` to the tool it wraps, the
same exit codes, error rendering & logging. It enters a `pyclig.Context`, so the function may be
a `pyclig.pass_context` function using `ctx.err`:

```python
def ruff_format() -> NoReturn:
    pyclig.run(
        lambda: core_ruff_format(sys.argv[1:]),
        errors=(exceptions.Error,),
    )
```

## Migrating from argparse

- Each subcommand becomes a `@cli.command()`; shared options become one decorator stacking
  `click.option`s. Commands are listed in the order they are added.
- click shows a command's docstring as its help: put `\f` after the help paragraph, so the
  `Args:` & `Returns:` sections stay out of `--help`. Pass `help=` for a description that is not
  an imperative docstring line.
- Custom argument types become `click.ParamType[T]` subclasses calling `self.fail()`.
- `parser.error()` becomes `raise click.UsageError(...)` (or `ctx.fail()`).
- A `type=` function checking a minimum becomes `click.IntRange(min=1)`.
- An environment variable default becomes `envvar=`, with `show_envvar=True` so a missing value
  names it.
- Module-level consoles become `ctx.out` / `ctx.err`, passed to helpers as arguments.
- argparse accepted unambiguous option prefixes (`--st` for `--start`); click does not.
