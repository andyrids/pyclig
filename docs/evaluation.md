# Evaluation - porting dkais & pkgdx onto pyclig

Date: 2026-10-31. Host: Windows 11, Python 3.13 project environments; pyclig is also tested on
3.11 & 3.14. Branches: pyclig `main`, dkais & pkgdx `feat/pyclig`.

## Summary

Every CLI issue filed against both projects is fixed, and none of their existing behaviour
regressed beyond the user-visible changes approved at STOP A. The evidence is in-repo tests:

| Repository | Tests | Notes |
| --- | --- | --- |
| pyclig | 89 passed, 95% coverage | 3.11, 3.13 & 3.14; mypy clean, no `type: ignore` |
| dkais | 107 passed | prek (ruff, mypy, pymarkdown, detect-secrets) passes |
| pkgdx | 127 passed | prek passes; `pkgdx init` ledger identical to `main` |

## Per issue

### dkais (GitHub)

| Issue | Result | Evidence |
| --- | --- | --- |
| #7 usage errors split | Fixed | `test_usage_error_only_on_stderr`, `..._prints_input_literally` |
| #8 `-d` after command | Fixed | `test_debug_before_or_after_command` |
| #9 Ctrl-C traceback | Fixed | `test_list_interrupt_exits_130`, `..._message_unchanged` |
| #10 `FORCE_COLOR` | Fixed | `test_forced_colour_styles_piped_summary` (subprocess) |
| #11 `list` table piped | Fixed | `test_list_rows_when_piped`, `test_list_table_on_a_terminal` |
| #12 exit codes | Fixed | `test_crash_exits_70_with_bug_hint`; usage tests assert 2 |
| #13 slow `--help` | Fixed | `test_fast_paths_skip_heavy_imports`; 844 -> 290 ms |
| #14 stale docs | Fixed | Guidance texts approved at STOP A |
| #15 stream routing | Fixed | Every CLI test asserts `stdout` & `stderr` apart (see note) |
| #16 `config.toml` | Fixed | Deleted; `test_import_installs_only_a_null_handler` |

Note on #15: its criterion asks that reverting the #7 fix fails a test.
`test_usage_error_only_on_stderr` asserts an empty STDOUT, and the old `error()` printed the
message there, so it fails by construction - it was not re-run against `main`.

### pkgdx (GitLab)

| Issue | Result | Evidence |
| --- | --- | --- |
| #7 usage errors split | Fixed | `test_usage_error_only_on_stderr` (`[red]x`, `:warning:`) |
| #8 global console | Fixed | `test_import_has_no_side_effects` (subprocess) |
| #9 `-d` after command | Fixed | `test_debug_before_or_after_command` |
| #10 Ctrl-C traceback | Fixed | `test_config_interrupt_exits_130`, `..._interrupt_exits_130` |
| #11 `FORCE_COLOR` (+ §6) | Fixed | `test_config_rows_styled_when_forced`; pyclig exit codes |
| #12 missing metadata | Fixed | `test_version_fallback_without_metadata` |
| #13 Rich private patches | Fixed | No `_force_terminal`, `_width` or `_color_system` in tests |
| #14 verbose handler | Fixed | `logging/` deleted; pyclig `test_logging.py` |

### Found during the review, not filed

| Finding | Result | Evidence (pyclig unless named) |
| --- | --- | --- |
| Windows broken pipe, exit 120 | Fixed | `test_broken_stdout_pipe_exits_quietly` |
| cp1252 pipes crash on `✓` / `→` | Fixed | `test_piped_output_encodes_any_text` |
| click turns `EOFError` into "Aborted!" | Fixed | `test_eof_error_is_a_crash` |
| `-d` lost on nested groups | Fixed | `test_debug_before_or_after_command` |
| dkais S3 listing errors crash | Fixed | dkais `test_list_archives_wraps_bucket_errors` |
| `*`, `~` & `%VAR%` expanded on Windows | Fixed | `test_arguments_reach_commands_as_typed` |

## Timings

Median of 15 runs, no network, `DKAIS_DATA_DIR` unset.

| Measurement | Before (`main`) | After |
| --- | --- | --- |
| `dkais --help` | 844 ms | 290 ms |
| `dkais -v` | 838 ms | 290 ms |
| `import dkais.__main__` (`-X importtime`) | 678 ms | 162 ms |
| `pkgdx --help` | 335 ms | 333 ms |
| `import pkgdx.__main__` (hook shim start-up) | 333 ms | 333 ms |

dkais's fast paths no longer import polars, boto3, psutil, Rich progress or pygments. pkgdx's
start-up is unchanged, so the hook shims stay in `__main__`.

## API friction met while porting

Applied to pyclig:

- click lists commands by name; both CLIs list them in workflow order. `Group.list_commands` now
   keeps the definition order.
- pkgdx's spinner test needs an interactive STDERR. `testing.invoke(interactive=True)` provides
   one.
- `-v` scanned every installed distribution (`packages_distributions`, ~80 ms). The import name
   is now looked up first.

Documented, no change proposed:

- Logging binds to the top-level package of the group callback, so modules log through
   `getLogger(__name__)`.
- click shows a command's whole docstring, `Args:` included - put `\f` after the help paragraph.
- A description that is not an imperative docstring line fails D401 - pass `help=` to
   `pyclig.group`, as both CLIs do.
- Helpers that take consoles print machine-readable lines with `click.echo(line, file=out.file)`,
   which keeps them testable with an in-memory console.
- `self.fail()` in a `click.ParamType` is `NoReturn`, but ruff's RET503 does not know - put the
   `return` after the guard.

Proposed, for pkgdx:

- A hook tool missing from PATH raises `FileNotFoundError`, now exit 70 with a bug hint. It should
   raise an `exceptions.Error` naming the tool, with a hint to activate the environment.

## Candidate patterns, not built

- `--plain`, `-q/--quiet`, `--no-input`, `-n/--dry-run`, and confirmation before destructive or
  very large actions (e.g. `dkais download --all`, ~4.2 TB)
- Per-command `examples=` - only groups have them today
- A plain `-d` log format when STDERR is not a terminal (Rich wraps it at 80 columns)
- dkais: `--start` after `--end` silently selects nothing; `download` with nothing pending still
  opens an empty progress bar
- pkgdx: `_core` reads & writes `prek.toml` with the locale encoding (the class of bug in #4); the
  `pymarkdown` hook still appends caller arguments after `scan` (#2, part b)

## Template

The copier template generates most of the original anti-patterns. Its change list is filed as
[copier-python-package#4](https://github.com/andyrids/copier-python-package/issues/4).

## Before merging

- Replace the editable `pyclig` path sources in dkais & pkgdx with `pyclig~=0.1` from PyPI.
- Close the tracking issues (dkais #6, pkgdx #6) by hand - their checklists do not link the issues.

## Round 2 - the pkgdx proposal & candidate patterns

pyclig 0.1.0 shipped first, so the ports could merge. The work below is on `feat/cli-patterns` in
pyclig (0.2.0) and on stacked branches in the consumers: dkais `fix/date-range`, then
`feat/cli-patterns`; pkgdx `fix/hook-tools`, then `feat/cli-patterns`.

| Repository | Tests | Notes |
| --- | --- | --- |
| pyclig | 111 passed, 95% coverage | 3.11, 3.13 & 3.14; mypy clean, incl. `--platform linux` |
| dkais | 124 passed | prek passes; no real `download` or `process` run |
| pkgdx | 151 passed | prek passes; `pkgdx init` ledger identical before & after |

### Built

| Item | Where | Evidence (test names) |
| --- | --- | --- |
| Missing hook tool: `error:`, exit 1 | pkgdx | `..._missing_tool_exits_1`, all 5 shims |
| Missing `git`: WARN, project root | pkgdx | `test_init_warns_..._without_git` |
| `prek.toml` read & written as UTF-8 | pkgdx | `..._set_encoding_on_non_ascii_config` |
| Non-UTF-8 TOML is a FAIL step | pkgdx | `..._fails_on_non_utf8_file` & 2 more |
| PyMarkdown global options first | pkgdx | `..._moves_global_options_before_scan` |
| `--start` after `--end`: exit 2 | dkais | `test_inverted_range_is_a_usage_error` |
| No empty progress bar | dkais | `..._skips_transfer_when_nothing_pending` |
| Per-command `examples=` | all | `test_command_help_lists_examples` |
| Plain `-d` records off a terminal | pyclig | `test_logging.py` plain-format tests |
| `pyclig.confirm` & `-f/--force` | pyclig, dkais | `..._without_terminal_needs_force` |
| `-n/--dry-run` | pyclig, dkais | `..._dry_run_stops_after_plan` |
| EOF at a prompt ends the line | pyclig | `..._aborted_after_the_prompt_line` |

Every new test failed against the code before its fix, except the subprocess import test for an
inverted range, which would have listed the real bucket.

Notes:

- PyMarkdown options move by an allow-list of its global options, checked against 0.9.41. An
  earlier rule - split at the first existing path - broke `scan`'s own options, e.g. `-r docs`.
  The short `-e` stays after `scan`, where it means `--exclude`.
- `pyclig.confirm` fails with exit 2, not 1: the remedy is a change to the command line, and a
  retrying script must not read it as a failed download.
- **Breaking (dkais):** `download --all` without a terminal on STDIN needs `--force`.

### Declined

- `--plain`: `dkais list` already prints tab-separated rows off a terminal.
- `-q/--quiet`: a flag on every command for output that is already plain when piped; `info()`
  would need the run state.
- `--no-input`: there is one prompt, and `--force` & the STDIN check cover scripts.
- pkgdx `init -n`: its steps cannot be previewed without splitting each one; `--reset` is
  explicit & `prek.toml` is tracked in Git.

### Remaining

- PyMarkdown: joined short options (`-dmd013`), `--` and argparse abbreviations stay after `scan`.
- `pyclig.confirm` outside a pyclig run raises the consoles `RuntimeError`, worded for consoles.
- With `2>log`, the confirmation prompt goes to the log.
- The Windows-console EOF case (Ctrl-Z + Enter) is unit-tested, not checked on a real console.
