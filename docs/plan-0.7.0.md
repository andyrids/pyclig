# Plan - pyclig 0.7.0: close every remaining row (then a 1.0.0 freeze)

## Context

The local clone is stale: it is on `chore/copier-0.5.0`, while GitHub has 0.5.0 and 0.6.0 released
(PRs #10-#13) and `develop` at `e0351f8` (Copier template 0.7.0 merged). So the next roadmap step is
**"1.0 - API freeze": every `docs/clig-coverage.md` row `done`, or owned `out`, and the kit gains
`samples=`**. About 29 rows are still `partial` or `gap` without being owned `out`.

Decisions taken with you:

- The work is split. **0.7.0** closes the rows additively and is planned here. **1.0.0** is a small
  freeze release, listed only in the appendix.
- **HELP-16** is owned `out`. CLIG says you *can* offer to run the correction, then warns that doing
  it is dangerous. Suggesting it (HELP-15) and never auto-running it (HELP-17) are both done.
- **INT-5, ENV-10 and ROB-4** close as `done`, with tests and evidence, not as `out`:
  - INT-5 by `ctx.cleanup`'s watcher, whose owner is `interface`.
  - ENV-10 by `TERM=dumb`; pyclig emits ANSI only, so TERMINFO/TERMCAP do not apply.
  - ROB-4 by a threaded `notice(items=)` test.

Defaults you can override when you approve:

- New static kit rules are **on by default**. Raising the `~=0.6.0` pin is when a consumer opts in.
  Rules that use `samples=` are opt-in by construction.
- `samples=` serves BAS-4, BAS-5 and ERR-2 only. ARG-1, ARG-5, SUB-4 and SUB-5 are static, which
  departs from the roadmap's wording. No default samples come from `examples=`, because those would
  do real work.
- Owner changes: ROB-2 `check`→`interface`, HELP-10 →`interface`, ERR-2 →`interface`.
- The ERR-8 pre-filled URL never contains the message, the arguments, paths or the environment.

**Scope of authority:** local commits on `feat/close-rows` only. Push, PR, tag, release and filed
issues each need a separate ask. Consumer repos are read-only and are tested as scratch clones.
Files marked immutable are proposed, not edited.

## Agents, context budget & mediation

Fable 5.2 has a 1M context window and 128K output tokens per response. The whole context is re-sent
every turn and compaction is lossy, so each agent works to a budget well below the limit. The
0.6 implementer used about 290k.

| Agent | Phases | Target | Hand off at |
| --- | --- | --- | --- |
| Fable implementer A (`model: fable`) | P1-P3 | ~300k | 400k |
| Fable implementer B (fresh, from the plan & `git log`) | P4-P8 | ~320k | 400k |
| Me (Opus), mediator & evaluator | Every phase review, then the evaluation | - | - |

**How I mediate:**

1. P0 commits this plan as `docs/plan-0.7.0.md`. Each agent's brief is that file, `CLAUDE.md` and
   one phase. I never paste a transcript into a brief.
2. I send one phase per message. When the agent reports back, I read the token count, the
   `git show --stat` of each new commit and the targeted hunks. I re-run the gate myself, then send
   the next phase with SendMessage, but only while the agent is below its hand-off line.
3. Past that line, a fresh agent starts from the plan and the log.
4. If an agent disputes the plan, it stops and reports. I resolve the point, or bring it to you.

**Agent rules:**

- Grep first, then Read with offset and limit, using the phase's "Read only" ranges. Never read all
  of `_core.py` or a whole test file.
- Filter output with `| tail`. Run the full gate once per phase.
- One commit per item.
- Show each new test failing first. An evidence-only test must fail under a deliberate break.
- No sub-subagents. Reports stay under 150 words, with failures quoted verbatim.

## Design (signatures: console first, then keyword-only; all additive)

### Item 1 - static kit rules (two commits: 1a flags, 1b naming)

The rules go in `_conformance.py` (`check` 75-105, `_check_params` 140-184, `STANDARD_SHORT` 36-47).
Each uses the literal `Finding("ID", ...)`, so the coverage-row test at `test_conformance.py:141-150`
sees it.

| Rule | Fires | Silent |
| --- | --- | --- |
| ARG-1 | An Argument typed BOOL, `Choice`, INT/FLOAT or a range | STRING, Path, File, custom |
| ARG-3 | A short that is not a `STANDARD_SHORT` key | Standard shorts |
| ARG-5 | 2 or more Arguments with differing `type.name` | `cp SRC DST`, or `nargs=-1` of one type |
| ARG-6+ | A standard long form with a different short (`--force/-F`) | No short |
| SUB-3+ | One long name, a different short or kind across commands | `GlobalOption`s |
| SUB-4 | Siblings that mix `-` and `_`, or an upper-case name | - |
| SUB-5 | update/upgrade or remove/delete; edit distance 1 with both names 4+ characters | Aliases |
| ENV-2 | `envvar` not matching `^[A-Z_][A-Z0-9_]*$` | - |
| ENV-4 | `envvar` in the common set below | Long name equals the variable (`--editor`) |

ENV-4's common set: HOME, PATH, USER, SHELL, TERM, TMPDIR, LANG, TZ, EDITOR, VISUAL, PAGER,
COLUMNS, LINES, DEBUG, NO_COLOR, FORCE_COLOR, `*_PROXY`.

Tests:

- A new fixture `lax` trips each rule once.
- `clean` stays clean.
- The expected set for `adv` gains exactly `("ARG-3", "adv cp")`.
- `test_probes_never_run_a_callback` records no calls.

### Item 2 - `samples=` (BAS-4 `done`/check, ERR-2 `done`/interface)

`check(cli, *, ignore=None, samples: Iterable[Sequence[str]] = ())`, and the same on `assert_conforms`.

- Each sample runs through `CliRunner`, with `_CLEARED` and the run variables cleared.
- The finding's `command` is `shlex.join([root, *sample])`.
- Findings:
  - BAS-4: a non-zero exit, or `--json` output that fails `json.loads`.
  - BAS-5: a STDOUT line that starts with `error:` or `warning:`.
  - ERR-2: `Traceback (most recent call last)` on STDERR.
- The kit docstring gains: "never runs a command body unless given samples".

### Item 3 - robustness (ROB-9 `done`/auto; ROB-2, ROB-4, INT-5 `done`/interface)

- **INT-5:** a `recv` mode in `_CLEANUP_CHILD` (`test_signals.py:289-348`) blocks in `a.recv(1)` inside
  `ctx.cleanup(timeout=T)`. The child gets `CTRL_BREAK_EVENT` on Windows and `SIGINT` on POSIX.
  `CTRL_C_EVENT` cannot be aimed at a single child, and would hit pytest too. The test asserts:
  - the notice arrives within 0.5 s;
  - the run exits 130 within T + 0.3 s;
  - it fails when `Watcher.start` is patched.

  README shows `with ctx.cleanup(timeout=2):` around blocking I/O.
- **ROB-4:** `test_notice_items_from_threads_never_interleave` (8 threads × 20 calls, 3 items each).
  Today's threaded test (`test_output.py:79-97`) covers a wrapped notice only.
- **ROB-2:** a subprocess runs `-X importtime`; the minimum of 3 runs must show pyclig's cumulative
  time under 100 ms.
- **ROB-9 matrix:** `sample_cli` runs `--help`, `-v`, a notice and a crash under each of:
  - no HOME, USERPROFILE or APPDATA;
  - a read-only or deleted cwd (POSIX);
  - `LC_ALL=C`;
  - a closed or `DEVNULL` STDIN;
  - `TERM=dumb`, `COLUMNS=20` and an empty `PYTHONIOENCODING`.

  Exit codes stay normal, with no traceback except on the crash.
- **ROB-9 fixes** (each shown failing first):
  - (a) An empty `PYTHONIOENCODING` is no longer treated as set (`_run.py:240`).
  - (b) On win32, `is_tty` confirms with `GetConsoleMode`. ctypes is imported only after `isatty()`
    returns True, and `force_terminal=False` is set when it says no. This fixes `> NUL` and Git
    Bash's `</dev/null`.
  - (c) Only if the matrix fails: a missing home or cwd skips that config layer
    (`_config.py:316-330`).

### Item 4 - arguments & deprecation (ARG-15 `done`/auto; ARG-14, HELP-18, FUT-2 `done`/interface; ARG-4 `done (click)`)

- **ARG-15:** `_versioned` (`_core.py:1044-1057`) declares `-v/--version` as a `GlobalOption`, so
  `prog show -v` prints the version. Its callback does nothing under resilient parsing, and an app's
  own `-v/--verbose` still wins. At the root the flag moves to `GLOBAL OPTIONS:`.
- **ARG-14:** `options.NoneOr(click.ParamType)`, with
  `__init__(self, inner: click.ParamType | type = click.STRING, *, word: str = "none")`.
  - `none` in any case becomes `None`; any other value goes to `inner.convert`.
  - The metavar is `INNER|none`.
  - Values from the environment and config get the same treatment.
- **HELP-18:** the param loop in `Command.__init__` (`_core.py:567-581`) wraps every read-mode
  `click.File`. When STDIN is a terminal, `-` gives the usage error
  `STDIN is a terminal - pipe the input in or name a file` and exit 2. This also covers a default
  of `-`, and resilient parsing is skipped.
- **FUT-2:** a deprecated command prints `warning: command 'old' is deprecated - REASON` on the run's
  STDERR console. click's own line is suppressed with a try/finally on `self.deprecated`, and
  deprecated params get the same treatment. `DeprecationWarning:` never appears, and help keeps
  `(DEPRECATED)`.
- **ARG-4:** a Windows subprocess test shows that `*.txt` arrives as typed.

### Item 5 - help content (HELP-3, HELP-7 `done`/auto; HELP-8, HELP-10 `done`/interface)

- **New keyword:** `Command(..., docs: str | None = None)`, which `pyclig.command` and `group` forward.
- **HELP-3:** concise help (`_core.py:712-723`, `:924-941`) lists the command's own visible options,
  but only when there are 1 to 6 (`_CONCISE_OPTIONS = 6`).
- **HELP-7 & HELP-8:** a final `LEARN MORE:` section.
  - It shows `Docs  URL` when `docs=` is set.
  - It shows `Issues  URL` in the root's full help, taken from `_project_url`.
  - It is absent when empty, and never appears in concise help.
- **HELP-10:** in a multi-line `examples=` item, the first line is the invocation and the rest is
  output, indented 2 more spaces. Single-line examples stay byte-identical (pkgdx
  `test_standards_cli.py:522-523`).
- **Fix:** the pointer for a nested group's `GlobalOption` names the group that declares it.

### Item 6 - help style (HELP-14 `done`/auto; ENV-10, ENV-12 `done (rich)`)

- **Bold:** headings and `USAGE:` go through `click.style(bold=True)`, but only when the run's
  console is styled (`color_system` set and not `legacy_windows`). The root `Context.color` follows
  `state.out`; concise help on STDERR follows `state.err`.
- **Usage errors** are `click.unstyle`d, because they print through Rich `Text` (`_run.py:436-446`).
- `--no-color` keeps bold.
- Tests:
  - No ESC codes on a pipe, with `testing.invoke(color=False)`, with `TERM=dumb`, or in a usage error.
  - Bold appears on a forced terminal.
  - `LINES=7` gives `ctx.err.size.height == 7`. **If Rich does not honour `LINES`, stop.**

### Item 7 - pre-filled bug report (ERR-8 `done`/auto)

- **URL by host:**
  - github.com: `/issues/new?title=&body=`.
  - gitlab.com: `/-/issues/new?issue[title]=&issue[description]=`.
  - Any other host keeps the plain URL.
- **Title:** `PROG VER: unexpected Type`.
- **Body:** program and pyclig versions, Python, `platform.system()` with its release, the exception
  type, and "paste the output above". It never contains the message, argv, paths or the environment.
- **Imports:** `urllib.parse` and `platform` are imported only on the crash path.
- **Printing:** the URL goes on its own `soft_wrap` line. Update `test_run.py:215-226` and test at
  `COLUMNS=40`.

### Item 8 - docs

- **`clig-coverage.md`:**
  - "as of 0.7.0";
  - the "Checked by the kit" list;
  - a "Delivered in 0.7.0" section;
  - HELP-16 owned `out`, with its reason;
  - a **Known limits** list: run flags are not applied when parsing fails before them; `Path(allow_dash)`
    is unguarded; `auto_envvar_prefix` is invisible to ENV-2 and ENV-4; macOS is unverified.
- **`roadmap.md`:** a 0.7 section marked delivered; 1.0 becomes the freeze only.
- **README:** the kit rules, `samples=`, `docs=`, `NoneOr` and the INT-5 pattern.
- **CHANGELOG:** `[Unreleased]` with a "Kit: new findings" subsection.
- **Draft only:** the template's `standard-cli.md` amendment, including the stale "(pyclig 0.5)"
  heading at `:125`.

## Phases

Line refs are on `develop` at `e0351f8`.

| Agent | Phase | Work | Read only (Grep the symbol first) | Stop |
| --- | --- | --- | --- | --- |
| me | P0 | `git fetch`, branch `feat/close-rows` from `origin/develop`, commit the plan | - | - |
| A | P1 | Item 1 | `_conformance.py`; `test_conformance.py:1-175`; coverage rows by Grep | S1 |
| A | P2 | Item 2 | `_conformance.py`; `testing.py:39-130`; `_run.py:148-165` | - |
| A | P3 | Item 3 | See P3 below | **S3 you** |
| B | P4 | Item 4 | See P4 below | - |
| B | P5 | Item 5 | `_core.py:620-725`, `:905-945`; `_run.py:355-388`; `test_core.py:33-120` | - |
| B | P6 | Item 6 | See P6 below | **S6 you** |
| B | P7 | Item 7 | `_run.py:355-388`, `:495-530`; `_output.py:184-195`; `test_run.py:215-235` | - |
| B | P8 | Item 8, full gate | See P8 below | Mediator |

Read only, for the rows above:

- P3: `_run.py:232-300`; `_config.py:316-330`; `paths.py:79-100`; `test_signals.py:286-610`;
  `test_output.py:79-97`; `conftest.py:59-110`; `test_run.py:355-380`.
- P4: `_core.py:496-600`, `:1005-1060`; `_flags.py`; `options.py:1-60`, `:154-222`;
  `test_core.py:120-180`, `:441-475`, `:587-610`; click `core.py:1401-1415`, `:2730-2780`.
- P6: `_core.py:45-130`, `:597-622`, `:975-1003`; `_run.py:249-290`, `:436-447`;
  `testing.py:52-120`.
- P8: README & coverage by Grep; CHANGELOG `:1-40`; `roadmap.md`; template
  `standard-cli.md:120-130`.

**Stops:**

- **S1, fit report:** `check()` runs on scratch clones of dkais and pkgdx `main` and on a generated
  `cli=True` project. The findings must equal the consumer predictions below exactly.
- **S3, a manual check by you:**
  - A real Ctrl-C during `recv` inside `ctx.cleanup`, in Windows Terminal and in WSL. This also
    covers the transcripts owed from 0.6.
  - `prog > NUL` picks `plain`.
  - Git Bash `--token-file - </dev/null` reports that the secret is empty.

  The agent leaves a demo script in the scratchpad and gives you the `!` commands to run.
- **S6, a manual check by you:** `--help` bold in Windows Terminal, plain with `| more`, `> file` and
  `TERM=dumb`, and in WSL.

**Gate, run every phase:**

- `uv run pytest -q --no-header --tb=short -x 2>&1 | tail -15`
- `just coverage | tail -8`, at 90% or more
- `uv run mypy --config-file mypy.ini --python-version 3.11 | tail -5`, and again with `3.14`
- `uv run prek run --all-files 2>&1 | tail -15`

## Consumers: when each needs updating

**Nothing changes during P1-P8.** Every consumer pins `~=0.6.0`, which excludes 0.7.0. Unlike 0.4-0.6,
0.7 **adds kit rules and changes help output**, so raising the pin is a real update point.

**Predicted on the 0.7 wheel** (verified at S1 and again in the evaluation):

| Consumer | New kit findings | Failing tests |
| --- | --- | --- |
| pkgdx `main` | 0 | 0 |
| dkais `main` | 1: `ARG-3 dkais download` (`-j`, `_cli.py:328-335`) | 1: `test_cli.py:879-881` |
| template (generated `cli=True`) | 0 | 0 |
| template repo | - | 1: `tests/test_template.py:265`, when the pin is raised |

**Update order:**

| When | pkgdx | template | dkais | cotravel |
| --- | --- | --- | --- | --- |
| P8 / evaluation | Scratch clone | Generated project | Scratch clone | - |
| After pyclig 0.7.0 | **1st:** pin, release 0.12.0 | - | - | - |
| After pkgdx 0.12.0 | - | **2nd:** see below | **3rd:** see below | **4th:** re-lock |
| After the template release | Copier update | - | Copier update | Copier update |

Pin edits:

- **pkgdx:** `pyproject.toml:30` `pyclig~=0.7.0`.
- **template:** `pyproject.toml.jinja:23` `pyclig~=0.7.0`, `:27` `pkgdx~=0.12`;
  `test_template.py:265`; `pyproject.toml:45`; the `standard-cli.md` amendment; release.
- **dkais:** `pyproject.toml:29` `pyclig~=0.7.0`, `:36` `pkgdx~=0.12`; `test_cli.py:881`
  `ignore={"ARG-3": "-j/--jobs as in make -j"}`, or rename the short; re-lock.
- **cotravel:** re-lock `develop`.

**Why this order:**

- pkgdx 0.11.x requires `pyclig~=0.6.0`. A project on `pyclig~=0.7.0` with `pkgdx~=0.11` therefore
  resolves only once pkgdx 0.12 exists.
- Raising the floor to `~=0.12` stops the resolver from falling back silently to pkgdx 0.7.0, whose
  `pyclig~=0.2` also accepts 0.7.
- Template before dkais, so dkais's Copier update matches.

**Also noted, not blocking:**

- cotravel `main` lags `develop` (`pkgdx~=0.7`, no tags).
- dkais's lock holds pkgdx 0.11.0.
- Optional adoption later: dkais `ctx.cleanup` around S3 I/O for INT-5, and `docs=`. For dkais's
  `-j`, choose between `ignore=` and a new short.

**Again at 1.0.0:** the same chain (`~=1.0`, pkgdx 0.13 or 1.0). After that, a bare `assert_conforms`
breaks on any minor release that adds a rule, which the freeze policy must address.

## Verification (me, as mediator and evaluator)

1. **Gate** on Python 3.11, 3.13 and 3.14.
2. **Reversion:** in a scratch worktree, revert each feature commit's `src/` hunk and confirm its
   tests fail. Name any invariant guards that pass by design.
3. **Kit:**
   - the S1 predictions are exact;
   - no callback runs without samples;
   - every emitted ID is a coverage row;
   - `adv` gained only ARG-3.
4. **By real subprocess:**
   - INT-5 timings on Windows 3.11 and 3.14, and on WSL;
   - no ESC codes on a pipe, with `TERM=dumb` or in a usage error;
   - `dkais list -v` prints the version;
   - no `DeprecationWarning:`;
   - the ROB-9 matrix;
   - one pre-filled GitHub URL and one GitLab URL opened, but not submitted.
5. **Design rules:**
   - `-X importtime -c "import pyclig"` loads none of `importlib.metadata`, `rich.traceback`,
     `rich.logging`, `_conformance`, `socket`, `urllib` or `platform`;
   - no new runtime dependency;
   - no markup parsing;
   - `inspect.signature` over `__all__`, `options` and `testing` is a pure addition compared with 0.6.0.
6. **Integration:**
   - scratch clones of dkais, pkgdx and a generated project, run on a wheel of the branch
     (`SETUPTOOLS_SCM_PRETEND_VERSION=0.7.0`), fail exactly as predicted and pass after the
     predicted edit;
   - pkgdx 0.7.0 from PyPI still runs on the branch.
7. **Timing:** median of 15 runs for `import`, `--help` and `-v` against 0.6.0. More than +10 ms on
   `--help` blocks the release.
8. **Coverage:** no row is left `gap` or `partial` unless it is owned `out`.
9. **Write-up:** I write "Round 7" in `docs/evaluation.md`, in round 6's format: a verdict per row
   with its evidence test, departures, defects found and what remains. I also draft the consumer
   transition issues, unfiled. Any missed prediction blocks the release until it is explained, and
   results are reported as found, failures included.

**You:** S3 and S6, the template amendment, then the PR, the 0.7.0 release and the consumer
sequence, each on your say-so.

## Appendix - 1.0.0 freeze candidates (planned after the 0.7 evaluation)

- Export the private types used in public signatures: `Format`, `Errors`, `ConfigError` and `Level`.
- Fix the name clash between `pyclig.confirm` and `options.confirm`, and make the factory keyword
  order consistent (`options.timeout` vs `output`/`port`/`user`).
- Kit stability policy: new rules only in minor releases, listed in the CHANGELOG, or an opt-in such
  as `since=`. Add scoped ignore keys such as `"ARG-3 dkais download"`.
- A SemVer statement on what counts as API (help layout and message wording do not), Development
  Status 5, and the support floors for Python, click and rich.
