# Plan - pyclig 0.5.0: configuration and environment

## Context

`docs/roadmap.md:29-38` puts "0.5 - configuration and environment" next. Its rows in
`docs/clig-coverage.md` are `gap` or `partial (click)`: CFG-2, CFG-3, CFG-4, CFG-8, ENV-6, ENV-13,
ENV-16, OUT-13e and ARG-6e. pkgdx hand-rolls a config directory (`standards/__init__.py:32-61`), and
dkais reads one env var per option. 0.5 adds:

- a config layer that sits under click's `default_map`;
- XDG paths;
- `.env`;
- secrets from a file or STDIN;
- `<PROG>_DEBUG` and `<PROG>_NO_COLOR`;
- three value factories.

The release is additive, and config is opt-in: a CLI without `config=` gets no new options and
reads no files.

Process mirrors `docs/plan-0.4.0.md`. Three read-only explorers and one Plan agent produced this
design. I checked its key claim in click itself: `iter_params_for_processing` (`click/core.py:158-166`)
sorts by `(not is_eager, invocation index)`, and `Context.__init__` inherits
`parent.default_map.get(info_name)` (`:392`). An eager `--config` declared first therefore runs
before any option that falls back to `default_map`.

Decisions taken (with you, 6 November 2026):

- All seven roadmap items ship in 0.5.0.
- The app names the project file. The default is `.<name>.toml`, found by searching upward from
  the working directory, or `pyproject.toml` with `table="tool.<name>"`. Parsed with `tomllib`.
- Secrets come from a file or STDIN only: `options.secret("token")` adds `--token-file FILE`,
  where `-` means STDIN. A store is reached by pipe or process substitution. ENV-16 becomes `done`.
- One Fable implementer, then a fresh Fable evaluator, so the implementer never grades its own work.
- Branch `feat/config-env` from `origin/develop` at `617b548` (tag v0.4.0).

Defaults, overridable at the P4 stop:

- `<PROG>` is the normalised package name (`State.package`) in both runners. `pyclig.run` hooks
  have no root name, and argv stems differ per hook.
- `--config FILE` replaces all discovered files. Flags, env and `.env` still win over it.
- A chosen `[profiles.NAME]` outranks the files' main sections.
- Top-level keys do not cascade into subcommand tables (click's `default_map` shape). Shared
  settings use a value `GlobalOption`.
- `.env` is opt-in (`Config(dotenv=True)`) and read from the working directory only.
- Run flags read config like any option (`quiet = true`). Unknown keys are ignored; `-d` logs the
  files it loaded.
- ENV-14 becomes `done`, owner `auto`. No new kit check, so consumers get no new findings.
- `CHANGELOG.md` `[0.4.0]` has no date. Add `2026-11-04` (the v0.4.0 tag date) in P7.

Scope of authority: local commits on `feat/config-env` only. No push, PR, tag, release or filed
issue without a separate ask. Consumer repos are read-only and are tested as scratch clones.
Immutable guidance (`standard-cli.md`) is drafted, not edited.

## Agents and context budget

Fable 5.1 has a 1M window, but every turn re-sends the whole context, so cost and focus degrade
well before the limit and compaction loses detail. Calibration from this session: Explore 50-65k,
Plan 150k.

| Agent | Work | Target | Hand off at |
| --- | --- | --- | --- |
| Fable implementer (`model: "fable"`) | P1-P7 | ~350k | 500k |
| Fable evaluator (fresh, `model: "fable"`) | P8 & Round 5 | ~200k | 400k |

Handover:

- This plan is `docs/plan-0.5.0.md`, the branch's first commit, with no frontmatter, like the 0.3
  and 0.4 plans.
- Each brief is that file plus `CLAUDE.md` and the phase to run, never a transcript.
- One commit per item, so `git log` is the progress record.
- I run the implementer one phase per message: launch it for P1, then continue it with
  SendMessage for P2 onwards. Each completion notice carries a token count. Past the hand-off line
  I start a fresh Fable from the plan and the log, never a continuation.
- P4 and P8 return to you before going further.

Rules for both agents, put in each brief:

- Read only the ranges the phase lists. Grep first, then Read with offset and limit.
  - Never read `_core.py` or a whole test file. Don't re-read a file you just edited.
- Filter output:
  - pytest: `uv run pytest -q --no-header --tb=short -x <file> 2>&1 | tail -15`
  - mypy: `| tail -5`
  - prek: `| tail -15`
  - coverage: `just coverage | tail -8`
- Run the full gate once per phase, not per edit.
- No sub-subagents. Reports back stay under 150 words and quote any failure verbatim.
- Stop and report at a contradiction with the plan; don't improvise around it.

## Design

New modules:

- `src/pyclig/paths.py`: public, like `options`.
- `src/pyclig/_config.py`: `Config`, the config options, loading and `.env`. `tomllib` is
  imported inside functions only.

Tests go in `tests/test_paths.py` and `tests/test_config.py`, using local test CLIs, never new
`sample_cli` commands.

### Item 1 - XDG paths (CFG-4 `done`)

`config_dir(name)`, `data_dir(name)` and `system_config_dir(name)` return a `Path`.

Each tries, in order: Windows (`sys.platform == "win32"` and the variable set), an absolute XDG
variable, then the fallback.

| Function | Windows | XDG | Fallback |
| --- | --- | --- | --- |
| `config_dir` | `%APPDATA%\name` | `$XDG_CONFIG_HOME/name` | `~/.config/name` |
| `data_dir` | `%LOCALAPPDATA%\name` | `$XDG_DATA_HOME/name` | `~/.local/share/name` |
| `system_config_dir` | `%PROGRAMDATA%\name` | first absolute `$XDG_CONFIG_DIRS` | `/etc/xdg/name` |

- macOS follows XDG, as pkgdx does. click's `get_app_dir` is not used: it picks `~/Library` and
  accepts a relative XDG path.
- `os.environ`, `sys.platform` and `Path.home()` are read on every call, because pkgdx's tests
  patch all three.
- No directory is created. A relative XDG value is ignored.

### Item 2 - `GlobalOption` taking a value (CFG-8 prerequisite)

`_flags.py:28-68` hard-codes `is_flag=True`.

| Declaration | Behaviour |
| --- | --- |
| No `type=` | Flag. The callback runs when truthy (as in 0.4). |
| `type=` given, or `is_flag=False` | Takes a value. The callback runs when given (below). |

"Given" means the value is not `None` and `ctx.get_parameter_source` is not `DEFAULT`.

- An explicit `is_flag=` wins.
- Still eager and still `expose_value=False`. The command gets the value through its callback,
  e.g. `ctx.meta["app.region"]`, which needs a documented example.
- The parameter name is a top-level config key, which is how shared settings are configured.
- Callbacks stay idempotent, since they run once per nesting level.

### Item 3 - config layer and precedence (CFG-3, CFG-8 `done`)

```python
@dataclass(frozen=True)
class Config:
    name: str | None = None  # dirs & default file; default State.package
    project: str | None = None  # bare file name; default f".{name}.toml"
    table: str | None = None  # dotted, e.g. "tool.pkgdx"; project file only
    profiles: bool = False  # adds --profile NAME
    dotenv: bool = False  # Item 4
```

`pyclig.group(..., config=Config(...))`, and `pyclig.command` too, inserts options at `params[0:2]`:

- `--config FILE`: an eager value `GlobalOption`, `click.Path(exists=True, dir_okay=False)`,
  envvar `<P>_CONFIG`.
- `--profile NAME`: only with `profiles=True`, envvar `<P>_PROFILE`.

The parameter names are `pyclig_config` and `pyclig_profile`, so they cannot clash with an app's
own option. `Group.add_command` rejects `config=` on a subcommand, as it does for `errors=`.

`ConfigOption.handle_parse_result`:

- reads the profile through the sibling option's `consume_value`;
- merges the layers into `ctx.default_map`, so click's own order gives flag > env > map > default;
- records the loaded files in `State` and logs them at debug level;
- skips completely under `resilient_parsing`.

`--help` and `-v`, when given, are eager and invoked, so they exit before any file is read.

| # | Source (highest first) |
| --- | --- |
| 1 | Command line (click) |
| 2 | Env via `envvar=` (click) |
| 3 | `.env` (Item 4) |
| 4 | `[profiles.NAME]`: project, then user, then system (only with `--profile`) |
| 5 | Project file, nearest from the working directory upward (`table` applied) |
| 6 | User file `paths.config_dir(name)/config.toml` |
| 7 | System file `paths.system_config_dir(name)/config.toml` |
| 8 | The app's `default_map`, then `default=` |

Merging and shape:

- Tables merge recursively; scalars and lists are replaced.
- Top-level keys belong to the root and `[sub]` to a subcommand.
- With `--config`, layers 4-7 become that file only.
- The nearest project file wins even when it lacks `table`, giving an empty layer.
- `tomllib` is imported only when a file exists.

| Case | Result |
| --- | --- |
| No files | No-op, `tomllib` not imported |
| (exit 1 cases raise) | `ConfigError(click.ClickException)` |
| Bad TOML, or a found file unreadable | `error: cannot read config PATH: detail`, exit 1 |
| `--config` missing, or a directory | Usage error, exit 2 |
| `--profile x` not defined in any loaded file | `BadParameter` naming the files, exit 2 |
| `[sub]` is not a table | `ConfigError`, exit 1 |
| `prog sub --config f` | Applies to `sub` and below (documented, like `-d`) |
| Completion, `--help`, `-v` | No file read |

`testing.invoke(..., config_files=False)` passes `pyclig_discover=False`, so the developer's real
config and `.env` never leak into tests. `--config` and `<P>_CONFIG` still work, and discovery
tests opt in with `env=` and `monkeypatch.chdir(tmp_path)`.

### Item 4 - `.env` (CFG-2, ENV-13 `done`; ENV-14 `done`, auto)

Only with `dotenv=True`. Reads `./.env` once at the root into `State.dotenv`. Parse rules:

- `KEY=value` and `export KEY=value` are accepted.
- `#` comments and blank lines are skipped. An unquoted `value # c` drops the trailing comment.
- Single or double quotes are removed. There are no escapes and no `$VAR` expansion.
- Keys match `[A-Za-z_][A-Za-z0-9_]*`. The file is read as `utf-8-sig`.
- Any other line warns `.env:LINE: not KEY=VALUE, ignored`, and the rest is still read.

How values are applied:

- `.env` fills a declared `envvar=` only when click found no value. It works by per-instance
  wrapping of `resolve_envvar_value`, the same pattern as `_prompt` at `_core.py:404-409`.
- It never writes `os.environ`, so child processes are untouched (pkgdx `PKGDX_SENTINEL`).
- Secret-pattern names are skipped. `_SECRET` moves from `_conformance.py:50-52` to `_config` and
  is imported back, so `.env` and ENV-15 share one definition.

### Item 5 - secrets (ENV-16 `done`; ARG-16 evidence; HELP-18 `partial`)

`options.secret(name, *, help=None, required=False)`: `secret("api-key")` adds
`--api-key-file FILE` with parameter `api_key`. The type is
`click.Path(exists=True, dir_okay=False, allow_dash=True)`, and a callback reads the file.

| Input | Command receives |
| --- | --- |
| Not given | `None`, or a usage error if `required` |
| FILE, `/dev/fd/N`, `<(pass show x)` | UTF-8 text, one trailing `\n` or `\r\n` removed |
| `-`, STDIN piped | STDIN text, same rule |
| `-`, STDIN a terminal | Usage error, exit 2 ("pipe it in"). Never blocks or echoes |
| Empty after stripping, missing file, or a directory | Usage error, exit 2 |

`--api-key-file` doesn't end in a secret word, so the kit stays clean.

### Item 6 - `<PROG>_DEBUG` and `<PROG>_NO_COLOR` (ENV-6, OUT-13e `done`, auto)

- `<P>` is `re.sub(r"\W", "_", package).upper()`, from a new `State.env_prefix`.
- Truthy means non-empty and not `0`, `false`, `no` or `off`. Bare `NO_COLOR` keeps Rich's
  "any non-empty" rule, and the README notes the difference.
- Read in `Command.main` (`_core.py:553-609`) and `pyclig.run` (`:870-908`) after `State` is built
  and before `_logging.configure`. A later `-d` or `--no-color` is a no-op.
- Not shown in `--help`, so consumers' help tests are unchanged.
- `testing.invoke` clears `<P>_DEBUG`, `_NO_COLOR`, `_CONFIG` and `_PROFILE`.

### Item 7 - `-o`, `-p`, `-u` (ARG-6e `done`)

All three are keyword-only, with `help=`, `default=` and `envvar=`:

- `options.output()`: `click.Path(dir_okay=False, allow_dash=True, path_type=Path)`.
- `options.port()`: `click.IntRange(1, 65535)`, metavar `PORT`.
- `options.user()`: `str`, metavar `NAME`.

They match `STANDARD_SHORT` (`_conformance.py:36-47`).

## Phases

Show each new test failing before its change. Every phase ends with the gate passing.

| Phase | Work | Stop |
| --- | --- | --- |
| P0 | Branch, commit `docs/plan-0.5.0.md` (done by me) | - |
| P1 | Item 6, `State.env_prefix`, `invoke` clearing | - |
| P2 | Item 2 | - |
| P3 | Item 1 | Fit report |
| P4 | Item 3, `invoke(config_files=)`, `tomllib` forbidden in `test_init.py` | **Maintainer** |
| P5 | Item 4 | - |
| P6 | Item 5, then Item 7 (two commits) | Kit report |
| P7 | Docs & full gate | Evaluator |
| P8 | Consumer integration, no pyclig changes | **Maintainer** |

Read only, per phase (plus the files the phase creates):

- **P1:** `_run.py:62-108`, `_core.py:553-609` & `:870-908`, `testing.py:38-116`,
  `tests/test_run.py:1-45`.
- **P2:** `_flags.py:28-87`, `_core.py:485-521`, `tests/test_core.py:185-260`.
- **P3:** pkgdx `standards/__init__.py:32-61`, `tests/test_standards_config.py:13-86`.
- **P4:** click `core.py:142-166`, `:380-394`, `:2481-2520`; `_core.py:70-100`, `:361-423`,
  `:693-711`, `:823-851`, `:911-948`; `tests/test_init.py`; dkais `_cli.py:86-103`.
- **P5:** `_core.py:400-409`, click `core.py:2669-2728`, `_conformance.py:50-53`.
- **P6:** `options.py`, `_conformance.py:142-186`, `tests/test_options.py:1-60`.
- **P7:** README `:81-113` & `:201-212`; CHANGELOG head; roadmap; coverage by Grep;
  `standard-cli.md:100-118`.
- **P8:** `evaluation.md:260-361`.

Line numbers are as of `617b548`. Earlier phases shift them: Grep for the symbol first.

Tests cover every table row above, plus `-q`, off-TTY, completion (`_PROG_COMPLETE`) and nesting.

Fit reports, which stop only if they fail:

- **P3:** in a scratch clone of pkgdx, `user_config_dir` keeps its `PKGDX_CONFIG_DIR` branch and
  returns `pyclig.paths.config_dir("pkgdx")`. `tests/test_standards_config.py` must pass unchanged.
- **P4:** a dkais sketch with `Config(project=".dkais.toml")` and `[download] data_dir`. It shows
  flag > `DKAIS_DATA_DIR` > file, and the cost of a per-command table against a value
  `GlobalOption`.
- **P6:** `assert_conforms` is clean on a CLI using all four factories.

**P4 stop:** you see the precedence-matrix test output, the root and subcommand `--help` of a
config CLI, and the dkais fit. You confirm or override each default listed under Context.

P4 result: the matrix, both `--help`s and the dkais fit passed (134 tests unmodified; flag >
`DKAIS_DATA_DIR` > file for `process --dry-run`). Every default stood, per-command tables kept
over a cascade. Two decisions: `--config FILE` named like the project file (e.g.
`pyproject.toml`) selects `table` as discovery does, otherwise the file is read whole; and
`tests/conftest.py` clears the colour & terminal variables for every test, after a developer's
`NO_COLOR=1` failed three 0.4.0 tests. Found on the way: `prog sub --help` needed a look-ahead,
since the root parses (and would read the files) before the subcommand's `--help` is seen; and
click takes a callback's return as the option's value, so `GlobalOption` now returns it.

Fixed after evaluation: the help look-ahead went. Config always loads (not under completion), and
a `ConfigError` is kept on the `State` and raised when a command is invoked, so `--help` in any
position, `help sub` and `-v` exit 0 on a broken file while a run still exits 1; `sub --help` may
therefore read the files, where the table above says none. A sub-level `--profile` now layers
like a root one, and `config_files` records every file applied.

P7 edits:

- `README.md`: Configuration, Paths and Secrets sections; run-flag env vars; standard flags; a
  value `GlobalOption` example.
- `CHANGELOG.md`: a `[0.5.0]` entry; date `[0.4.0]` as 2026-11-04.
- `clig-coverage.md`: "as of 0.5.0", the rows below, and a "Delivered in 0.5.0" section after
  line 259.
- `roadmap.md`: mark 0.5 delivered. Secrets read "from files or STDIN (pipes, process
  substitution)".
- `test_init.py`: add `tomllib` to the forbidden imports.
- Draft, don't apply, a `standard-cli.md` amendment: lines 103-116 gain `-o`, `-p` and `-u` with
  their helpers, plus a short paragraph on config, env and secrets. It goes to the Copier template
  first.

Coverage after 0.5:

| Rows | Status | Owner | Evidence |
| --- | --- | --- | --- |
| CFG-2, ENV-13, CFG-3, CFG-4, CFG-8, ENV-16, ARG-6e | done | interface | as above |
| ENV-6, OUT-13e, ENV-14 | done | auto | as above |
| HELP-18 | partial | interface | `secret('-')` refuses a terminal |
| ARG-16, ENV-15, SUB-2, CFG-1 | unchanged | unchanged | add new evidence |

Gate, every phase:

- `uv run pytest -q`
- `just coverage` at 90% or more
- `uv run mypy --config-file mypy.ini --python-version 3.11`, and again with `3.14`
- `uv run prek run --all-files`

Critical files:

- `src/pyclig/_core.py`: `Context.__init__` 81-99, `Command.__init__`/`get_params` 381-423,
  `main` 553-609, `add_command` 693-711, `command`/`run`/`group` 823-948.
- `src/pyclig/_flags.py`, `src/pyclig/_run.py` (`State` 62-108), `src/pyclig/options.py`,
  `src/pyclig/testing.py` (`invoke` 38-116), `src/pyclig/_conformance.py` (`_SECRET`),
  `src/pyclig/__init__.py` (exports `Config`, `paths`).
- New: `src/pyclig/_config.py`, `src/pyclig/paths.py`.

## Consumers: when each needs updating

**No consumer changes while P0-P7 run.** dkais (`github/dkais`) and pkgdx (`gitlab/pkgdx`) both pin
`pyclig~=0.4.0`, use no `GlobalOption`, and get no `config=` without opting in. The predicted
MUSTs are pin raises only, because `~=0.4.0` excludes 0.5.0.

| When | pkgdx | template | dkais | cotravel |
| --- | --- | --- | --- | --- |
| P8 (pre-release) | Scratch clone | Scratch clone from GitHub (not on disk) | Scratch clone | - |
| After pyclig 0.5.0 on PyPI | **1st:** `pyclig~=0.5.0`, release 0.10.0 | - | - | - |
| After pkgdx 0.10.0 | - | **2nd:** pins, see below | **3rd:** see below | Re-lock |
| After the template release | Copier update | - | Copier update | Copier update |

- **template** `copier-python-package`: the pyclig pin in `pyproject.toml.jinja` and
  `tests/test_template.py`, the `pkgdx~=0.10` dev pin, and the `standard-cli.md` amendment.
- **dkais**: `pyclig~=0.5.0` **and** `pkgdx~=0.10`, then a lock check.

Why this order (re-checked against PyPI metadata in P8):

- pkgdx 0.9.0 requires `pyclig~=0.4.0`. dkais on `pyclig~=0.5.0` with `pkgdx~=0.9` therefore fails
  to resolve, which is loud.
- pkgdx 0.7.0 requires `pyclig~=0.2`, which accepts 0.5. A pin still allowing 0.7 silently falls
  back to it. Hence pkgdx first, and every consumer raises the pkgdx lower bound.
- Not affected: `pkgdx-consumer`, `mpctraj` and `dataclocklib` (old pkgdx, no pyclig).
- When pkgdx gains `PKGDX_DEBUG` automatically, check that no pkgdx test asserts on an
  environment without it.

Optional adoption, in later consumer PRs:

- `paths.config_dir`: pkgdx's `user_config_dir` platform branch, free if the P3 fit passes.
- `paths.data_dir`: the dkais `--data-dir` default (`_cli.py:86-103`). A behaviour change, since
  `required` goes.
- `Config`: dkais `.dkais.toml`, and its help gains `--config`. Not pkgdx: `project_excludes` is
  strict, and hooks read it with no parser.
- `<PROG>_DEBUG`: automatic in both.

## Verification

**Evaluator (P8), fresh Fable.** Its brief is this plan, `CLAUDE.md` and
`git diff 617b548...HEAD`. It does not trust the implementer's summary. It works on scratch
clones from each `origin/develop` and on a wheel of the branch.

1. Gate on Python 3.11, 3.13 and 3.14.
2. Reversion check: in a scratch worktree, revert each feature commit's `src/` hunk and confirm
   that its tests fail.
3. Behaviour by real subprocess, with temporary APPDATA/XDG directories and working directory:
   - the full precedence matrix, `--config` replacing, and `--profile` in either order;
   - bad TOML exits 1 naming the file, and a missing `--config` exits 2;
   - a malformed config with `--help`, `-v` or completion exits 0;
   - `printf 's3cret\n' | prog x --token-file -` receives `s3cret`;
   - `PROG_DEBUG=1` logs during parsing, and `=0` doesn't;
   - `PROG_NO_COLOR=1 FORCE_COLOR=1` gives no colour;
   - `.env` never overrides real env, skips `*_TOKEN`, and leaves child-process env untouched.
4. Design rules:
   - no new dependency;
   - `-X importtime` shows no `tomllib`, `rich.traceback`, `rich.logging`, `importlib.metadata` or
     `_conformance` on `import pyclig`, and no `tomllib` on `--help` or `-v` of a config CLI;
   - the paths functions create no directories.
5. Consumers on the wheel:
   - dkais and pkgdx suites unmodified, predicted 0 failures;
   - `assert_conforms` clean, and dkais `test_fast_paths_skip_heavy_imports` passes;
   - the P3 sketch passes `test_standards_config.py`;
   - a generated `cli=True` template project passes `test_main`;
   - `PKGDX_DEBUG=1` on a pkgdx hook logs debug;
   - pkgdx 0.7.0 from PyPI runs on the branch;
   - median of 15 for `--help`, `-v` and `import` against 0.4.0.
6. Writes "Round 5" in `docs/evaluation.md` in round 4's format: tests table, verdict per item with
   evidence test, defects, integration, departures, what remains. Drafts the consumer transition
   issues with predicted failures, not filed.

A prediction that misses blocks the release until explained.

**Me, after the evaluator.** Re-run the gate, read the diff, spot-check three verdicts, and report
results as found, failures included.

**You.** The P4 and P8 stops, the `standard-cli.md` amendment, then PR, release 0.5.0 and the
consumer sequence above, each on your say-so.
