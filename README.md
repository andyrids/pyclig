# `pyclig`

A Python Click wrapper with Command Line Interface Guidelines (CLIG) paradigms.

> [!NOTE]
> `pyclig` is unofficial and not affiliated with the
> [Command Line Interface Guidelines](https://clig.dev/) or their authors.

click owns parsing, help, shell completion & the test runner. `pyclig` adds the conventions on
top: STDOUT for output & STDERR for messages, exit codes, error rendering, logging, output
primitives & standard flags. Options, arguments & types are plain click.

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
@click.option("--start", metavar="DATE")
@pyclig.pass_context
def list_(ctx: pyclig.Context, start: str | None, json_output: bool) -> int:
    """List bucket archives & local state."""
    ctx.out.print(f"from {start}")
    return pyclig.ExitCode.OK


if __name__ == "__main__":
    cli()
```

Point the entry point at the group: `[project.scripts] dkais = "dkais.__main__:cli"`. Always
name the group - the name is the program name, also under `python -m`, and sets the shell
completion variable (`_DKAIS_COMPLETE`).

Commands take `examples=` too: their `--help` lists them under `EXAMPLES:`, before the epilog.

## What every group gets

| Feature | Behaviour |
| --- | --- |
| `-h`, `--help` | Usage, description, options, commands, examples & epilog |
| Bare `prog` | Concise help on STDOUT, exit 0 - `--help` without options & epilog |
| `-v`, `--version` | `prog version` from the distribution metadata, else `0.0.0+unknown` |
| `-d`, `--debug` | On every command, before or after its name; `DEBUG` logging as soon as parsed |
| Subcommands | `@cli.command()` & `@cli.group()` create `pyclig.Command` & `pyclig.Group` |
| Arguments | Reach commands as typed - globs & variables are not expanded on Windows either |
| Streams | UTF-8 STDOUT & STDERR, so `✓` or `→` never fail on a cp1252 pipe |

`ctx.obj` is left to the application.

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
| Broken STDOUT pipe (`prog \| head -1`) | - | 1 |
| Any other exception | trimmed traceback, `error:`, bug report hint | 70 |

`pyclig.ExitCode` names the codes: `OK`, `FAILURE`, `USAGE`, `INTERNAL` & `INTERRUPT`. The bug
report hint names the distribution's `Issues` project URL. Messages are never parsed as Rich
markup: user input such as `[/b]` or `:warning:` prints as typed.

A command may catch Ctrl-C or its own errors to print a tailored message first - a returned code
passes through untouched. Wrap third-party failures (e.g. network errors) in an `errors=` type, so
users see a message instead of a crash.

## Output

`ctx.out` (STDOUT) & `ctx.err` (STDERR) are Rich consoles created for each run, with markup,
emoji codes & highlighting off. Pass `ctx.err` to any `Progress` or `Status`. Each console
follows its own stream: `FORCE_COLOR`, `TTY_COMPATIBLE` & `NO_COLOR` are honoured, and piped
output on Windows keeps its colour when forced.

| Primitive | On a terminal | Otherwise |
| --- | --- | --- |
| `notice(console, level=..., message=...)` | Bold red / yellow `level:`, wrapped | One line |
| `info(console, message=...)` | Dim | Plain |
| `hanging(console, head="✓", message=...)` | Wrapped under the message | Same |

Arguments after the console are keyword-only. Control characters, including terminal escapes,
are dropped from messages. Print machine-readable output - JSON, tab-separated rows - with
`click.echo`, which neither wraps nor expands tabs. Use `rich.text.Text` with a `style` for styled
output, and `TextColumn(markup=False)` in a Rich `Progress`.

## Standard flags

`pyclig.options` holds the flags with standard names, each taking a `help=` override:

| Factory | Flag | Parameter |
| --- | --- | --- |
| `json_output()` | `--json` | `json_output` |
| `select_all()` | `-a`, `--all` | `select_all` |
| `force()` | `-f`, `--force` | `force` |
| `dry_run()` | `-n`, `--dry-run` | `dry_run` |

## Confirmation

`pyclig.confirm()` asks before a large or destructive action, and `--force` skips the question:

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
| STDIN is not a terminal | `error:` naming `--force`, the command's usage, a `--help` hint | 2 |
| `y` or `yes` | The `[y/N]` prompt | continues |
| `n`, an empty answer or EOF | `error: aborted` | 1 |
| Ctrl-C | `warning: interrupted` | 130 |

A script cannot answer the prompt, so without a terminal on STDIN the run fails rather than read
an answer from a pipe. click writes the prompt to STDERR - with `2>log` it lands in the log - so
call `confirm` before starting a `Progress` or `Status`.

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
from pyclig.testing import invoke


def test_list_rows_when_piped() -> None:
    """Assert `list` prints tab-separated rows when STDOUT is a pipe."""
    result = invoke(cli, ["list"], out_tty=False, err_tty=True)
    assert result.exit_code == 0
    assert "\t" in result.stdout
```

`invoke` returns click's `Result`, with `stdout` & `stderr` apart. `out_tty`, `err_tty`, `color`
& `width` set up each console; `env` sets (or, with None, unsets) variables. Colour & terminal
variables from the developer's shell are cleared. Never patch Rich private attributes.

`in_tty=True` treats STDIN as a terminal, so `pyclig.confirm` prompts and reads its answer from
`input`. In `invoke`, click echoes that answer to STDERR after the prompt (`... [y/N]: y`).

## Parser-less entry points

`pyclig.run()` gives a pre-commit hook shim, which leaves `sys.argv` to the tool it wraps, the
same exit codes, error rendering & logging:

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
