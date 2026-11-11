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
rule-by-rule status and `docs/roadmap.md` what each release adds. Pin `pyclig~=0.6.0` while it
is pre-1.0: a minor release may break, and `~=0.6` would admit 0.7.

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

Commands take `examples=` too: their `--help` leads with them under `EXAMPLES:`. An example
may show its output on the lines after the invocation, which print indented under it:

```python
@cli.command(examples=["dkais count --start 2026-10\n31 archives"])
```

`docs="https://..."` on a group or a command adds a closing `LEARN MORE:` section to its full
help. The root's also lists `Issues`, the bug tracker in the distribution's `Project-URL`
metadata.

## What every command gets

| Feature | Behaviour |
| --- | --- |
| `-h`, `--help` | Usage, description, examples, commands, options, global options & epilog |
| `-h` anywhere | Help, exit 0, even after a typo - anywhere before `--` |
| Bare `prog` | Concise help on STDOUT, exit 0 - no global options, epilog or links |
| `prog cmd` needing arguments | Concise help on STDERR, exit 2 (`no_args_is_help=True`) |
| Concise help | Lists a command's own options when it has 1 to 6 |
| Headings | Bold where the console is styled - never on a pipe or with `TERM=dumb` |
| `-v`, `--version` | `prog version`, before or after a command name; an app's `-v` wins |
| `deprecated=` | In use: `warning: command 'old' is deprecated - REASON` on STDERR |
| `click.File("r")` | `-` on a terminal STDIN is a usage error, not a silent wait |
| Run flags | `-d`, `-q`, `--no-color` & `--no-input`, before or after the command name |
| `<PROG>_DEBUG`, `<PROG>_NO_COLOR` | `-d` & `--no-color` from the environment, before parsing |
| `help`, `help cmd...` | A group's or the named command's help, exit 0; unlisted, an app's wins |
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

`<PROG>_DEBUG=1` and `<PROG>_NO_COLOR=1` do the same from the environment, read before parsing,
so even `-d`'s own parse-time records appear; a later `-d` or `--no-color` is a no-op. `<PROG>` is
the package name upper-cased with `_` for every other character (`my-tool` is `MY_TOOL`). A value
is on when set, non-empty and not `0`, `false`, `no` or `off`; bare `NO_COLOR` keeps Rich's rule,
on whenever it is set. Neither is listed in `--help`. Run flags also read config files
(`quiet = true`, see Configuration).

A command's own option with the same spelling wins: `copy -d /tmp` reaches the app, and
`--debug` still works there. The root's `--help` lists the run flags under `GLOBAL OPTIONS:`; a
subcommand's names them on one line.

An application declares its own with `cls=pyclig.GlobalOption` on the command whose subtree
accepts it, usually the root group. The callback is a plain click callback. It runs only when
the option was given - on the command line, through `envvar=` or from a config file - never for
its `default=`, and may run once per level of a nested command line that sees it (each level
reads the environment), so it must be idempotent:

```python
def _trace(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    ctx.meta["trace"] = True


@pyclig.group("dkais")
@click.option(
    "--trace", cls=pyclig.GlobalOption, callback=_trace, help="Trace the run."
)
def cli() -> None: ...
```

With `type=` (or `is_flag=False`) a `GlobalOption` takes a value, which the callback shares with
the commands below through `ctx.meta`. A top-level key of a config file configures it
(`region = "eu"`), which is how a setting shared by several commands is configured:

```python
def _region(ctx: click.Context, param: click.Parameter, value: str) -> None:
    ctx.meta["app.region"] = value


@pyclig.group("dkais")
@click.option(
    "--region",
    cls=pyclig.GlobalOption,
    type=str,
    callback=_region,
    help="The region.",
)
def cli() -> None: ...
```

## Configuration

Config is opt-in: a CLI without `config=` gets no new options and reads no files.

```python
@pyclig.group(
    "dkais", config=pyclig.Config(project=".dkais.toml", profiles=True)
)
def cli() -> None: ...
```

| `Config` field | Meaning | Default |
| --- | --- | --- |
| `name` | The config directories & the default project file | the package |
| `project` | The project file, found from the working directory upward | `.<name>.toml` |
| `table` | A dotted table of the project file, e.g. `tool.<name>` in `pyproject.toml` | whole |
| `profiles` | Add `--profile NAME`; `[profiles.NAME]` outranks the main tables | `False` |
| `dotenv` | Read `./.env` into declared `envvar=` options | `False` |

The files are TOML, read into click's `default_map` before any other option, so click's own
order gives the precedence, highest first:

1. The command line
2. The environment, via `envvar=`
3. `./.env`, with `dotenv=True`
4. `[profiles.NAME]` - project, then user, then system file - with `--profile NAME`
5. The project file, nearest from the working directory upward
6. The user file, `paths.config_dir(name)/config.toml`
7. The system file, `paths.system_config_dir(name)/config.toml`
8. The application's `default_map`, then `default=`

Top-level keys configure the root command and a `[sub]` table its subcommand, as `default_map`
does; they do not cascade, so a setting shared by several commands is a value `GlobalOption`
(above) or is repeated per table. Tables merge recursively; scalars and lists are replaced. Run
flags read config like any option (`quiet = true`), unknown keys are ignored, and `-d` logs the
files it loaded.

`--config FILE` (or `<PROG>_CONFIG`) replaces every discovered file. It is read whole unless it
is named like the project file: `--config ../pyproject.toml` selects `table` as discovery would.
`prog sub --config FILE` applies the file to `sub` and below. `prog --help`, `-v` and completion
read no file, and a file that cannot be read is reported only when a command runs, so a
broken file never hides the help.

| Case | Result |
| --- | --- |
| No file | Nothing read; `tomllib` is not imported |
| Bad TOML, or a found file unreadable | `error: cannot read config PATH: detail`, exit 1 |
| `--config` missing, or a directory | Usage error, exit 2 |
| `--profile x` in no loaded file | Usage error naming the files, exit 2 |
| `[sub]` is not a table | `error: config: [sub] must be a table, not int`, exit 1 |

### `.env`

With `dotenv=True` the root reads `./.env` once, into the options that declare `envvar=` and
found nothing in the environment. It never writes `os.environ`, so child processes see no change.
The rules are deliberately small: `KEY=value` and `export KEY=value` lines; `#` comments and
blank lines are skipped; an unquoted value loses a trailing `# comment` after a space; single
or double quotes are removed; there are no escapes and no `$VAR` expansion. A key ending in a
secret word (`_TOKEN`, `_PASSWORD`, `_API_KEY`...) is skipped, see Secrets. Any other line warns
`.env:LINE: not KEY=VALUE, ignored` and the rest is still read.

In tests, `invoke` reads no config file or `.env` unless `config_files=True`, and clears
`<PROG>_DEBUG`, `_NO_COLOR`, `_CONFIG` and `_PROFILE`, so a developer's own settings never leak
in; `--config` and `env={"<PROG>_CONFIG": ...}` still work.

## Paths

`pyclig.paths` returns the per-user and system directories, XDG everywhere but Windows, and
creates none of them:

| Function | Windows | XDG | Fallback |
| --- | --- | --- | --- |
| `config_dir(name)` | `%APPDATA%\name` | `$XDG_CONFIG_HOME/name` | `~/.config/name` |
| `data_dir(name)` | `%LOCALAPPDATA%\name` | `$XDG_DATA_HOME/name` | `~/.local/share/name` |
| `system_config_dir(name)` | `%PROGRAMDATA%\name` | first of `$XDG_CONFIG_DIRS` | `/etc/xdg/name` |

A relative XDG value is ignored (`$XDG_CONFIG_DIRS` gives its first absolute entry), and macOS
follows XDG rather than `~/Library`. The environment, platform and home are read on every call,
so tests can patch them.

## Secrets

A secret belongs neither on the command line nor in an environment variable (the kit reports
ARG-16 and ENV-15). `pyclig.options.secret("api-key")` adds `--api-key-file FILE` and hands the
command the file's text as `api_key`, one trailing newline removed; `-` reads a piped STDIN, so a
secret store is reached by a pipe or process substitution:

```sh
pass show prog/token | prog login --token-file -
prog login --token-file <(pass show prog/token)
```

| Input | Command receives |
| --- | --- |
| Not given | `None`, or a usage error with `required=True` |
| FILE, `/dev/fd/N`, `<(...)` | UTF-8 text, one trailing `\n` or `\r\n` removed |
| `-`, STDIN piped | STDIN text, same rule |
| `-`, STDIN a terminal | Usage error, exit 2 - it never blocks or echoes |
| Empty, missing or a directory | Usage error, exit 2 |

## Errors & exit codes

Commands return an exit code (or None for 0). Anything else is mapped by the runner, with
messages on STDERR:

| Outcome | STDERR | Exit |
| --- | --- | --- |
| `return code` | - | code |
| `click.UsageError`, `ctx.fail()` | `error:`, the failing command's usage, a `--help` hint | 2 |
| Other `click.ClickException` | `error: message` | its code |
| Ctrl-C (Ctrl-Break on Windows), in a command or at a prompt | `warning: interrupted` | 130 |
| `SIGTERM` (POSIX) | `warning: terminated` | 143 |
| Declined `click.confirm(abort=True)` | `error: aborted` | 1 |
| A type in `errors=` | `error: message`, the traceback first with `-d` | 1 |
| ... with a `hint` attribute | ... then the hint, dim, last | 1 |
| ... with an `exit_code` attribute | ... | that code, if a non-zero int |
| Broken STDOUT pipe (`prog \| head -1`) | - | 1 |
| Any other exception | trimmed traceback, `error:`, bug report hint | 70 |

`pyclig.ExitCode` names the codes: `OK`, `FAILURE`, `USAGE`, `INTERNAL`,
`INTERRUPT` & `TERMINATE`. Messages are never parsed as Rich
markup: user input such as `[/b]` or `:warning:` prints as typed.

The bug report hint links the distribution's `Issues` project URL on a line of its own, never
wrapped. On github.com & gitlab.com the link opens a new issue, pre-filled with:

- the program & its version, the pyclig version;
- the Python version & implementation, the operating system & its release;
- the exception's type.

It never contains the exception's message, the command line arguments, a path or the environment,
which may hold secrets. The user pastes the output themselves.

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

## Signals & clean-up

Each run installs its own `SIGINT`, `SIGTERM` & (on Windows) `SIGBREAK` handlers and restores the
previous ones when it ends. The notice prints as soon as the signal arrives, not after the stack
unwinds, and the run exits 130 (`interrupted`) or 143 (`terminated`). On Windows `os.kill(pid,
SIGTERM)` is `TerminateProcess`: the process ends at once with exit 15 and no handler runs - send
`CTRL_BREAK_EVENT` to a process group instead, which exits 130.

Wrap clean-up that must run after an interrupt in `ctx.cleanup`, so it is bounded:

```python
try:
    work(pool)
finally:
    with ctx.cleanup(timeout=10):
        pool.shutdown()
```

| Case | STDERR | Exit |
| --- | --- | --- |
| No interrupt | - | as the command returns |
| Interrupted, the block finishes | `cleaning up - press Ctrl-C again to skip` | 130 |
| A second Ctrl-C in the block | `warning: clean-up skipped` | 130, at once |
| The timeout passes | `warning: clean-up timed out after 10s` | 130, at once |
| `SIGTERM` | `warning: terminated`, `cleaning up` | 143 |

The timeout counts from the interrupt; `timeout=None` allows any time, though a second signal still
skips. A skip or timeout flushes the streams and exits even while the block is stuck in a blocking
call. Off the main thread, or with no interrupt, the block simply runs.

A blocking call, such as a socket read on Windows, holds Ctrl-C back until it returns. Wrap
blocking network I/O in the same block: the notice then prints at once, and the run exits when
the call returns or the timeout passes, whichever is first:

```python
with ctx.cleanup(timeout=2):
    data = connection.recv(4096)
```

## Output

`ctx.out` (STDOUT) & `ctx.err` (STDERR) are Rich consoles created for each run, with markup,
emoji codes & highlighting off. Each console tells the truth about its own stream: `is_terminal` is
the real TTY check, so `FORCE_COLOR` means colour only - a piped console keeps its colour but
stays one line per message, never wraps and never animates. `NO_COLOR`, `<PROG>_NO_COLOR`,
`TERM=dumb` & `--no-color` drop colour; `TTY_COMPATIBLE=1` makes a pipe a terminal.

`ctx.format` says what a command producing records should print: `human` on a terminal,
otherwise `plain`; the per-command flags `--plain` (`pyclig.options.plain()`) & `--json`
(`pyclig.options.json_output()`) override it, `--json` winning in any order. Only commands that
produce records take the flags, so help never advertises a flag a command ignores.
`ctx.emit(records, table=..., caption=...)` prints the records in that format:

| Format | STDOUT | Caption |
| --- | --- | --- |
| `json` | An indented list; values JSON cannot encode print as `str()` | Dropped |
| `plain` | Tab-separated rows, no header, columns from the first record's keys | `info(ctx.err)` |
| `human` | `table()`, or a default table with a column per key | Below the table |

A plain cell never breaks its row: `None` is empty, bools are `true`/`false`, tabs & newlines
become one space. Without records JSON prints `[]` and the others only the caption. `table` is a
factory, so cells can depend on other fields and `rich.table` stays off the fast paths.

`with ctx.pager():` pages what the block prints on `ctx.out`, in `human` format only - `plain` &
`json` are for pipes. It goes through `click.echo_via_pager`, so `PAGER` is honoured and `less`
gets `LESS=-FIRX` when `LESS` is unset. On Windows paging is opt-in: with `PAGER` blank the output
prints directly, because click's fallback there is `more`, which garbles UTF-8 and cannot scroll;
`PAGER=less` (Git for Windows ships one) pages in colour. Output is held until the block ends, and
`click.echo` inside it bypasses the page.

Messages & feedback take the console first, then keyword-only arguments:

| Primitive | On a terminal | Otherwise |
| --- | --- | --- |
| `notice(level=, message=, items=())` | Bold `level:`, wrapped; items indented | One line each |
| `info(message=)` | Dim; dropped with `-q` | Plain; dropped with `-q` |
| `hint(message=)` | Dim; kept with `-q` | Plain; kept with `-q` |
| `hanging(head="✓", message=)` | Wrapped under the message | Same |
| `row(mark=, label=, detail=, width=)` | `mark  label  detail`, never wrapped | Same |
| `summary(message=, failed=)` | `✓ message`, or `! message` when failed; wrapped | One line |
| `status(message=)` | A spinner around the block | No-op |
| `progress(columns=, **kwargs)` | A transient Rich `Progress` | Disabled |

`-q` drops `info`, `row` (unless `essential=True`), `summary` (unless `failed=True`) & animation;
`notice` & `hint` stay. `status` & `progress` animate only on an interactive console. A grouped
failure is one `notice(items=...)` then a `hint` with the remedy. Control characters, including
terminal escapes, are dropped from messages, and a `str` is never parsed as markup; a
`rich.text.Text` with a `style` prints styled, as given. That holds for the description column &
`str` columns of `progress` too, so prefer them to a `TextColumn` of your own, which renders as you
built it.

## Standard flags

`pyclig.options` holds the flags with standard names, each taking a `help=` override; the value
flags also take `default=` and `envvar=`:

| Factory | Flag | Parameter | Scope |
| --- | --- | --- | --- |
| `json_output()` | `--json` | `json_output`; sets `ctx.format` | Commands producing records |
| `plain()` | `--plain` | `ctx.format == "plain"` | Commands producing records |
| `select_all()` | `-a`, `--all` | `select_all` | Per command |
| `force()` | `-f`, `--force` | `force` | Per command |
| `dry_run()` | `-n`, `--dry-run` | `dry_run` | Per command |
| `output()` | `-o`, `--output FILE` | `output`, a `Path` or None | Per command |
| `port()` | `-p`, `--port PORT` | `port`, 1 to 65535 | Per command |
| `user()` | `-u`, `--user NAME` | `user` | Per command |
| `secret(name)` | `--<name>-file FILE` | `<name>`, the file's text (see Secrets) | Per command |
| `timeout()` | `--timeout SECONDS` | `timeout`, a positive float (default 30) | Per command |
| `confirm()` | `--confirm NAME` | `confirmed`, for `confirm_name` | Per command |

`options.NoneOr` is a type for an option whose value can be switched off: `--limit none` hands
the command None, any other value goes to the inner type, and help shows `--limit INTEGER|none`.
The word is matched in any case, from the command line, an `envvar=` or a config file:

```python
@click.option("--limit", type=pyclig.options.NoneOr(int), default=50)
```

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
and when the run cannot prompt it takes its default, or fails naming the option when it has none -
so `--no-input` never lies.

A severe action - one that cannot be undone, such as dropping a database - asks for the resource's
name instead. `pyclig.confirm_name()` pairs with `options.confirm()`, and `--force` never skips it:

```python
@cli.command()
@pyclig.options.confirm()
@pyclig.pass_context
def drop(ctx: pyclig.Context, confirmed: str | None) -> None:
    """Drop the production database."""
    pyclig.confirm_name(
        ctx, message="Drop prod?", name="prod", confirmed=confirmed
    )
```

| Case | STDERR | Exit |
| --- | --- | --- |
| `--confirm prod` | - | continues |
| `--confirm` with another name | `error:` naming `prod`, the usage, a hint | 2 |
| STDIN or STDERR is not a terminal | `error:` naming `--confirm`, the usage, a hint | 2 |
| `--no-input` | `error:` naming `--no-input` & `--confirm`, the usage, a hint | 2 |
| `prod` typed at the prompt | The prompt | continues |
| Another name, an empty answer or EOF | `error: aborted` | 1 |

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

When the root logger has no handlers as the run starts, it gets one too: third-party `WARNING`
records and `warnings.warn` print as `warning:` notices - the message only, with `file:line` added
under `-d`. The root's level is never changed, and an application that configures the root itself
(e.g. `logging.basicConfig`) is left alone. Both are restored when the run ends.

`<PROG>_LOG_FILE=FILE` appends every record of the run, at `DEBUG` and in the plain `-d` format,
to `FILE` (UTF-8), without changing what STDERR shows. A crash (exit 70) writes its traceback there
too and adds the hint `debug log: FILE`. If the file cannot be opened, `warning: cannot write the
debug log to FILE: reason` prints and the run goes on.

`ctx.logs_on_failure()` holds the info lines of a block and prints them only if it fails:

```python
with ctx.logs_on_failure():
    for step in steps:
        logger.info("ran %s", step)
        run(step)
```

Warnings & errors still print at once. Raise to fail: when an exception leaves the block, the held
lines print before it propagates, so `error:` is still last; on success, `Abort`, `Exit` or
Ctrl-C they are dropped. `-q` hides the replayed lines, `-d` prints every record live, and the log
file gets every record either way. Keep the block outside `progress` & `status`, so the replay is
not drawn over.

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
`docs/clig-coverage.md`. It never runs a command body unless given `samples=`. `check` returns
the `Finding`s instead of asserting; `ignore` needs a reason per rule.

| Rules | Finding |
| --- | --- |
| HELP-1, HELP-3, HELP-9 | Misused help probes; a flag without help; a root without examples |
| BAS-2, BAS-5 | Help or unknown-flag probes with the wrong exit code or stream |
| ARG-1, ARG-5 | An argument typed like a flag's value; arguments of differing types |
| ARG-2, ARG-3 | A flag without a long form; a one-letter flag outside the standard set |
| ARG-6 | A standard short with another meaning, or a standard long with another short |
| ARG-16, ENV-15 | Secret-looking flags & environment variables |
| ENV-2, ENV-4 | An `envvar=` that is not portable, or that reuses a common name |
| SUB-3 | A plain click child; one flag with another short or kind across commands |
| SUB-4, SUB-5 | Sibling names mixing `-` & `_` or upper case; confusable names |

`samples=` are command lines the kit runs for real, so name ones that are safe in a test:

```python
assert_conforms(cli, samples=[["list", "--json"], ["show", "--value", "x"]])
```

A sample that exits non-zero or prints invalid `--json` is BAS-4, an `error:` or `warning:` line
on STDOUT is BAS-5, and a traceback is ERR-2.

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
