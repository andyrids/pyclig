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

- `examples=` on commands, listed under `EXAMPLES:` in their `--help`
- `pyclig.confirm()`: a `[y/N]` prompt on a terminal STDIN, else exit 2 naming `--force`
- `pyclig.options.dry_run()`: `-n/--dry-run`
- `pyclig.testing.invoke(in_tty=True)`, for code that prompts with `pyclig.confirm()`

### Changed

- `-d` prints each record as one plain line when STDERR is not a terminal; Rich layout otherwise

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
