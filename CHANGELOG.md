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

## [Unreleased]

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
