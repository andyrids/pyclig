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

## Round 4 - output and feedback

Date: 4 November 2026. `docs/plan-0.4.0.md` set seven items and a C1 fix; `feat/output-feedback`
ships them in ten feature commits. A fresh agent evaluated from the plan and `git diff
76dba75...HEAD` alone. The consumers were not changed: each was cloned into a scratch directory at
its `origin/develop`, run unmodified on a wheel of the branch with only the pin overridden, and
their fit claims were sketched, not applied.

| Repository | Tests | Notes |
| --- | --- | --- |
| pyclig | 262 passed, 97% coverage | 3.11, 3.13 & 3.14; mypy clean on 3.11 & 3.14; prek clean |
| dkais (scratch, `f15b488`) | 134 on 0.3.0; 134 on the branch, 0 fail | Exactly as predicted |
| pkgdx (scratch, `d132947`) | 242 on 0.3.0; 242 on the branch, 0 fail | Exactly as predicted |
| template (scratch) | Generated `cli=True`: 5 on 0.3.0; 5 on the branch | `e19ff12`; `help` works |

### Verdict on the plan's items

| Item | Verdict | Evidence |
| --- | --- | --- |
| 1 `ctx.emit` | Confirmed by subprocess | `test_emit_plain_is_tsv_with_the_caption_on_stderr` |
| 2 `row`, `summary` | Confirmed; matches pkgdx `_row` | `test_row_pads_label_by_cell_width` |
| 3 `status`, `progress` | Partly; see defect 1 | `test_progress_descriptions_are_not_markup` |
| 4 `hint` | Confirmed | `test_hint_kept_and_info_dropped_when_quiet` |
| 5 `help` | Confirmed, every row of the table | `test_help_command_names_a_command` |
| 6 `ctx.pager` | Confirmed on a ConPTY; see defect 2 | `test_pager_is_opt_in_on_windows` |
| 7 `notice(items=)` | Confirmed from 8 threads | `test_notice_items_indented_off_a_terminal` |
| C1 fix | Confirmed | `test_messages_drop_c1_controls` |

Items 1, 5 & 6 are in `tests/test_core.py`, the rest in `tests/test_output.py`. By subprocess:
`emit | cut -f1` keeps tabs, `--json` parses, `FORCE_COLOR=1` on a pipe stays TSV and `-q` drops
the caption; 160 grouped notices from 8 threads never split; tab completion is not intercepted.

Reversion: each feature commit's tests were run with `src/` at the commit's parent. Every test
fails except those that lock an invariant: `help` yields to an app's own command, is not listed
and is not intercepted under resilient parsing (3 tests), and in the pager fix the rows that
expect `color=None`, POSIX paging and the raise-flushes case (6 cases). Those pass by design and
keep their value as guards.

### Defects found

1. `progress` task descriptions are not sanitised (`_output.py:327`): `bar.add_task("step\x1b[2J")`
   or `"step\x9b2J"` clears a real terminal, wiping the rows and notices printed before the bar
   (ConPTY, pyte screen). Every other primitive strips control codes and README says they are
   dropped from messages; the test puts `\x1b[2J` in and does not assert it is gone.
2. `Context.pager` says "`-q` never pages" (`_core.py:182`) but `prog -q cmd` pages on a terminal:
   the format stays `human`, so `less` runs (ConPTY, `PAGER=less`). Code or docstring, one must move.
3. `emit` JSON prints `NaN` and `Infinity` for non-finite floats (`_output.py:383`, `json.dumps`
   default `allow_nan=True`), which is not JSON; `jq` rejects it. No consumer row has one.

### Integration on the branch

- Real CLIs on the wheel: `dkais help list` & `pkgdx help init` print that command's help, exit 0;
  `FORCE_COLOR=1 dkais list --start 2026-10 | cut -f1` prints bare keys with a coloured STDERR
  (one public bucket read, 32 archives).
- The fallback case: pkgdx 0.7.0 from PyPI resolves with the branch wheel; `pkgdx --help`,
  `pkgdx init` in a throwaway project (3 changed, one network warning, exit 0) & `assert_conforms`
  clean. `assert_conforms` also clean on dkais & pkgdx develop.
- `import pyclig` loads none of `rich.progress`, `rich.table`, `rich.box`, `rich.live`,
  `rich.traceback`, `rich.logging`, `importlib.metadata` or `_conformance`; the only new
  module-level imports are `shlex` & `rich.pager`. `test_fast_paths_skip_heavy_imports` passes.
- Start-up, median of 15 (0.3.0 → branch): `dkais --help` 172 → 176 ms, `dkais -v` 175 → 176 ms,
  `import dkais.__main__` 156 → 154 ms, `pkgdx --help` 178 → 179 ms, `import pyclig` 127 → 134 ms.
- Pager on a Windows ConPTY: blank `PAGER` and a missing command print directly, Git's `less`
  pages and `q` returns the prompt, `-F` quits when it fits, `LESS` is unset again afterwards and
  a preset `LESS=-X` is left alone; `--json` never pages.
- Claims: every row moved to `done` in `clig-coverage.md` names behaviour that was observed;
  README & CHANGELOG match the code, except README's "control characters ... are dropped from
  messages" for `progress`; the shipped signatures match the plan; `Requires-Dist` is still
  `click~=8.5` & `rich~=15.0`.

### Departures from the plan

- `grp help leaf` runs the root callback only; `grp leaf --help` also runs `grp`'s. The table
  speaks of the root callback, so it holds, narrowly.
- The `emit` fit for dkais `list` is byte-identical for JSON, plain rows & the caption; an empty
  listing in `human` moves the caption from an empty table on STDOUT to STDERR, and a `None` cell
  prints blank where `_tsv` prints `None`.
- The `row` fit for pkgdx `_row` is byte-identical with a detail; without one the trailing padding
  goes. pkgdx's `quiet` skip of OK rows maps to `essential=`.
- The tree versions as `0.2.1.dev39`: `v0.3.0` is not an ancestor of the branch. The wheel was
  built with `SETUPTOOLS_SCM_PRETEND_VERSION=0.4.0`.

### Remaining after 0.4.0

- `PYTHONIOENCODING=` set but empty counts as explicit (`_run.py:143`), so the streams stay
  cp1252 where Python itself would ignore it. Pre-existing.
- On Windows a STDOUT redirected to `NUL` reports as a terminal, so `prog > NUL` picks `human`.
  Pre-existing `isatty`.
- Inside `ctx.pager()` on a `TTY_COMPATIBLE=1` pipe with a `PAGER` other than `less`, click strips
  the colour that `FORCE_COLOR` keeps outside the block.
- Not verified this round: `less` on POSIX (the P6 record covers WSL) and tab completion through
  a real shell (the unit test covers resilient parsing).

### Fixed after evaluation

1. `progress` sanitises its description column & `str` columns (`PlainColumn`, `_output.py`):
   `test_progress_descriptions_print_literally` asserts `\x1b[2J` & `\x9b2J` are gone, for both.
   A caller's own `ProgressColumn` renders as built; the docstring & README say so.
2. `Context.pager` docstring corrected: `-q` marks STDERR only, so a `human` run still pages.
   Behaviour unchanged, no test.
3. `emit` dumps JSON with `allow_nan=False`, so a NaN or infinity is a bug (exit 70) instead of
   invalid JSON on STDOUT: `test_emit_json_refuses_nan`.

## Round 5 - configuration and environment

Date: 6 November 2026. `docs/plan-0.5.0.md` set seven items; `feat/config-env` ships them in
eight feature commits (`d8ed44b` to `6a88b0b`), a test commit and the docs. A fresh agent
evaluated from the plan, `CLAUDE.md` and `git diff 617b548...HEAD` alone, on a wheel of the
branch (`SETUPTOOLS_SCM_PRETEND_VERSION_FOR_PYCLIG=0.5.0`). Consumers were not changed: each was
cloned into a scratch directory at its `develop` (the template from GitHub), run unmodified with
only the pyclig pin overridden, and the P3 fit was applied to the pkgdx scratch clone only.

| Repository | Tests | Notes |
| --- | --- | --- |
| pyclig | 360 passed, 97% coverage | 3.11, 3.13 & 3.14; mypy clean on 3.11 & 3.14; prek clean |
| pyclig, `NO_COLOR=1` | 360 passed | The developer-environment case from the P4 record |
| dkais (scratch, `b6c846b`) | 134 on 0.4.0; 134 on the branch, 0 fail | Exactly as predicted |
| pkgdx (scratch, `a041464`) | 242 on 0.4.0; 242 on the branch, 0 fail | Exactly as predicted |
| pkgdx, P3 sketch | `test_standards_config.py`: 55 passed | `paths.config_dir("pkgdx")` |
| template (scratch, `62fae4b`) | Generated `cli=True`: 5 on 0.4.0; 5 on the branch | `help` works |

### Verdict on the 0.5.0 items

| Item | Verdict | Evidence |
| --- | --- | --- |
| 1 `paths` | Confirmed on Windows & WSL (Linux) | `test_system_config_dirs_takes_first_absolute` |
| 2 value `GlobalOption` | Confirmed: flag, env, `.env`, file | `test_global_option_is_flag_rules` |
| 3 `Config` | Confirmed, every row of both tables; defects 1-4 | `test_precedence_matrix` |
| 4 `.env` | Confirmed | `test_dotenv_below_the_environment_above_the_files` |
| 5 `secret` | Confirmed, `<(...)` & a WSL pty included | `test_secret_refuses_a_terminal_stdin` |
| 6 `<PROG>_DEBUG`, `_NO_COLOR` | Confirmed; bold stays | `test_run_honours_debug_variable` |
| 7 `-o`, `-p`, `-u` | Confirmed; kit clean | `test_kit_is_clean_on_every_factory` |

Items 3 & 4 are in `tests/test_config.py`, 1 in `test_paths.py`, 2 in `test_core.py`, 5 & 7 in
`test_options.py` and 6 in `test_logging.py`. By subprocess, with a test package `evalcli`
(`Config(profiles=True, dotenv=True)`, a value `--region`, `show` with `--name`, `--tag`
`multiple=True`, `--level`, a nested `sub leaf`) and temporary `APPDATA`, `ProgramData` and XDG
directories: with a system, a user and a project file the system `region` & `tag` list, the user
`level` and the project `name` all arrive, and flag > env > `.env` > profile (project, user,
system) > project > user > system holds for every pair; `--profile` before or after the
subcommand, or `EVALCLI_PROFILE`, selects `[profiles.NAME.show]`; `--config` replaces all three
files; `--config pyproject.toml` with `table="tool.evalcli"` selects the table and `other.toml`
is read whole; `prog sub --config f` fills `sub` & `sub leaf`; bad TOML exits 1 naming the file;
a missing or directory `--config` exits 2; an unknown profile exits 2 naming the files, or
`no config file found`; `--help`, `sub --help`, `sub leaf --help`, `-v` & `_CLI_COMPLETE` exit 0
with a broken project file; `EVALCLI_DEBUG=1` logs `loaded config` during parsing before a
`--bogus` usage error, `0`, `false`, `NO`, `off` & empty do not, ` 1 ` & `yes` do; `.env`
accepts `export`, quotes & trailing comments, warns `.env:7: not KEY=VALUE, ignored`, skips
`EVALCLI_TOKEN` (logged at debug), fills `--tag` with `"t1 t2"` split in two, loses to the real
environment and to a flag, and a child `python -c` sees no `EVALCLI_NAME`; `--token-file -`
receives `s3cret` from `printf 's3cret\n' |`, with `\r\n`, without a newline, and keeps a second
newline; a file, `<(printf ...)` on WSL, an empty secret (2), a missing file (2), a directory (2),
`required=True` missing (2) and STDIN a pty under `script` (2, `STDIN is a terminal - pipe the
secret in`) all behave. `-o -` is accepted, `-p 70000` exits 2, `-u` reads its `envvar=`.

Reversion: each feature commit's added tests were run with `src/` at the commit's parent (files
the commit added removed). Every test fails except the invariant guards: `d8ed44b` 6 of 9 - the
falsy-value and `-d`-after-variable tests pass without the feature; `80707cd` 4 of 5 -
`test_dotenv_is_opt_in` passes by design. `319e4b0` 6 of 6 and `7454264` 1 of 1 fail; for
`e3704c6`, `56b8b70`, `030e40b` & `6a88b0b` the test module cannot import (`paths`, `Config`,
`options.secret`, `options.output`), so all 8, 23, 5 & 4 fail at collection.

### Defects found in 0.5.0

1. The help look-ahead (`_config.py:216-218`) treats any remaining `--help` or `-h` argument as a
   help request, so `prog show --name --help` (the option's value), `prog show -- --help` (a
   positional) and `prog --config f show -- --help` run the command with no file read:
   `name=--help ... files=[]`, and the explicit `--config` is silently ignored.
2. `prog --config broken.toml --help` exits 1 with `error: cannot read config ...`: click
   processes the eager options that were given in command-line order, so `ConfigOption`'s
   `handle_parse_result` runs before `--help`'s callback, and `--help` is then in `opts`, not in
   `args`, where the look-ahead searches. `prog --help --config broken.toml` exits 0. README
   (`:182-183`) and `_config.py:24` say `--help` reads no file;
   `test_help_version_and_completion_read_no_file` only puts `--help` first.
3. `prog help show` with a broken project file exits 1: the `help` command is resolved in
   `Group.resolve_command` (`_core.py:801-807`), after the root's parameters, config included,
   are processed. `prog show --help` prints the help.
4. A `--profile` given after the subcommand replays the main tables over the root's profile
   (`_config.py:283-289`): `prog --profile alpha show --profile beta` prints `name=project`, not
   alpha's `proj-alpha` from the project file's `[profiles.alpha.show]`, while alpha's root key
   `region=user-alpha` survives. Two profiles in one run only.
5. `state.config_files` is overwritten by a subcommand's `--config` (`_config.py:279`):
   `prog show --config f` records `[f]` while the root read three files; the `-d` log shows four.

### Integration on `feat/config-env`

- Real CLIs on the wheel: `DKAIS_DEBUG=1 dkais --help` prints the help, exit 0;
  `PKGDX_DEBUG=1 pkgdx-format-hook <file>` logs `[resolve_config] Using bundled config ...` at
  DEBUG and `1 file left unchanged`, without the variable the latter only; `assert_conforms`
  clean on dkais & pkgdx develop; dkais `test_fast_paths_skip_heavy_imports` 6 passed.
- The fallback case: pkgdx 0.7.0 from PyPI resolves with the branch wheel; `pkgdx --help` exit 0,
  `PKGDX_DEBUG=1 pkgdx init` in a throwaway project logs `create_secrets_baseline` (3 changed,
  one network warning, exit 0) & `assert_conforms` clean.
- PyPI, re-checked: pkgdx 0.7.0 requires `pyclig~=0.2`, 0.8.0 `pyclig~=0.3.0`, 0.9.0
  `pyclig~=0.4.0`. The plan's order - pkgdx, template, dkais - holds. Issues drafted, not filed.
- `import pyclig` adds `pyclig._config` & `pyclig.paths` only (178 to 180 modules) and none of
  `tomllib`, `rich.traceback`, `rich.logging`, `rich.progress`, `rich.table`,
  `importlib.metadata` or `_conformance`. After `--help` of the config CLI none of those is
  loaded, after `-v` only `importlib.metadata`, after `show` `tomllib`. `Requires-Dist` is still
  `click~=8.5` & `rich~=15.0`. The three paths functions, pointed at absent parents, create
  nothing.
- Start-up, median of 15, two runs (0.4.0 to branch): `dkais --help` 190 to 223 & 208 to 216 ms,
  `dkais -v` 251 to 218 & 221 to 206, `import dkais.__main__` 178 to 208 & 180 to 217,
  `import pyclig` 145 to 163 & 197 to 171. The run-to-run spread (about 30 ms) exceeds any
  difference; pkgdx 0.7.0 `--help` 260-296 ms against develop 200-217.
- Claims: every row moved to `done` in `clig-coverage.md` names behaviour that was observed;
  CHANGELOG matches the code and dates 0.4.0; the shipped signatures match the plan. README is
  right except the sentence that a broken file "never hides the help" (defects 2 & 3).

### Departures from the 0.5.0 plan

- `--profile` or `--config` after the subcommand applies to that command and below only:
  `prog show --profile alpha` leaves the root's `region` at the main tables' `sys`, where
  `prog --profile alpha show` gives `user-alpha`. Documented for `--config`; "either order" holds
  for the subcommand's own table.
- An environment variable set but empty (`EVALCLI_NAME=`) is filled from `.env`: click's
  `resolve_envvar_value` treats an empty value as unset, so `.env` follows click, not "set".
- `<PROG>_NO_COLOR=1 FORCE_COLOR=1` prints `\x1b[1merror:\x1b[0m` - colour gone, bold kept - on
  Windows and on a WSL pty, as `--no-color` and Rich's `no_color` do (README `:91`).
- `--config PyProject.toml` on Windows is read whole: the name match (`_config.py:264`) is
  case-sensitive where the file system is not.
- The tree versions as `v0.2.0-60-g2f2b9a3`; the wheel was built with the pretend version.
- From Git Bash `PROGRAMDATA=x` never reaches Python: MSYS exports both spellings and
  `os.environ` keeps the inherited `ProgramData`. `ProgramData=x` works, as does PowerShell. Not
  pyclig's, and `tests/test_paths.py` patches `os.environ` directly.

### Remaining after 0.5.0

- Under Git Bash `</dev/null` is `NUL`, which reports as a terminal, so `--token-file -` says
  `STDIN is a terminal` where WSL says `the secret is empty`. Pre-existing `isatty` (Round 4).
- `prog show -v` is a usage error: `-v` stays root-only, as in 0.4.
- Not verified this round: macOS, and `-X importtime` on 3.11 (3.13 was used).

### Fixed after evaluation (0.5.0)

Five fix commits, `1cfe92a` to `0e9d690`, re-checked by the same subprocess CLI on a rebuilt
wheel. The help look-ahead went: a `ConfigError` is kept on `State.config_error` and raised in
`Context.invoke` (`_core.py:116-118`) before any callback, and `Group.invoke` (`:763-776`)
first resolves and parses the subcommand so its `--help` answers.

1. `prog show --name --help`, `prog show -- --help` & `prog --config f show -- --help` now apply
   the files (`files=[...]`, `region=explicit`): `test_help_as_a_value_does_not_skip_config`.
2. `prog --config broken.toml --help` exits 0, as do `--help`, `show --help`, `sub --help`, `-v`
   & completion with a broken project file; a run still exits 1:
   `test_help_paths_exit_0_with_a_broken_file`.
3. `prog help show` & `prog help sub leaf` exit 0 with a broken file: same test.
4. Redefined rather than restored: a `--profile` at a subcommand layers over the application's
   own `default_map` (`_config.py:300-310`, `BASE_KEY`), so `prog --profile alpha show --profile
   beta` still prints `name=project` - beta replaces alpha for `show`, alpha keeps the root's
   `region=user-alpha`: `test_profile_at_a_subcommand_layers_like_the_root`. One profile per
   level is now the rule.
5. `prog show --config f` records all four files: `test_config_files_records_every_file_applied`.

Side effects under a deferred error were checked once each: in the normal case the subcommand
is parsed once and every callback runs once (`--trace`, a value `--region`, an `envvar=`
callback, the root callback); with a broken file the subcommand's option callbacks run once in
the pre-parse, the root callback never runs, `--token-file -` consumes STDIN once and the run
exits 1 (`test_config_error_precedes_every_callback`). A usage error found in the pre-parse
(`show --bogus`, 2) wins over the config error (1), which is fine. Bare `prog` with a broken file
exits 1 with the error instead of concise help - unchanged from the evaluated tree, consistent
with "no application code runs on defaults that miss the config" (the root callback runs before
the concise help), and the plan's table names `--help`, `-v` & completion only. Acceptable.

New in the fixes:

- Defect 6: `prog sub leaf --help` with a broken file exits 1 on Windows & WSL: the pre-parse in
  `Group.invoke` (`_core.py:771-775`) resolves one level, so a nested group's `leaf --help` sits
  in `sub`'s protected arguments when the error is raised. `prog sub --help` & `prog help sub
  leaf` exit 0. Before the fixes the look-ahead gave 0.
- Defect 7: A `prompt=True` option is asked before the deferred error (WSL pty: `Answer:` then
  `error: aborted` on EOF): the pre-parse prompts for a value the run will never use.
  `options.secret` reading a file or STDIN behaves the same way, harmlessly.

Consumers on the rebuilt wheel, unmodified: dkais 134 passed, pkgdx 242 passed, the generated
`cli=True` project 5 passed & `evaltool help` exit 0.

Every commit from `78fb383` to `0e9d690` was tested on its own tree, installed from a scratch
worktree into a venv holding only click, rich & pytest (an environment with the main repo's
editable install contaminates the subprocess tests, which build a clean `env=`). All 18 pass
except `b851998`: 2 failed, `test_help_paths_exit_0_with_a_broken_file[sub-help]` &
`test_config_error_precedes_every_callback`, green again at `0e9d690`. For a bisect, treat
`b851998` as a known-red commit. The gate at `0e9d690`: 370 passed, mypy clean, 97% coverage.

Re-checked after `c4cadd5`, which replaced the pre-parse: while a config error is pending a group
that is descending to a subcommand skips its callback, the first callback that would run raises,
and a prompt raises instead of prompting. On a rebuilt wheel, by subprocess:

- Defect 6 fixed: `prog sub leaf --help` & `prog help sub leaf` exit 0 with a broken file on
  Windows & WSL, as do `--help`, `show --help`, `sub --help`, `iwc --help`, `-v` &
  `--config bad.toml --help`: `test_help_paths_exit_0_with_a_broken_file[nested-help]`.
- Defect 7 fixed: on a WSL pty `prog ask` prints the config error with no `Answer:` prompt; a
  piped STDIN gives the same: `test_config_error_precedes_every_callback` (the `ask` case).
- Defects 1-5 still hold (same repros, same output). A broken run exits 1 with the root `--trace`
  callback run once and no root, `sub` or leaf callback; `--token-file -` consumes nothing the
  run would reuse. An `invoke_without_command=True` group with a broken file exits 1, callback
  not run, and its `--help` exits 0. Normal runs are unchanged: root, `sub` & leaf callbacks run
  once each in order, `iwc` runs its callback, the prompt is asked once on a pty.
- Gate at `c4cadd5`: 371 passed, mypy clean. Consumers on the rebuilt wheel, unmodified: dkais 134
  passed, pkgdx 242 passed, the generated `cli=True` project 5 passed & `evaltool help` exit 0.

## Round 6 - robustness and signals

Date: 8 November 2026. `docs/plan-0.6.0.md` set seven items; `feat/robustness-signals` ships them
in seven feature commits (`dcfeb3b` to `7e6dfc4`), two spike and result notes and the docs
(`c578e65`). A fresh agent evaluated from the plan, `CLAUDE.md` and `git diff 69ae9ed...HEAD`
alone, on a wheel of the branch (`SETUPTOOLS_SCM_PRETEND_VERSION=0.6.0`) installed into venvs
holding only each consumer's own dependencies, with the pyclig pin overridden to the wheel.
Consumers were cloned into a scratch directory and run unmodified.

| Repository | Tests | Notes |
| --- | --- | --- |
| pyclig | 445 passed, 3 skipped, 97% | 3.11, 3.13 & 3.14; mypy 3.11 & 3.14 clean; prek clean |
| dkais (scratch, `28feab9`) | 134 on 0.5.0; 134 on the wheel, 0 fail | As predicted; `develop` |
| pkgdx (scratch, `f0ce0d5`) | 242 on 0.5.0; 242 on the wheel, 0 fail | As predicted; `main` (1) |
| template (`76eb5b9`), generated `cli=True` | 5 on the wheel | `evaltool help` exit 0 |
| pkgdx 0.7.0 from PyPI on the wheel | `pkgdx --help` exit 0; kit clean | The fallback case |

1. With `ruff` & `mypy` off `PATH`, 14 `test_standards_hooks.py` tests fail identically on 0.5.0
   and on the wheel (`ToolNotFoundError`): the environment, not pyclig.

### Verdict on the 0.6.0 items

| Item | Verdict | Evidence |
| --- | --- | --- |
| 1 signals | Confirmed: Windows 3.11, 3.14 & WSL | `test_notice_is_printed_before_unwinding` |
| 2 `ctx.cleanup` | Confirmed, all six rows | `test_cleanup_second_signal_skips_the_block` |
| 3 root & warnings | Confirmed | `test_third_party_warning_prints_message_only` |
| 4 `_LOG_FILE` | Confirmed; defects 1 & 2 | `test_log_file_gets_crash_traceback` |
| 5 `logs_on_failure` | Confirmed, pty `Progress` too | `test_held_logs_replayed_before_error` |
| 6 `confirm_name` | Confirmed, every row, pty too | `test_confirm_name_typed_otherwise_aborts` |
| 7 `options.timeout` | Confirmed; kit clean | `test_timeout_rejects_non_positive` |

Items 1 & 2 are in `tests/test_signals.py`, 3-5 in `test_logging.py`, 6 in `test_core.py` and 7
in `test_options.py`.

Signals, by real subprocess: a `pyclig.command` polling `time.sleep(0.05)`, then on
`KeyboardInterrupt` a `ctx.cleanup(timeout=T)` block that sleeps 0.3 s or sticks in
`Event.wait`, `Thread.join` or `socket.recv`; Windows 3.11 & 3.14 children in a new process
group sent `CTRL_BREAK_EVENT`, WSL (Python 3.14) children sent SIGINT and SIGTERM. In every run
`warning: interrupted` came first, at +47-53 ms on Windows (the poll) and +1 ms on WSL, then
`cleaning up - press Ctrl-C again to skip`, then the block's first line; exit 130. A second signal
exited 10-14 ms (Windows) and 4-8 ms (WSL) after it with `warning: clean-up skipped`, for all
three stuck blocks. A 0.5 s timeout fired at 561-574 ms (Windows) and 503-504 ms (WSL), `warning:
clean-up timed out after 0.5s`, also for a nested outer `0.5` with an inner `timeout=None`. A
signal landing inside a block on the normal path printed the notice and hint at +2-4 ms, let the
block finish (1.9 s) and exited 130; a second one there skipped in 8-13 ms. On WSL SIGTERM gave
`warning: terminated`, the hint `cleaning up`, and 143 on the plain, skip and timeout paths.
`pyclig.run` on WSL: 130 and 143 within 15 ms. Windows `os.kill(pid, SIGTERM)`: exit 15, no
output, as documented. Ctrl-C at a `confirm` prompt on a WSL pty: `Proceed? [y/N]:` then one
`warning: interrupted` line, 130. A manual Ctrl-C in Windows Terminal and in WSL was not done: an
agent cannot drive a console, so the transcripts are left to the maintainer.

Logs, by subprocess on Windows 3.14 (package `cli`): inside `logs_on_failure` a `RuntimeError`
prints `step 1`, `step 2` before the traceback and `error: unexpected RuntimeError: boom` (70);
success, `Abort` (1) and `ctx.exit(0)` print none; a `UsageError` replays (it is an `Exception`);
`-d` prints every record live with no duplicate; `-q` hides the replay; `level=DEBUG` holds debug
lines too; a `warning` inside prints at once, before the replay. On a WSL pty (`script`) with a
`Progress` on `ctx.err` inside the block the bar frames end, then `warning: live warning`, the
replayed `step 0`-`step 3`, the traceback and `error:` - nothing drawn over.

Root and warnings: a `warnings.warn(UserWarning)` prints `warning: Unverified HTTPS request is
being made` with no path; `-d` prints `WARNING  [UserWarning] ...  logcli.py:17`; a
`urllib3.connectionpool` WARNING prints as a notice and its INFO does not; `-q` keeps both. With
`logging.basicConfig` first, the output is byte-for-byte the pre-0.6 one: the default
`file:line: UserWarning:` pair and `BASIC WARNING ...` lines, under `-d` too. Pkgdx's caplog tests
are among its 242.

`<PROG>_LOG_FILE`: `CLI_LOG_FILE=run.log` gets `DEBUG` and `INFO` records from a run without
`-d`, appends across runs, gets the root's `[UserWarning]` and `urllib3` records, and on exit 70
the traceback after `ERROR    [None] unexpected ValueError  _logging.py:0`, with the hint
`debug log: C:\...\run.log` (absolute). A missing directory warns `cannot write the debug log to
...: No such file or directory`, exit 0; a blank value is ignored.

Import and run state: `-X importtime` on 3.11 and 3.14 shows `import pyclig` adding
`pyclig._signals` and none of `socket`, `select`, `rich.traceback`, `rich.logging`,
`importlib.metadata` or `_conformance`; `--help` adds none of them, `-v` only
`importlib.metadata`, a run without `ctx.cleanup` none. `Requires-Dist` is still `click~=8.5` &
`rich~=15.0`. After five in-process `invoke` runs (plain, `-d`, with `LOG_FILE`, a crash with
`LOG_FILE`, and `raise_signal(SIGINT)` inside `ctx.cleanup`, exit 130) the SIGINT, SIGTERM and
SIGBREAK handlers, the wakeup fd (-1), `showwarning`, the root handlers (none) and level, and the
package logger's level, handlers and propagation are all as before.

Reversion: each feature commit's tests were run with `src/` at the commit's parent (files the
commit added removed). `dcfeb3b` and `19696f7` fail at collection (`confirm_name`,
`options.timeout`). `4e3ead0`: `raise_signal(SIGTERM)` with `SIG_DFL` kills pytest at
`test_signal_notice_and_exit_code[sigterm]` after one pass, exit 3. `089b82b`: 18 of 20 - 11
error on the `exits` fixture (`_signals._exit`) and 7 subprocess tests fail. `9531a35`: 5 of 7 -
`test_root_and_showwarning_restored_after_runs` and `test_configured_root_left_alone` pass
without the feature by design. `3ebd4e6`: 7 of 8 - `test_log_file_variable_cleared_by_invoke`
passes by design. `7e6dfc4`: 8 of 11 - the three `test_held_logs_state_restored` cases pass by
design.

### Defects found in 0.6.0

1. `assert_conforms` inherits the developer's `<PROG>_LOG_FILE`: the kit clears only `_CLEARED`
   (`_conformance.py:53`, `:198`), where `testing.invoke` also clears `_PREFIXED`
   (`testing.py:48`, `:120`). With `EVALTOOL_LOG_FILE=.../nodir/x.log` the generated project's
   `test_conforms` fails with `2 CLIG findings`: `HELP-1 evaltool -h exits 0, printing to STDERR`
   and the same for `--help`, from `warning: cannot write the debug log to ...`; a writable path
   is opened (created) by every probe. The P3 note that the kit "never learns `<PROG>`" does not
   hold: the probe has the command's name as `path`.
2. `log_failure` (`_logging.py:196-214`) builds the crash record with `__file__`, line 0 and no
   function, so the file reads `ERROR    [None] unexpected ValueError  _logging.py:0`. Cosmetic;
   the traceback below it is complete.
3. `_signals.cleanup` (`_signals.py:131-133`) calls `watcher.stop()`, which closes the pipe or
   socket pair, before it sets `state.watcher = None`; a signal in that window makes the handler
   (`:329-333`) call `notify` on a closed end and raise `OSError` out of the handler. A window of
   microseconds, found by reading, not reproduced.

### Integration on `feat/robustness-signals`

- Real CLIs on the wheel: `dkais download --start 2026-10 --end 2026-10 --data-dir X --dry-run`
  prints `31 archives to download · 19.3 GB · 0 already present`, exit 0, with no `warning:`
  line, on 0.5.0 and on the wheel alike: no third-party warning became visible in a dry run.
  `assert_conforms` clean on dkais & pkgdx; dkais `test_fast_paths_skip_heavy_imports` 6 passed.
- The fallback case: pkgdx 0.7.0 from PyPI resolves with the wheel; `pkgdx --help` exit 0 with
  empty STDERR & `assert_conforms` clean.
- PyPI, re-checked: pkgdx 0.7.0 requires `pyclig~=0.2`, 0.8.0 `~=0.3.0`, 0.9.0 `~=0.4.0`, 0.10.0
  `~=0.5.0`; 0.10.0 is the latest and pyclig's is 0.5.0. The plan's order - pkgdx, template,
  dkais, cotravel - holds. Issues drafted, not filed.
- Start-up, median of 15 (0.5.0 to branch): `dkais --help` 216 to 209 ms, `dkais -v` 208 to 210,
  `import dkais.__main__` 188 to 182, `import pyclig` 151 to 150 in the dkais venvs and 143 to
  147 in bare ones (`python -c pass` 59-60). Within the run-to-run spread.
- Claims: every row moved to `done` in `clig-coverage.md` names behaviour that was observed;
  CHANGELOG matches the code and dates 0.5.0; README's exit-code, clean-up and confirmation
  tables match the output above, and its pin reads `pyclig~=0.6.0`.
- Every prediction in the plan held: 0 consumer failures, kit clean, `test_fast_paths` passes,
  `test_main` passes, pkgdx 0.7.0 runs. None missed.

### Departures from the 0.6.0 plan

- A fourth `State` field, `watcher`, plus `log_file` (`_run.py:114-118`).
- A foreign wakeup fd is left in place (`Watcher.start`, `_signals.py:180-187`) and the Python
  handler forwards the signal to the watcher; `test_cleanup_foreign_wakeup_fd_is_restored`.
- Windows test children poll `recv` with a 0.1 s timeout; this round's probe polled `sleep`.
- An interrupt while the runner reports is caught in `_run.execute` (`_run.py:385-388`).
- `showwarning` with an explicit `file` writes `formatwarning` there (`_logging.py:383-387`).
- Under `-d` a warning's `[funcName]` is its category, e.g. `[UserWarning]`.
- `<PROG>_LOG_FILE` is not in the kit's `_CLEARED`: defect 1.
- The exit-70 hint shows the absolute path (`FileHandler.baseFilename`).
- No helper thread prints the first notice; the spike found `Console._lock` an `RLock`.
- `confirm_name` prompts `MESSAGE Type 'NAME' to confirm:` on STDERR, the message first.
- A `UsageError` leaving `logs_on_failure` replays the held lines; the plan names `Exception`.

### Remaining after 0.6.0

- The manual Ctrl-C transcripts in Windows Terminal and WSL (plan step 2).
- INT-5 stays `partial`: on Windows the notice waits for the main thread's blocking call, and a
  plain `recv` never sees Ctrl-Break (the spike). The probe's 50 ms is its poll, not pyclig.
- Not verified this round: macOS, and the subprocess matrix on 3.13 (3.11 & 3.14 were run).
- pkgdx's own "interrupted" line (`standards/_cli.py:245-250`) will now follow pyclig's notice; a
  pkgdx adoption PR, not a pyclig defect.

### Fixed after evaluation (0.6.0)

Three fix commits, `0cbae09`, `aec1596` & `81751d2`, re-checked by the same probes on a rebuilt
wheel (`SETUPTOOLS_SCM_PRETEND_VERSION=0.6.0`) reinstalled into every venv above.

1. The kit now clears the run's own variables: `_run.cleared(callback, path)` (`_run.py:144-159`)
   prefixes `RUN_VARIABLES` (`DEBUG`, `NO_COLOR`, `CONFIG`, `PROFILE`, `LOG_FILE`) with the same
   `package_of` + `prefix_of` that `Command.main` and `pyclig.run` use, and both `_probe`
   (`_conformance.py:198-200`) and `testing.invoke` (`testing.py:117-119`) take it. On the
   generated project `test_main.py` passes 3 of 3 with `EVALTOOL_LOG_FILE` unwritable, with it
   writable and no file created, with `EVALTOOL_DEBUG=1`, and with all three plus
   `EVALTOOL_NO_COLOR=1`: `test_run_variables_cleared`.
2. `log_failure` walks to the innermost traceback frame (`_logging.py:208-215`): the file now
   reads `ERROR    [crash] unexpected ValueError  logcli.py:88`, and a failure inside
   `logs_on_failure` `ERROR    [held] unexpected RuntimeError  logcli.py:38`:
   `test_log_file_gets_crash_traceback`.
3. `cleanup` sets `state.watcher = None` before `watcher.stop()` (`_signals.py:131-133`), and
   `notify` returns False on a closed end so the handler takes the plain path (`:204-214`,
   `:348-350`): `test_cleanup_detaches_the_watcher_before_stopping` &
   `test_signal_to_a_stopped_watcher_takes_the_plain_path`. Reviewed, not reproduced, as before.

Each fix's new or changed tests fail with `src/` at the fix's parent: `test_run_variables_cleared`
with `[Finding(rule... printing to STDERR')] == []`, `test_log_file_gets_crash_traceback` with
`[None] ... _logging.py:0`, and both signal tests.

Gate at `81751d2`: 448 passed, 3 skipped on 3.11 & 3.14; mypy clean on both; prek clean; 97%
coverage. Signals on the rebuilt wheel, Windows 3.11 & 3.14 and WSL: notice at +47-52 ms
(Windows) and +1 ms (WSL); the second signal exits 11-13 ms (Windows) and 3-8 ms (WSL) after it
with `clean-up skipped`; the 0.5 s timeout at 562-568 ms and 503-505 ms; SIGTERM on WSL 143 on
the plain, skip and timeout paths; `os.kill(SIGTERM)` on Windows 15. Consumers on the rebuilt
wheel, unmodified: dkais 134 passed, pkgdx 242 passed, the generated `cli=True` project 5 passed &
`evaltool help` exit 0.

New in the fixes: none. One residual, noted and not a defect: a signal landing between the
detach and `watcher.stop()` with `state.signal` already set raises `KeyboardInterrupt` out of
the `finally`, so `stop` is skipped; the run exits 130 at once, and only an in-process runner
would keep the daemon thread and its wakeup fd until the process ends. A window of microseconds.

## Round 7 - closing the rows

Date: 11 November 2026. `docs/plan-0.7.0.md` set eight items to close every row of
`docs/clig-coverage.md` that was neither `done` nor owned `out`; `feat/close-rows` ships them in
16 feature & fix commits (`6e00805` to `4608fd7`), three evidence-only test commits and the docs
(`a43fb11`). Two Fable 5.2 implementers worked one phase per message (A: P1-P3, about 173k
tokens; B: P4-P8, about 271k), and the mediator reviewed each phase's diff and re-ran the gate
before the next. Consumers ran unmodified in scratch clones on a wheel of the branch
(`SETUPTOOLS_SCM_PRETEND_VERSION=0.7.0`), first on their locked 0.6.0.

| Repository | Tests | Notes |
| --- | --- | --- |
| pyclig | 556 passed, 15 skipped, 97% | 3.11, 3.13 & 3.14 after fix 1; mypy & prek clean |
| pyclig on WSL (Linux, 3.14) | 567 passed, 4 skipped | Native filesystem, installed |
| pkgdx (scratch, `4e6920b`) | 242 on 0.6.0; 242 on the wheel | As predicted: no findings |
| dkais (scratch, `e15e060`) | 147 on 0.6.0; 146 on the wheel, 1 fail | As predicted (1) |
| template, generated `cli=True` | 5 on 0.6.0; 5 on the wheel | As predicted: no findings |
| pkgdx 0.7.0 from PyPI on the wheel | `--help` & `help init` exit 0 | Kit clean: the fallback case |

1. `test_cli_conforms_to_the_guidelines`: `ARG-3 dkais download` for `-j` (`--jobs`), the one
   finding the plan predicted.

### Verdict on the 0.7.0 items

| Item | Verdict | Evidence |
| --- | --- | --- |
| 1 static kit rules | Confirmed; S1 exact | `test_conformance.py`, fixture `lax` |
| 2 `samples=` | Confirmed | `test_conformance.py` sample tests |
| 3 robustness | Confirmed; S3 by hand | `test_hostile_environment_changes_nothing` |
| 4 arguments | Confirmed | `test_deprecated_use_warns_on_stderr` |
| 5 help content | Confirmed after a perf fix | `test_root_help_of_an_installed_app_...` |
| 6 help style | Confirmed; S6 by hand | `test_help_bold_follows_the_real_console` |
| 7 bug report URL | Confirmed; defect 1 | `test_bug_report_url_carries_nothing_private` |
| 8 docs | Confirmed: no row left open | 145 rows, each `done*` or owned `out` |

Reversion: for each of the 16 commits that change `src/`, its tests ran with `src/` at the
commit's parent. Every commit has failing tests; `NoneOr` and `docs=` fail at import. New tests
that pass at the parent are guards by design: real consoles & descriptor-less streams stay
terminals, `-v` under resilient parsing, a piped STDIN or a named file is read, `(DEPRECATED)` in
help, no or many options in concise help, single-line examples unchanged, the `importlib`
fallback, plain help without styling, an unstyled usage block, and a URL with nothing private.

Design rules:

- Public signatures against 0.6.0 (`inspect.signature` over `pyclig`, `options`, `testing`,
  `paths` & the classes): nothing removed or changed but for new keyword-only `docs=`,
  `samples=` & `err=`, plus `options.NoneOr`.
- `import pyclig` loads none of `importlib.metadata`, `rich.traceback`, `rich.logging`,
  `_conformance`, `socket`, `urllib.parse` or `platform`. `ctypes` loads, as on 0.6.0, through
  `rich.console`.
- Runtime dependencies are unchanged.

Start-up, median of 15 (0.6.0 → wheel): `pkgdx --help` 163 → 153 ms, `pkgdx -v` 154 → 152 ms,
`dkais --help` 158 → 153 ms, `dkais -v` 151 → 144 ms, `import pyclig` 118-120 ms on both. Within
noise. Before the P5 follow-up, root `--help` of an installed app cost +20 ms
(`importlib.metadata` for the `Issues` line), which broke the plan's +10 ms block; `54f6463`
reads `METADATA` directly and brought it back to the pre-feature 147-149 ms.

By hand (S3, 11 November): Ctrl-C during `recv` inside `ctx.cleanup(timeout=3)` in Windows
Terminal & WSL said so at once and exited 130 at the timeout, a second Ctrl-C skipped the block;
`> NUL` picked `plain`; Git Bash `</dev/null` reported an empty secret, exit 2. S6, the same
day: help headings & `USAGE:` bold in Windows Terminal & WSL, kept with `--no-color`; plain through
`| more`, a file, `| cat -v` & `TERM=dumb`; a usage error's `USAGE:` block plain; `LINES=7` gave a
height of 7.

### Defects found in 0.7.0

1. On Python 3.11, `test_import_has_no_side_effects` and
   `test_root_help_of_an_installed_app_skips_importlib_metadata` failed: 3.11's `pathlib` imports
   `urllib.parse` itself, so the new forbidden sets were wrong there. A test defect, not an
   import by pyclig.
2. Nit: CHANGELOG listed the `METADATA` fast path under `Fixed`, though it is the implementation
   of an unreleased feature.

### Departures from the 0.7.0 plan

- ARG-1, ARG-5, SUB-4 & SUB-5 are static; `samples=` serves BAS-4, BAS-5 & ERR-2, with no
  default samples (approved at the plan).
- A root context's `color` is True where STDOUT is styled and otherwise left `None`, not False,
  so an app's own `click.style` output is not stripped on legacy consoles.
- `FORCE_COLOR` on a pipe gives bold headings; `--no-color` keeps bold.
- HELP-18 raises `BadParameter`, so its message reads `Invalid value for ...`, as `secret` does.
- FUT-2 lowers `deprecated` for one click call; `Context.invoke` restores it before the callback,
  so help rendered inside `old` keeps `(DEPRECATED)`.
- `Docs` is each command's own `docs=`, not inherited; nested pointer lines group by declaring
  command.
- The bug hint returns `(hint, url)`; a tracker gets `/new?...` only when its path ends in
  `/issues` and has no query.
- History: one broken commit pair from P5 was folded into `117f00c` before review, so every
  commit parses.

### Remaining after 0.7.0

- `_announced` toggles `param.deprecated` on a shared object: two runs of one CLI in threads may
  race. Listed under Known limits.
- The kit's `_CLEARED` lacks `TTY_INTERACTIVE`, which `testing._CLEARED` has. For 1.0.
- ROB-2's import-time test fails on a WSL-mounted Windows drive (about 155 ms); on the native
  WSL filesystem it passes.
- Not verified this round: the two pre-filled URLs in a browser, with the maintainer; GitLab's
  percent-encoded `issue%5Btitle%5D` form; macOS; 3.11 & 3.13 on POSIX.
- `develop` versions as `0.2.1.devN`: `v0.6.0` is not its ancestor, so the bug URL shows that
  version from a source tree. Pre-existing; release builds are tagged.

### Fixed after evaluation (0.7.0)

1. `ac36bcf` & `2029108`: `test_init` imports `pathlib` before its baseline, and the help test
   drops `urllib.parse` below 3.12, with a NOTE. 3.11: 556 passed, 15 skipped.
2. `5bc9a76`: the `Fixed` bullet removed from CHANGELOG.
3. `4cebada`, after GitHub CI on #15: on Linux 3.11 & 3.12 click's `uuid` import loads
   `platform`, and a Windows runner took 101 ms to import. The import tests now subtract a
   baseline of what `pathlib`, click & rich load, and ROB-2 budgets what pyclig adds over its
   dependencies (50 ms; measured 18-24 ms) instead of an absolute 100 ms.

After merging, `test_child_timeout_bounds_the_cleanup` (from 0.6.0) failed once on Linux 3.11 in
CI on #16, with STDERR only `warning: interrupted`, and passed on re-run: a pre-existing timing
flake, not touched by 0.7.0. Released as v0.7.0 on 11 November 2026.

## Round 8 - the API freeze

Date: 11 November 2026. `docs/plan-1.0.0.md` set eight items to freeze the 0.7 API, with one
approved break; `feat/api-freeze` ships them in nine commits (`9351025` to `3f01a1e`) after the
plan (`36a703f`). One Fable 5.2 implementer worked one phase per message (P1-P4, about 122k
tokens), and the mediator reviewed each phase's diff and re-ran the gate before the next.
Consumers ran unmodified in fresh clones from their remotes, on their locked 0.7.0 and then on a
wheel of the branch (`SETUPTOOLS_SCM_PRETEND_VERSION=1.0.0`) installed with `--no-deps`.

| Repository | Tests | Notes |
| --- | --- | --- |
| pyclig | 561 passed, 15 skipped, 97% | 3.11, 3.13 & 3.14; mypy 3.11 & 3.14 & prek clean |
| pkgdx (fresh, `main` `67bbe3e`) | 242 on 0.7.0; 242 on the wheel | As predicted: no findings |
| dkais (fresh, `develop` `241cff8`) | 147 on 0.7.0; 147 on the wheel | As predicted: ARG-3 ignored |
| template `v0.8.0`, generated `cli=True` | 5 on 0.7.0; 5 on the wheel | As predicted: no findings |
| pkgdx 0.12.0 from PyPI on the wheel | `--help` exit 0 | Kit clean |

### Verdict on the 1.0.0 items

| Item | Verdict | Evidence |
| --- | --- | --- |
| 1 API lock | Confirmed; S1 | `test_public_api_is_frozen`, passing on `v0.7.0`'s `src/` |
| 2 `options.__all__` | Confirmed | `test_star_import_gives_only_the_factories` |
| 3 `Format`, `Level`, `Errors` | Confirmed | `test_signature_types_are_exported` |
| 4 `timeout` keyword order | Confirmed | The lock's one changed line |
| 5 kit clears `TTY_INTERACTIVE` | Confirmed | `test_samples_clear_tty_interactive` |
| 6 internal keywords | Confirmed | Docstrings only, by design |
| 7 `options.confirm_name` | Confirmed; S2 | `test_confirm_name_factory_replaces_confirm` |
| 8 docs & classifier | Confirmed; S3 by the maintainer | 145 rows, statuses unchanged |

API diff: the branch's lock, run on `v0.7.0`'s `src/`, reports exactly the approved changes -
`Errors`, `Format`, `Level` & `options.confirm_name` new, `options.confirm` gone and
`options.timeout` reordered - and nothing else. `tests/api.txt` holds 107 entries and 19 rule
IDs, and renders byte-identically on 3.11 and 3.14.

Reversion: for each of the five commits that change `src/` behaviour, its tests ran with that
change undone on `HEAD`. Every one has failing tests; undoing the rename also fails collection of
`test_core.py`. `options.__all__` was removed by hand, because the rename edits the same lines.
Guards by design: the lock passes without `__all__`, which shows `__all__` equals the 0.7 public
names, and the docstring commit has no test.

Design rules:

- `import pyclig` loads none of `importlib.metadata`, `rich.traceback`, `rich.logging`,
  `_conformance`, `socket`, `urllib.parse` or `platform`.
- The wheel is 1.0.0 with Development Status 5, ships no `tests/`, and its runtime dependencies are
  unchanged (`click~=8.5`, `rich~=15.0`, Python >= 3.11).

Start-up, median of 15 in the dkais clone (0.7.0 → wheel): `import pyclig` 121 → 120 ms,
`dkais --help` 170 → 167 ms, `dkais -v` 169 → 168 ms. Within noise.

### Defects found in 1.0.0

1. In review of P1, the lock named exported classes by their private module
   (`pyclig._config.Config`, `pyclig._core.Context`), so moving a class between `_` modules - not
   API under Stability - would have read as a change. `535086a` names them by their public path.
2. The template amendment draft was first written against pyclig's v2.4.0 copy and appended a
   bullet; checked against template `v0.8.0`, it now replaces the "Raising the pyclig pin to 0.7"
   bullet at `:216-217`.

### Departures from the 1.0.0 plan

- `options.__all__` has 12 names (11 factories & `NoneOr`), not "12 factories and NoneOr".
- The lock also records return annotations and class attributes (`context_class`, `group_class`).
- The ARG-11a & ARG-11b evidence cells are unchanged in wording, which the line length left no
  room for; "Delivered in 1.0.0" describes the pairing.
- The rename's docstring names the `force()` / `pyclig.confirm` pairing too.

### Remaining after 1.0.0

- pyclig's own `docs/guidance/standard-cli.md:107` (immutable, v2.4.0) still names
  `options.confirm`; a Copier update after the template release refreshes it.
- Deferred by the plan: `since=` & scoped ignore keys, the `_announced` thread race, macOS,
  exporting `ConfigError`, import timing on a WSL-mounted drive, the
  `test_child_timeout_bounds_the_cleanup` CI flake, and `develop` versioning as `0.2.1.devN`.

### Consumer transitions (drafts, unfiled)

Every consumer pins `~=0.x`, so none accepts 1.0.0 until its pin is raised; none needs a code
change.

1. **pkgdx, first:** raise `pyproject.toml:30` to `pyclig~=1.0`, release 0.13.0.
2. **Template, after pkgdx 0.13.0:** `template/pyproject.toml.jinja:23` `pyclig~=1.0` & `:27`
   `pkgdx~=0.13`; `tests/test_template.py:265` (it fails until updated) & `pyproject.toml:45`; the
   `standard-cli.md` amendment (`:116` & `:216-217`, version 2.6.0); release.
3. **dkais, after pkgdx 0.13.0:** `pyproject.toml:29` `pyclig~=1.0` & `:36` `pkgdx~=0.13`; `uv
   sync` (its `.venv` holds pyclig 0.4.0), re-lock; then the Copier update.
4. **cotravel, last:** re-lock, then the Copier update.
