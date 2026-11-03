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

## Round 3 - CLIG as a contract

Date: 3 November 2026. `docs/plan-0.3.0.md` proposed eight gaps around a `GlobalOption`; a
rule-by-rule audit of clig.dev widened it to the seven interfaces a later rule would otherwise
have had to break. 0.3.0 locks those (`feat/clig-foundation`, 13 commits) and ships the
conformance kit. The consumers were not changed: each was cloned into a scratch directory, run
unmodified on the new pyclig, then with the transition diff of its draft issue.

| Repository | Tests | Notes |
| --- | --- | --- |
| pyclig | 173 passed, 97% coverage | 3.11, 3.13 & 3.14; mypy clean, no `type: ignore` |
| dkais (scratch) | 127 on 0.2.0; 7 fail unmodified; 130 with the diff | Exactly the predicted 7 |
| pkgdx (scratch) | 237 on 0.2.0; 2 fail unmodified; 238 with the diff | Exactly the predicted 2 |

### Verdict on the plan's findings

| ID | Verdict | Evidence (`tests/test_core.py` unless named) |
| --- | --- | --- |
| F1 standalone commands | Confirmed, wider: no `-h` either | `test_standalone_command_short_help` |
| F2 no `--plain` | Partly: `is_terminal` meant "colour wanted" | `test_plain_flag_on_a_terminal` |
| F3 run-level flags | Confirmed | `test_global_option_before_or_after_command` |
| F4 hints | Partly: pkgdx `GitNotFoundError` is a WARN row | `test_mapped_error_prints_hint_last` |
| F5 `confirm` with `2>log` | Confirmed | `test_confirm_fails_without_terminal_stderr` |
| F6 third-party warnings | Confirmed; no consumer hits it | Roadmap 0.6 |
| F7 `-h` after a typo | Confirmed; snapshot the arguments | `test_help_wins_over_a_usage_error` |
| F8 nested `errors=` | Confirmed | `test_nested_errors_rejected` |

### Built in 0.3.0

| Item | Evidence (test names) |
| --- | --- |
| `FORCE_COLOR` means colour only | `test_forced_colour_streams_stay_pipes` |
| Runner, `errors=` & Ctrl-C translation on `Command` | `test_standalone_command_maps_errors` |
| `pyclig.command()`; custom help names survive | `test_custom_help_names_reach_subcommands` |
| Examples first; concise help for `no_args_is_help` | `test_command_help_lists_examples_first` |
| `hint` & `exit_code` on `errors=` types | `test_mapped_error_exit_code` |
| `GlobalOption`; an app's own spelling wins | `test_app_flag_wins_over_a_run_flag` |
| `--no-color`, `-q`, `--no-input` | `test_quiet_drops_info_and_animation` |
| Gated `prompt=` options, prompting on STDERR | `test_prompt_option_fails_instead_of_prompting` |
| `ctx.format`, `options.plain()`, `--json` wins | `test_json_wins_over_plain` |
| `pyclig.run` enters a `Context` | `test_run_enters_a_context` |
| Conformance kit, 10 rules, no callback runs | `test_probes_never_run_a_callback` |

Every test was shown failing before its change, apart from the kit's fixture tests, which could
only fail by import until the module existed.

### Integration

- Real CLIs on the overlay: `dkais list --strt 1 -h` & `pkgdx init --bogus -h` show help, exit 0;
  `FORCE_COLOR=1 dkais list --start 2026-10 | cut -f1` prints bare keys with a coloured STDERR
  (one public bucket read); `download --all` off a terminal exits 2 before any transfer, checked
  in-process with a stubbed bucket because the real command lists the bucket before the gate.
- `pkgdx init` in two throwaway projects, git's network blocked so `prek update --check` fails
  the same way on both: ledgers & `prek.toml` identical on 0.2.0 and the overlay. A hook shim with
  no `ruff` on `PATH` prints `error:` then the hint, exit 1.
- `assert_conforms`: no findings on dkais or pkgdx.
- Start-up, median of 15 (0.2.0 → overlay): `dkais --help` 148 → 150 ms, `dkais -v` 144 → 152 ms,
  `import dkais.__main__` 83 → 88 ms; `pkgdx --help` 150 → 153 ms. `import pyclig` loads
  `_flags` and neither `_conformance` nor `click.testing`.

### Departures from the notes

- The `prompt=` gate wraps `prompt_for_value` once, at command creation, instead of copying the
  option in `get_params`: identity stays stable across click's repeated `get_params` calls.
- click prompts on STDOUT; the wrapper redirects STDOUT to STDERR for the prompt's duration, so
  `prog login > file` cannot hide the question.
- `summarise` in dkais takes `plain: bool` from `ctx.format == "plain"` rather than the format
  itself, which keeps the format type out of its signature.
- A `no_args_is_help` command keeps STDERR & exit 2; only the layout became concise.

### Remaining after 0.3.0

- `-d -q` prints debug records: `-q` drops `info` lines & animation only, by design.
- A `GlobalOption` declared on a nested group is collapsed on its subcommands with a pointer to
  the root, where it is not listed.
- Run flags are not applied when parsing fails before them (`--no-color --bogus` may print red).
