# Plan - pyclig 0.6.0: robustness and signals

## Context

The next roadmap item is "0.6 - robustness and signals" (`docs/roadmap.md:40-49`). Its rows in
`docs/clig-coverage.md` are:

- `gap`: ERR-7, ARG-11b, ROB-6, SIG-2, SIG-3;
- `partial`: OUT-18, INT-5, ROB-5, SIG-1.

Two things are missing today. pyclig installs no signal handler: Ctrl-C is reported only after
the stack unwinds (exit 130), and SIGTERM kills the run silently. Logging touches only the
package logger, never the root logger or `warnings`. pkgdx and dkais hand-roll interrupt
messages, teardown and timeouts. 0.6 adds the per-run signal handling, a bounded clean-up, root
and warning routing, a debug log file, held logs, severe confirmation and a timeout factory. It
is additive, and only the signal handling changes behaviour without being opted into.

Process mirrors `docs/plan-0.5.0.md`. Three read-only Explore agents (internals, process,
consumers) and one Opus Plan agent produced this design, using measured signal probes on Windows
3.11, 3.13 and 3.14.

Decisions taken (with you, 7 November 2026):

- **Signals:** automatic and per run, restored afterwards. SIGTERM exits 143
  (`ExitCode.TERMINATE`); Ctrl-C and Ctrl-Break exit 130.
- **Clean-up:** a hard exit (flush, then `os._exit`) on a second signal or on timeout, driven by
  a watcher thread that runs only while a `ctx.cleanup` block is active. The default timeout is
  10 s, counted from the interrupt.
- **Logging:**
  - OUT-18 takes over root records and `warnings.showwarning` only when the root logger has no
    handlers.
  - ERR-7 is `<PROG>_LOG_FILE` only, appended, with no run flag.
- **Confirmation:** a separate `pyclig.confirm_name` plus `options.confirm()`, which `--force`
  never bypasses. `confirm` is unchanged.
- **All seven items ship in 0.6.0.**
- **Branch:** `feat/robustness-signals` from `origin/develop` `69ae9ed`, whose tree is the same
  as `v0.5.0` (`00764aa`).

Defaults, overridable at the P3 stop:

- INT-5 stays `partial`. A blocking Windows call delays Ctrl-C, and no whole-run watcher is added.
- `ctx.logs_on_failure` (ROB-5) is opt-in, replays only when an `Exception` leaves the block, and
  is a no-op under `-d`.
- `options.timeout` defaults to 30.0 s with no short flag.
- No new kit check, so consumers get 0 new findings.

Scope of authority: local commits on `feat/robustness-signals` only. No push, PR, tag, release
or filed issue without a separate ask. Consumer repos are read-only and are tested as scratch
clones. The immutable `standard-cli.md` and `toolchain-logging.md` are drafted, not edited.

## Agents, models and context budget

Each agent's model and effort follow the difficulty of its phases. Every brief is
`docs/plan-0.6.0.md` plus `CLAUDE.md` plus the phase to run, never a transcript.

| Agent | Phases | Model / effort | Target | Hand off at |
| --- | --- | --- | --- | --- |
| A, implementer | P1: two small factories | sonnet / medium | ~80k | 200k |
| B, implementer | P2, P3: signals, threads, Windows | fable / high | ~290k | 400k (1) |
| C, implementer | P4-P6: root, file, held logs | opus / medium | ~200k | 300k (2) |
| E, evaluator | P8, Round 6 (fresh) | fable / high | ~250k | 400k |

1. Past it, a fresh fable runs P3 from the plan, the log and the spike notes.
2. Past it, P7 goes to a sonnet / medium agent.

How I run them:

- One phase per message: launch the agent for its first phase, then continue it with SendMessage.
- Each completion notice carries a token count. Past the hand-off line, start a fresh agent from
  the plan and `git log`, never a continuation.
- One commit per item, so `git log` is the progress record.
- Before the next phase, I check each phase's gate output and diff stat.

Rules put in every brief (from `plan-0.5.0.md:76-87`):

- Read only the ranges the phase lists. Grep first, then Read with offset and limit. Never read
  `_core.py` or a whole test file, and don't re-read a file just edited.
- Filter output:
  - pytest: `uv run pytest -q --no-header --tb=short -x <file> 2>&1 | tail -15`
  - mypy: `| tail -5`
  - prek: `| tail -15`
  - coverage: `just coverage | tail -8`
- Run the full gate once per phase.
- No sub-subagents. Reports stay under 150 words and quote any failure verbatim.
- At a contradiction with the plan, stop and report; don't improvise around it.

## Design

New private module `src/pyclig/_signals.py`. It imports `signal` and `socket` inside its
functions only, so nothing changes at import. Tests go in `tests/test_signals.py`, plus additions
to the existing `test_logging.py`, `test_options.py` and `test_core.py`, using local test CLIs.

### Item 1 - Per-run signals (SIG-1 `done`, auto; INT-5 `partial`, new evidence)

**Where it runs:** `_signals.scoped(state)` is the outermost `with` in `Command.main`
(`_core.py:641`) and in `pyclig.run` (`:966`). It is modelled on `_logging.scoped`
(`_logging.py:182-200`).

- It acts on the main thread only.
- It saves the SIGINT, SIGTERM and (win32) SIGBREAK handlers and restores them in `finally`. A
  saved `None` becomes `SIG_DFL`.

**New `State` fields** (`_run.py:63-102`): `signal: int | None`, `announced: bool`,
`cleaning: int`.

| Signal | Action |
| --- | --- |
| First, outside `cleanup` | Notice (below), records it, raises `KeyboardInterrupt` |
| First, inside `cleanup` | Same notice plus the clean-up hint; does not raise (Item 2) |
| Later, outside a block | Raises `KeyboardInterrupt` again, with no second notice |
| While the runner is reporting the outcome | Exits at once with the code |

The notice ends the `^C` line on a terminal (SIGINT), then prints `warning: interrupted`
(SIGINT, SIGBREAK) or `warning: terminated` (SIGTERM).

**Runner:**

- `_interrupted(err)` (`_run.py:414-419`) becomes `_interrupted(state)`, used by `execute` and
  `_aborted` (`:422-437`).
- It prints only if the handler has not, and returns 143 for SIGTERM, otherwise 130.
- `ExitCode.TERMINATE = 143` is added in `_exit.py`.
- A `KeyboardInterrupt` raised by code (the `InterruptingInput` mocks, pkgdx's tests) still
  prints after unwinding, so `test_run.py:231-242` is unchanged.

**Windows:**

- `os.kill(pid, SIGTERM)` is `TerminateProcess`: exit 15 with no message. This is documented,
  not fixed.
- Ctrl-Break is the stop signal a program can catch there, and maps to 130.
- On 3.11-3.13 a blocked main thread delays both the notice and the `KeyboardInterrupt` equally,
  so the notice still comes before any clean-up.

**The P2 spike checks these first and records the results in the plan:**

- re-entry into Rich when the notice lands mid-print (fallback: print from a helper thread with
  a 0.5 s join);
- the `asyncio.Runner` fallback;
- mypy guarding `signal.SIGBREAK` with `sys.platform == "win32"`.

**P2 spike result:** Rich re-entry is safe: `Console._lock` is an `RLock`, so the handler's
`print` on `state.err` nests. Mid-render the notice lands first and the cut line is dropped; in
the write phase the in-flight line repeats, which the default handler causes too (the buffer is
left stale), so no helper thread is used. `asyncio.run` keeps a non-default SIGINT handler on
3.11-3.14: the interrupt leaves it at once, the task's `finally` runs and the proactor loop
resets its wakeup fd. mypy 3.11 and 3.14, win32 and linux, accept `signal.SIGBREAK` under
`sys.platform == "win32"`. `CTRL_BREAK_EVENT` reaches a `CREATE_NEW_PROCESS_GROUP` child on
3.11-3.14, but SIGBREAK never wakes a plain `socket.recv`, `time.sleep` or `Event.wait`, so the
Windows test child polls `recv` with a 0.1 s timeout. On WSL, SIGINT and SIGTERM interrupt a
plain `recv` at once.

### Item 2 - `ctx.cleanup(*, timeout: float | None = 10.0)` (SIG-2, SIG-3 `done`, interface)

A context manager on `Context`, next to `pager` (`_core.py:201-229`), that delegates to
`_signals.cleanup`.

| Situation | Outcome |
| --- | --- |
| Entered after an interrupt | Hint `cleaning up - press Ctrl-C again to skip`; timer starts |
| Signal during a block on the normal path | Notice and hint; the block finishes, then 130 or 143 |
| Another signal inside the block | `warning: clean-up skipped`; immediate exit 130 or 143 |
| Timeout | `warning: clean-up timed out after 10s`; immediate exit |
| Block raises | Propagates; the timer is cancelled |
| No interrupt, or not the main thread | Runs normally |

After SIGTERM the hint is just `cleaning up`.

**Watcher:** a daemon thread owns `signal.set_wakeup_fd` while the block is active, over
`os.pipe` on POSIX or `socket.socketpair` on Windows. It handles the second signal and the
timeout even while the main thread is blocked in `Thread.join` or `socket.recv`. To exit it:

- flushes STDOUT, STDERR and the log-file handler;
- prints through a helper thread with a join timeout;
- calls `_signals._exit(code)`, a patchable seam around `os._exit`.

**Edge cases:**

- If `set_wakeup_fd` returns a foreign fd, the watcher restores it and falls back to the Python
  handler.
- Nested blocks count depth, and the outermost block's timeout applies.

### Item 3 - Root records and warnings (OUT-18 `done`, auto)

This applies only when `logging.root.handlers` is empty at the start of the run.

- **Root handler:** `_logging` adds a marked root handler: `EventHandler` at WARNING, or the
  debug handler at NOTSET with `-d`. The root level is never changed, and only that handler is
  removed at the end.
- **Warnings:** `warnings.showwarning` is replaced for the run. The replacement emits a
  `py.warnings` record carrying the message only, with file and line kept on the record so `-d`
  shows them. The saved function is restored afterwards.
- **Not `logging.captureWarnings`:** it keeps global state and prints `file:line`, which OUT-18
  forbids by default.
- **Tests:** under pytest the root already has handlers (`log_cli=true`), so consumer caplog
  tests are untouched. pyclig's own tests use a fixture that empties the root handlers, plus
  `@pytest.mark.filterwarnings("default")`.

### Item 4 - `<PROG>_LOG_FILE` (ERR-7 `done`, owner becomes `auto`)

**Reading it:** `apply_environment` (`_run.py:132-149`) reads the variable into
`State.log_file`.

**The handler:** `configure` attaches a `FileHandler(path, "a", encoding="utf-8")` with
`DEBUG_FORMAT` to the package logger, and to the root logger when Item 3 applies.

- The package logger runs at DEBUG, with WARNING moved to the console handler's own level.
- The handler survives the `-d` reconfigure (`_flags.py:111-116`).
- If the file can't be opened: `warning: cannot write the debug log to FILE: reason`, and the
  run continues.

**Failures:** `_failed` (`_run.py:440-470`) writes the traceback to the file. Exit 70 adds the
hint `debug log: FILE`.

**Clearing:** `LOG_FILE` is added to `testing._PREFIXED` (`testing.py:48`) and to the kit's
`_CLEARED` (`_conformance.py:53`).

### Item 5 - `ctx.logs_on_failure(*, level=logging.INFO)` (ROB-5 `done`, interface, opt-in)

**Inside the block:** the package logger is lowered to `level`, and the console handler stays at
WARNING. A held handler keeps records below WARNING (a deque of up to 1000).

**At the end:**

- On success the held records are dropped.
- If an `Exception` leaves the block, they are replayed through the console handler and the
  exception is re-raised, so `error:` still prints last.
- There is no replay for `Abort`, `Exit(0)` or `KeyboardInterrupt`.

**Flags and live displays:** it is a no-op under `-d`, and replayed info lines stay hidden under
`-q`. The docs say: raise to fail, and keep the block outside `progress` and `status`.

### Item 6 - Severe confirmation (ARG-11b `done`, interface)

The API is `pyclig.confirm_name(ctx, *, message, name, confirmed)` plus `options.confirm()`
(`--confirm NAME`, parameter `confirmed`). The factory is added to the `options.py:6-16` table and
to `__all__`.

| Case | Outcome |
| --- | --- |
| `--confirm=NAME` matches | Returns |
| `--confirm` mismatch | Usage error naming the expected name; exit 2 |
| Cannot prompt | `... - pass --confirm=NAME to proceed`; exit 2 (`_cannot_prompt`, `:319`) |
| Typed name matches | Returns (`Type 'NAME' to confirm:` on STDERR) |
| Typed mismatch, empty answer, EOF | `error: aborted`; exit 1 |
| Ctrl-C | 130 |

### Item 7 - `options.timeout(*, default=30.0, help=..., envvar=None)` (ROB-6 `done`, interface)

`--timeout SECONDS`, typed `FloatRange(min=0, min_open=True)`, with its default shown in help.
pyclig makes no network calls (FUT-6), so it wraps no client. The README shows passing the value
on to HTTP and botocore clients.

## Phases

Show each new test failing before its change. Every phase ends with the gate passing.

| Phase | Work | Agent | Stop |
| --- | --- | --- | --- |
| P0 | Branch, commit this plan as `docs/plan-0.6.0.md` (no frontmatter, like 0.3-0.5) | me | - |
| P1 | Item 6, then Item 7 (two commits) | A | Kit report |
| P2 | Spike (notes appended to the plan), then Item 1 | B | - |
| P3 | Item 2 | B | **Maintainer** |
| P4 | Item 3 | C | Fit report |
| P5 | Item 4 | C | - |
| P6 | Item 5 | C | Fit report |
| P7 | Docs and full gate | C or sonnet | Evaluator |
| P8 | Round 6 and consumer integration, no pyclig changes | E | **Maintainer** |

Read only, per phase (as of `69ae9ed`; Grep for the symbol first, since earlier phases shift lines):

- **P1:** `_core.py:271-323`; `options.py:1-38`, `:101-113`, `:222-300`; `_conformance.py:36-48`;
  `tests/test_core.py:930-950`; `tests/test_options.py:1-60`.
- **P2:** `_run.py:1-26`, `:63-113`, `:132-150`, `:351-437`; `_core.py:597-686`, `:930-969`;
  `_exit.py`; `_logging.py:182-200`; `tests/conftest.py:31-60`, `:115-135`;
  `tests/test_run.py:231-256`; `tests/test_init.py:1-45`.
- **P3:** `_core.py:70-100`, `:201-240`; `_signals.py`; `_output.py:146-193`; a fresh dkais clone
  (Grep `shutdown`).
- **P4:** `_logging.py`; `_core.py:640-656`, `:964-969`; `pyproject.toml:65-71`; pkgdx
  `tests/test_core.py:495-512`, `tests/test_init.py:12-35`.
- **P5:** `_logging.py`; `_run.py:132-150`, `:440-470`; `_flags.py:111-117`; `testing.py:39-50`,
  `:116-121`; `_conformance.py:50-55`.
- **P6:** `_logging.py`; `_core.py:162-230`; `_output.py:49-72`, `:173-193`, `:266-300`; dkais
  `_report.py` (Grep `is_interactive`).
- **P7:** README `:14-17`, `:82-142`, `:243-277`, `:330-396`; CHANGELOG `:1-35`; roadmap `:40-54`;
  coverage rows by Grep; `standard-cli.md:20-27`, `:158-162`.
- **P8:** `evaluation.md:363-400`, `:486-492`.

Signal tests:

- In-process: `signal.raise_signal`, with `_signals._exit` patched.
- Subprocess: `-c` programs that print a "ready" line.
  - POSIX sends SIGINT and SIGTERM with `send_signal`.
  - Windows starts the child with `CREATE_NEW_PROCESS_GROUP` and sends `CTRL_BREAK_EVENT`.
  - Each child blocks in `socket.recv`, which blocks on every version. Windows CI runs on 3.14
    only.

Fit reports, which stop only if they fail:

- **P1:** `assert_conforms` is clean on a CLI using `options.confirm()` and `options.timeout()`.
- **P4:** the pkgdx and dkais suites pass unmodified on the branch, and a dkais dry run lists any
  newly visible third-party warnings.
- **P6:** dkais-style progress inside `logs_on_failure` on a WSL `script` pty is not garbled.

**P3 stop:** you see the signal matrix on Windows 3.11 and 3.14 and on WSL, and the fit on a
fresh dkais clone (the `process` clean-up wrapped in `ctx.cleanup`). You confirm or override the
defaults under Context. The matrix covers:

- the notice at once;
- the second-signal skip and the timeout;
- SIGTERM exiting 143 and Ctrl-Break exiting 130.

P7 edits:

- **`README.md`:**
  - a "Signals & clean-up" section, and 143 under Errors & exit codes;
  - the logging additions (root and warnings, `LOG_FILE`, `logs_on_failure`);
  - `confirm_name`, `options.confirm` and `options.timeout`;
  - the stale pin at `:16` (`pyclig~=0.3.0`) corrected to `~=0.6.0`.
- **`CHANGELOG.md`:** a `[0.6.0]` entry; date `[0.5.0]` as 2026-11-06 (the tag date).
- **`clig-coverage.md`:** "as of 0.6.0", the rows below, and a "Delivered in 0.6.0" section.
- **`roadmap.md`:** mark 0.6 delivered.
- **`test_init.py`:** add `socket` to the forbidden imports. Probe that after import SIGINT is
  `default_int_handler`, SIGTERM is `SIG_DFL`, and `showwarning` is the original.
- **Drafted, not applied:** the `standard-cli.md` amendment (143, `ctx.cleanup`, `--confirm`) and
  the `toolchain-logging.md` amendment (root handler, warnings, `LOG_FILE`). Both go to the
  Copier template first.

Coverage after 0.6:

| Rows | Status | Owner |
| --- | --- | --- |
| SIG-1, OUT-18, ERR-7 | done | auto |
| SIG-2, SIG-3, ROB-5, ROB-6, ARG-11b | done | interface |
| INT-5 | partial: a blocking Windows call delays Ctrl-C | interface |

Gate, every phase:

- `uv run pytest -q`
- `just coverage` at 90% or more
- `uv run mypy --config-file mypy.ini --python-version 3.11`, and again with `3.14`
- `uv run prek run --all-files`

Critical files:

- `src/pyclig/_run.py`: `State`, `apply_environment`, `execute`, `_interrupted`, `_aborted`,
  `_failed`.
- `src/pyclig/_core.py`: `Context` (`pager` as the pattern), `confirm`/`_cannot_prompt`, `main`,
  `invoke`, `run`.
- `src/pyclig/_logging.py`: `configure`, `scoped`.
- `src/pyclig/options.py`, `src/pyclig/_exit.py`, `src/pyclig/testing.py:48`,
  `src/pyclig/_conformance.py`, `src/pyclig/__init__.py` (exports `confirm_name`).
- New: `src/pyclig/_signals.py`, `tests/test_signals.py`.

## Consumers: when each needs updating

**Now, independent of 0.6.** The 0.5 cycle is merged to `develop` but not released, and every
local clone is stale (`git pull` before use):

- **dkais** `develop`: `pyclig~=0.5.0`, `pkgdx~=0.10`. `main` still has `pyclig~=0.4.0` and
  `pkgdx~=0.9`, 4 commits behind.
- **cotravel** `develop`: `pkgdx~=0.10`. `main` still has `pkgdx~=0.7`, 8 commits behind.
- The `develop` to `main` releases are yours to make whenever you like. The 0.6 pin raises
  stack on `develop` either way.

**While P0-P7 run: no consumer changes.** pkgdx and the template pin `~=0.5.0`, and dkais
`develop` does too, all of which exclude 0.6.0. The changes they must make are pin raises only,
and 0 test failures are predicted.

| When | pkgdx (`gitlab/pkgdx`) | template (`copier-python-package`) | dkais | cotravel |
| --- | --- | --- | --- | --- |
| P8 (pre-release) | Scratch clone | Generated `cli=True` project | Fresh clone of `develop` | - |
| After pyclig 0.6.0 on PyPI | **1st:** MR `pyclig~=0.6.0`, release 0.11.0 | - | - | - |
| After pkgdx 0.11.0 tag | - | **2nd:** pins, below | **3rd:** both pins | **4th:** re-lock |
| After the template release | Copier | - | Copier | Copier |

- **template:** `pyproject.toml.jinja` `pyclig~=0.6.0` & `pkgdx~=0.11`, `tests/test_template.py`,
  its own dev pin, and the `standard-cli.md` and `toolchain-logging.md` amendments; release.
- **dkais:** `pyclig~=0.6.0` **and** `pkgdx~=0.11`, then a lock check.
- **cotravel:** `pkgdx~=0.11`, re-lock.

- **Why this order:** pkgdx 0.10 requires `pyclig~=0.5.0`. A consumer on 0.6 that still admits
  pkgdx 0.10 fails to resolve, loudly. An old pkgdx (0.7.0, `pyclig~=0.2`) would fall back
  silently, so every consumer raises the pkgdx floor. This is re-checked against PyPI metadata
  in P8.
- **Who does what:** I stop after the pkgdx MR and wait for your tag. You merge and tag at every
  step.
- **pkgdx release MR:** `test_prek_revision_update` is expected to fail locally until the tag
  exists.

Optional adoption, in later consumer PRs:

- **pkgdx:** hooks get signal handling automatically through `pyclig.run`. Reword
  `standards/_cli.py:245-250`, whose own "interrupted" line now doubles pyclig's notice.
- **dkais:**
  - wrap `_download.py:150` and `_cli.py:605-606` (`shutdown`, `clean_stale`) in `ctx.cleanup`;
  - replace `read_timeout=60` (`_s3.py:125`) with `options.timeout(default=60)`;
  - use `logs_on_failure` around downloads;
  - drop its own "Interrupted" warnings. It still needs `_POLL_SECONDS` on Windows.
- **Visible change for both:** third-party warnings (urllib3, botocore) now print as `warning:`
  lines in real runs.

## Verification

**Evaluator (P8), fresh fable / high.**

- Its brief is this plan, `CLAUDE.md` and `git diff 69ae9ed...HEAD`. It does not trust the
  implementers' summaries.
- It works on a wheel of the branch and on scratch clones, installed into a venv holding only
  click, rich and pytest.

1. Gate on Python 3.11, 3.13 and 3.14. Reversion check: revert each feature commit's `src/` hunk
   in a scratch worktree and confirm its tests fail.
2. Signals, by real subprocess on WSL and on Windows 3.11 and 3.14:
   - the notice is timestamped before the clean-up's first output, exit 130;
   - SIGTERM gives `terminated` and 143, Ctrl-Break gives 130;
   - a second signal exits within 100 ms with `clean-up skipped`;
   - the timeout bound holds to within +0.2 s;
   - a block stuck in `Thread.join` or `socket.recv` still exits;
   - Ctrl-C at a prompt prints one line;
   - Windows `os.kill(SIGTERM)` gives exit 15 with no message (documented);
   - a manual Ctrl-C in Windows Terminal and in WSL, transcripts kept.
3. Logs: a failure inside `logs_on_failure` prints the held lines before `error:`; success prints
   none; `-d` gives no duplicates; progress on a TTY is not garbled.
4. Root and warnings:
   - a third-party `warnings.warn` prints `warning: msg` with no path, and `-d` adds the location;
   - a third-party logger's WARNING prints as a notice;
   - an app using `basicConfig` is unchanged;
   - the pkgdx caplog tests pass.
5. `<PROG>_LOG_FILE`: the file gets the DEBUG records and the exit-70 traceback, and the hint names
   the file. An unwritable path warns and the run continues.
6. Import and run state: no `socket`, `rich.traceback`, `rich.logging`, `importlib.metadata` or
   `_conformance` on `import pyclig` (`-X importtime`), and no `socket` on `--help` or `-v`. After
   an in-process `invoke`, all of these are restored:
   - the signal handlers and the wakeup fd;
   - `showwarning`;
   - the root handlers and the logger levels.
7. Consumers on the wheel:
   - the pkgdx and dkais suites pass unmodified, with 0 failures predicted;
   - `assert_conforms` is clean, and dkais `test_fast_paths_skip_heavy_imports` passes;
   - the generated template project passes `test_main`;
   - pkgdx 0.7.0 from PyPI still runs;
   - median of 15 runs for `--help`, `-v` and `import` against 0.5.0.
8. Writes "Round 6" in `docs/evaluation.md` in round 5's format:
   - tests table and a verdict per item with its evidence test;
   - defects, integration, departures and what remains.

   It also drafts the consumer transition issues with predicted failures, not filed. A prediction
   that misses blocks the release until it is explained.

**Fixes after evaluation:** `fix:` commits by agent C (or B, for signal defects), written up in
"Fixed after evaluation (0.6.0)" and re-checked by E (continued with SendMessage) on a rebuilt
wheel.

**Me, after the evaluator:**

- re-run the gate;
- read the diff;
- spot-check three verdicts;
- report results as found, failures included.

**You:**

- the P3 and P8 stops;
- the two guidance amendments;
- then the PR (`feat/robustness-signals` into `develop`, then `develop` into `main`) and the
  v0.6.0 tag;
- then the consumer sequence above, each on your say-so.
