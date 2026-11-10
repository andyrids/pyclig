<!-- pyml disable MD024 -->
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> [!NOTE]
>
> - `[SemVer] - yyyy-mm-dd` or `[Unreleased]` for release heading.
> - `Added` for new features.
> - `Changed` for changes in existing functionality.
> - `Deprecated` for soon-to-be removed features.
> - `Removed` for now removed features.
> - `Fixed` for any bug fixes.
> - `Security` in case of vulnerabilities.

## [0.6.0] - 2026-11-10

### Added

- Per-run signal handlers: Ctrl-C (and Ctrl-Break on Windows) prints `warning: interrupted` at
  once & exits 130; `SIGTERM` prints `warning: terminated` & exits 143 (`ExitCode.TERMINATE`)
- `ctx.cleanup(timeout=10.0)`: bounds clean-up after an interrupt - a second Ctrl-C or the
  timeout flushes the streams & exits at once
- Third-party `WARNING` records & `warnings.warn` print as `warning:` notices when the root logger
  has no handlers; `file:line` shows under `-d`
- `<PROG>_LOG_FILE`: appends a `DEBUG` log of every run to a file; a crash adds its traceback &
  the hint `debug log: FILE`
- `ctx.logs_on_failure(level=logging.INFO)`: holds a block's info lines & prints them only when an
  exception leaves it
- `pyclig.confirm_name` & `options.confirm()`: `--confirm NAME` or a typed name for severe
  actions, never skipped by `--force`
- `options.timeout()`: `--timeout SECONDS`, a positive float, 30 by default
- `testing.invoke` clears `<PROG>_LOG_FILE`

## [0.5.0] - 2026-11-06

### Added

- `pyclig.Config` & `config=`: `--config FILE` & `--profile NAME` read TOML files into click's
  `default_map` - flags > env > `.env` > profile > project > user > system > defaults
- `Config(dotenv=True)`: `./.env` fills declared `envvar=` options the environment left empty,
  never `os.environ`; secret-named keys are skipped
- `pyclig.paths`: `config_dir`, `data_dir` & `system_config_dir` - XDG everywhere but Windows
- `GlobalOption` takes a value with `type=`; its callback runs when given, never for `default=`
- `options.secret(name)`: `--<name>-file FILE` reads a secret from a file or piped STDIN, never
  from a terminal
- `options.output`, `options.port` & `options.user`: `-o`, `-p` & `-u` with their standard names
- `<PROG>_DEBUG` & `<PROG>_NO_COLOR`, read before parsing; off for `0`, `false`, `no` & `off`
- `testing.invoke(config_files=)`: no config file or `.env` is read in a test unless asked, and
  `<PROG>_DEBUG`, `_NO_COLOR`, `_CONFIG` & `_PROFILE` are cleared

## [0.4.0] - 2026-11-04

### Added

- `ctx.emit(records, table=..., caption=...)`: JSON, tab-separated rows or a table by `ctx.format`
- `pyclig.row` & `pyclig.summary`: state rows & a closing line; `-q` drops them unless essential
  or failed
- `pyclig.status` & `pyclig.progress`: a spinner & a Rich `Progress` that animate only on an
  interactive console
- `pyclig.hint`: the next-step line, kept with `-q`
- `notice(items=...)`: grouped failures under one header, printed in one call
- `help` & `help <command>...` on every group, unlisted; an app's own `help` command wins
- `with ctx.pager():` pages `human` output through click's pager with `LESS=-FIRX`; opt-in
  through `PAGER` on Windows, where `more` cannot show it

### Fixed

- Messages drop C1 control codes, so an 8-bit CSI (`\x9b`) cannot restyle the terminal

## [0.3.0] - 2026-11-03

### Added

- `pyclig.command()`: a standalone command with the runner, run flags, `-h` & `-v/--version`
- `pyclig.GlobalOption`: a run flag declared once, accepted on every command below it; its
  callback runs only where the flag was given, so it must be idempotent
- `-q/--quiet`, `--no-color` & `--no-input` on every command, before or after its name
- `ctx.quiet`, `ctx.can_prompt` & `ctx.format` (`human`, `plain` or `json`)
- `pyclig.options.plain()`: `--plain`, per command; `--json` now sets `ctx.format` too
- `hint` & `exit_code` attributes on `errors=` types: a dim remedy line, a non-zero code other
  than 1 (anything else, such as 0 or a bool, still exits 1)
- `pyclig.testing.check`, `assert_conforms` & `Finding`: the CLIG conformance kit, by rule ID
- `docs/clig-coverage.md`, the rule-by-rule requirement table, & `docs/roadmap.md`

### Changed

- **Breaking:** `FORCE_COLOR` means colour only - a piped console keeps its colour but is not a
  terminal, so notices stay one line, `-d` stays plain & nothing animates; `TTY_COMPATIBLE=1`
  still makes a pipe a terminal. A CLI pinned to `~=0.2` picks this up on its next install
- **Breaking:** `pyclig.confirm()` needs a terminal on STDERR as well as STDIN & honours
  `--no-input`; its message now says why (`there is no terminal to ask on`, `--no-input was given`)
- **Breaking:** help order is `USAGE`, description, `EXAMPLES`, `COMMANDS`, `OPTIONS`, `GLOBAL
  OPTIONS`, epilog; run flags leave `OPTIONS:` for `GLOBAL OPTIONS:`, one line on subcommands
- A command with `no_args_is_help` prints concise help (usage, description, examples, hint)
- A click `prompt=` option prompts on STDERR; when the run cannot prompt it takes its default,
  or fails naming itself when it has none
- The runner, `errors=` & the Ctrl-C/EOF/pipe translation live on `Command`; `Group.add_command`
  rejects a subcommand that sets `errors=`
- `pyclig.run()` enters a `Context`, so a `pass_context` shim gets `ctx.err`
- `pyclig.testing.invoke` takes any `pyclig.Command` & gives the run `err_tty`
- `-d` is the first `GlobalOption`; a command's own `-d` (e.g. `-d/--dir`) wins & `--debug` stays;
  likewise an app's `-v/--verbose` keeps `--version` as the long form only

### Fixed

- `-h` & `--help` show help, exit 0, after an unknown option, a flag given a value or an unknown
  command - anywhere before `--`
- `-d`, `ctx.out` & `-h` on `click.command(cls=pyclig.Command)` standalone commands
- `-q` keeps the `--help` pointer of a usage error & error hints

## [0.2.0] - 2026-10-31

### Added

- `examples=` on commands, listed under `EXAMPLES:` in their `--help`
- `pyclig.confirm()`: a `[y/N]` prompt on a terminal STDIN, else exit 2 naming `--force`
- `pyclig.options.dry_run()`: `-n/--dry-run`
- `pyclig.testing.invoke(in_tty=True)`, for code that prompts with `pyclig.confirm()`

### Changed

- `-d` prints each record as one plain line when STDERR is not a terminal; Rich layout otherwise

### Fixed

- `error: aborted` after EOF (Ctrl-D) at a prompt starts its own line on a terminal

## [0.1.0] - 2026-10-31

### Added

- `pyclig.group()`, `Group` & `Command`: click classes with CLIG help, `-d`, `-v` & a runner
- `pyclig.Context` with per-run `out` & `err` consoles; `pyclig.pass_context`
- Exit codes `0`/`1`/`2`/`70`/`130` (`pyclig.ExitCode`) & `error:` / `warning:` rendering
- Ctrl-C, `EOFError` & broken pipes (incl. Windows `EINVAL`) mapped instead of swallowed by click
- `notice`, `info` & `hanging` output primitives that never parse markup
- `pyclig.options`: `--json`, `-a/--all` & `-f/--force`
- `pyclig.run()` for parser-less entry points, e.g. pre-commit hook shims
- `pyclig.testing.invoke()`, with a TTY flag for each stream
