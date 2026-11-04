# Plan - pyclig 0.4.0: output and feedback

## Context

`docs/roadmap.md` puts "0.4 - output and feedback" next. dkais & pkgdx still hand-roll format
switching, state rows, gated spinners and failure reporting, and `docs/clig-coverage.md` lists
those rules as `gap` or `partial`. 0.4 adds the primitives to close them. It is additive: nothing
should break in a consumer except the version pin, which the integration phase tests.

Decisions taken:

- Branch `feat/output-feedback` from `origin/develop` at `76dba75`. `chore/copier-0.4.0` is merged
  there, and into `origin/develop` of pkgdx & dkais & cotravel (checked 4 November 2026).
- ROB-5 moves to 0.6 as `partial`.
- `help` works but is not listed under `COMMANDS:`.
- A fresh Fable agent evaluates, separate from the Fable implementer.

Defaults, overridable at approval:

- OUT-5's owner changes from `check` to `interface`: the kit cannot judge "brief".
- ERR-3 ships no raising form: no consumer raises grouped errors.
- `emit` JSON uses `default=str`, for parity with plain's `str()`.
- `summary` has a fixed mark, with no `mark=` until pkgdx asks.
- SUB-3 stays `partial`: using one format across subcommands remains the app's choice.
- No new kit check, so consumers get no new findings.

Scope of authority: local commits on the feature branch only. No push, PR, tag, release or filed
issue without a separate ask. Consumer repos are read-only and are tested as scratch clones.
Immutable guidance files are proposed, not edited.

## Agents and context budget

Fable 5.1 has a 1M context window and 128K output per response. The whole context is re-sent every
turn, so cost and focus degrade long before the limit, and compaction is lossy. Calibration from
this session's read-only agents: Explore ~100k, Plan ~160k. Budgets are therefore well under 1M:

| Agent | Work | Target | Hand off at |
| --- | --- | --- | --- |
| Fable implementer | P1-P7 | ~350k | 500k |
| Fable evaluator (fresh) | P8 & evaluation | ~200k | 400k |

Handover: I write this plan to `docs/plan-0.4.0.md` (a working document without frontmatter, like
`plan-0.3.0.md`) as the first commit. The agent's brief is then that file plus `CLAUDE.md`, not a
pasted transcript. Finished work is recorded in `git log`, one commit per item, so if an agent
crosses its hand-off line I start a new one from the plan & the log. I read the token count on
each completion notice, and continue the same agent with SendMessage only below that line.

Rules for both agents:

- Read only the ranges each phase lists. Grep first, then Read with offset & limit. Never read
  `_core.py` or a whole test file. Don't re-read a file just edited.
- Filter output: `uv run pytest -q --no-header --tb=short -x tests/test_output.py 2>&1 | tail -15`;
  mypy `| tail -5`; prek `| tail -15`; `just coverage | tail -8`.
- Full gate once per phase, not per edit.
- No sub-subagents. Reports back to me stay under 150 words, with failures quoted.
- Stop and report at a contradiction with this plan, rather than improvising around it.

## Design

Existing primitives take the console first, then keyword-only arguments (`_output.py:13`). New ones
follow that, except `ctx.emit` & `ctx.pager`, which need the run's format. All are additive.

### Item 1 - `ctx.emit` (OUT-2, OUT-4 `done`; SUB-3 wider evidence)

```python
def emit(self, records: Iterable[Mapping[str, object]], *,
         table: Callable[[], "Table"] | None = None,
         caption: str | None = None) -> None
```

| Format | Output | Caption |
| --- | --- | --- |
| `json` | `json.dumps(list, indent=2, default=str)` by `click.echo(file=out.file)` | dropped |
| `plain` | TSV, no header, columns from the first record's keys | `info(err)` |
| `human` | `table()` or a default `SIMPLE_HEAD` table | set as `.caption` |

- Plain must use `click.echo`: Rich expands tabs on every print path (verified).
- Fields: `None` to `""`, bools to `true`/`false`, `[\t\n]+` to one space, missing key to `""`.
- Empty: JSON `[]`; plain nothing; human skips the table and sends the caption to `info`.
- The factory exists because dkais cells depend on other fields (`n/days`). It also keeps
  `rich.table` lazy. `json`, `rich.table` & `rich.box` import inside the function.

### Item 2 - state rows & summary (OUT-7, OUT-5 `done`)

```python
def row(console: Console, *, mark: Text | str, label: str,
        detail: Text | str = "", width: int = 0, essential: bool = False) -> None
def summary(console: Console, *, message: str, failed: bool = False) -> None
```

- `row`: one atomic, never-wrapped line, padded by cell length; dropped when quiet unless
  `essential`. Callers pass an already padded `mark` for a fixed column. A caller's `Text` is not
  sanitised, as with `hanging(head=)`: say so in the docstring.
- `summary`: `✓` or `!`; wraps on a terminal, one line otherwise (not `hanging`, which wraps off a
  TTY); dropped when quiet unless `failed`. `-q` marks only `err`, so a summary on `ctx.out` stays.

### Item 3 - status & progress (OUT-14, ROB-3 `done`; ROB-5 `partial`, moved to 0.6)

```python
def status(console: Console, *, message: str) -> ContextManager[None]
def progress(console: Console, *, columns: Sequence["str | ProgressColumn"] = (),
             **kwargs: Any) -> "Progress"
```

- `status`: a no-op when not interactive, else `console.status(_text(message), spinner="dots")`.
- `progress`: a real Rich `Progress` with `disable=not console.is_interactive` and `transient=True`
  by default. Default columns use `TextColumn("{task.description}", markup=False)`, because Rich's
  defaults parse markup and `[/b]` raises `MarkupError`. `rich.progress` imports inside the
  function: dkais `tests/test_cli.py:708` asserts it stays off fast paths.
- `columns` is keyword-only, a change from the design draft, to keep the module's rule.

### Item 4 - next-step hint (OUT-9 `done`)

Export the existing `_output.hint` as `pyclig.hint`: kept with `-q`. A success nudge uses `info`,
dropped with `-q`. No new primitive.

### Item 5 - `help` (HELP-6, DOC-4 `done`)

No new public API. In `Group.resolve_command` (`_core.py:682`), when `args[0] == "help"`, the parse
is not resilient and `self.get_command(ctx, "help") is None`:

- Walk the non-dash names with `resolve_command`, which reuses click's errors & suggestions. Build
  each child with `sub.context_class(sub, info_name=name, parent=cur, **sub.context_settings)`.
- Echo the help and `ctx.exit()`, as `_help_if_asked` (`_core.py:263`) does.

| Case | Result |
| --- | --- |
| `help`, including an empty group | Full help, no callback |
| `help grp leaf`, `-d help req`, `help -d req` | That command's help, exit 0 |
| `grp help leaf` | Help; the root callback runs, as with `grp leaf --help` |
| `help nosuch`, `help req x` | Usage error, exit 2 |
| App's own `help`, or a root positional | The app wins |
| Tab completion | Not intercepted |

Never in `.commands`, so the kit's walk & `COMMANDS:` are unchanged. Groups only: a standalone
`pyclig.command()` has no subcommands to name. Document that a required root option errors first.

### Item 6 - pager (OUT-19 `done`; kept after P6's check, opt-in on Windows)

```python
@contextlib.contextmanager
def pager(self) -> Iterator[None]
```

- `with ctx.pager(): ctx.emit(rows)`. No `pager=` on `emit`. A no-op unless `ctx.format == "human"`.
- `ctx.out.pager(pager=_ClickPager(...), styles=True)`. `_ClickPager.show` calls
  `click.echo_via_pager(content.rstrip("\n"), color=...)`, as click adds its own newline.
- Click supplies only `LESS=-R`, so set `LESS=-FIRX` in `os.environ` for the call, when unset.
- P6 outcome: `more` garbles UTF-8 & cannot scroll, so `ctx.pager` never defaults to it. On
  Windows with `PAGER` blank the block prints directly. Windows pages through click's temp file,
  which strips styles when `color` is `None`, so `color=True` is passed only when `PAGER` names
  `less` (any case, `.exe` or a quoted path) and pyclig itself set `LESS=-FIRX`; otherwise click
  decides. POSIX behaviour is unchanged.
- Hazards to document: `click.echo` inside the block bypasses the buffer, and output is held until
  the block ends. A raise skips the pager, but Rich flushes what was printed to STDOUT.

### Item 7 - grouped failures (ERR-3 `done`)

```python
def notice(console: Console, *, level: Level, message: str,
           items: Iterable[str] = ()) -> None
```

Header plus indented items in one `console.print`, so threads & live displays can't split them.
Kept with `-q`. A later `hint` carries the remedy, which keeps ERR-4 true. Split `hanging` into a
`Text`-returning helper plus the print.

### Bug found on the way

`_CONTROL` (`_output.py:30`) misses C1 codes, so `\x9b` (CSI) survives, contradicting the module
docstring & README. Widen it to include `\x80-\x9f`. `fix:` commit, first in P1.

## Phases

Show each new test failing before its change. Use local test CLIs, not new `sample_cli` commands,
so exact-set tests stay untouched. Each phase ends with its row in the gate below passing.

| Phase | Work | Read only | Stop |
| --- | --- | --- | --- |
| P1 | C1 fix, `hint`, `notice(items=)` | `_output.py`, `__init__.py`, `test_output.py:1-40` | - |
| P2 | `row`, `summary` | pkgdx `standards/_cli.py:24-62` for the fit | Report the fit |
| P3 | `status`, `progress` | `tests/test_init.py` | - |
| P4 | `emit` | `_core.py:60-122`, dkais `_cli.py:240-286` | Report the fit |
| P5 | `help` | `_core.py:263-280`, `:682-698`, `tests/test_core.py:1-40` | - |
| P6 | `pager` | `_core.py:60-122`, `click/_termui_impl.py:455-470`, `:570-590` | **Maintainer** |
| P7 | Docs & full gate | README:148-172, roadmap, CHANGELOG head, coverage by Grep | Evaluator |
| P8 | Consumer integration, no pyclig changes | `evaluation.md:183-243` | **Maintainer** |

The behaviours above are the requirement; test names are the implementer's. Tests must cover the
table or bullets of each item, including `-q`, off-TTY, markup such as `[/b]` and control codes.

Fit reports (not stops unless they fail):

- P2: a sketch replacing pkgdx `_row` must produce its current line byte for byte.
- P4: a sketch replacing dkais `list` must match plain & JSON byte for byte, including the STDERR
  caption.

P6 manual check: the implementer leaves a demo script in the scratchpad and gives me the command.
You run it with `!` in Windows Terminal and WSL, on long & short output, with `PAGER` unset and set
to `less`. If `more` garbles it badly, ship 0.4 without the pager.

P6 result: WSL with `less` is perfect; Git's `less.exe` through `PAGER` works on Windows (`-FIRX`,
UTF-8, `q` restores the prompt); `more` garbles UTF-8 and cannot scroll, which pyclig cannot fix.
Decision: keep the pager and never default to `more`, replacing the fallback above.

P7 edits:

- `README.md` output sections; `CHANGELOG.md` `[Unreleased]`.
- `clig-coverage.md`: "as of 0.4.0", the rows above, a "Delivered in 0.4" section after line 249.
- `roadmap.md`: mark 0.4 delivered, move ROB-5 to 0.6, and fix line 51 to "Every row `done`, or
  owned `out`".
- Add `rich.progress`, `rich.table`, `rich.box` to the forbidden list in `test_init.py`.
- Draft, don't apply: `standard-cli.md` amendment (lines 72-73, use `ctx.emit`), to be made in the
  Copier template first.

Gate, every phase:

- `uv run pytest -q`
- `just coverage` at 90% or more
- `uv run mypy --config-file mypy.ini --python-version 3.11`, and again with `3.14`
- `uv run prek run --all-files`

## Consumers: when each needs updating

**No consumer changes while P1-P7 run.** Every consumer pins `pyclig~=0.3.0`, so nothing moves until
pyclig 0.4.0 is on PyPI and they raise the pin. That raise is the only predicted MUST.

| When | pkgdx | template | dkais | cotravel |
| --- | --- | --- | --- | --- |
| P8 (pre-release) | Scratch clone | Scratch clone | Scratch clone | - |
| After pyclig 0.4.0 | **1st:** `pyclig~=0.4.0`, release 0.9.0 | - | - | - |
| After pkgdx 0.9.0 | - | **2nd:** see below | **3rd:** see below | Re-lock |
| After the template release | Copier update | - | Copier update | Copier update |

- **template** `copier-python-package`: `pyproject.toml.jinja:23`, `tests/test_template.py:265`,
  `pkgdx` dev pin, `standard-cli.md`.
- **dkais**: `pyclig~=0.4.0` **and** `pkgdx~=0.9`, then a lock check.

Why this order, from PyPI metadata checked today:

- pkgdx 0.7.0 requires `pyclig~=0.2`, which accepts 0.4. pkgdx 0.8.0 requires `pyclig~=0.3.0`.
- So dkais on `pyclig~=0.4.0` with `pkgdx~=0.7` still resolves, by silently falling back to pkgdx
  0.7.0, the version its lock holds now. Hence pkgdx first and raising dkais's lower bound.
- The template's `pkgdx~=0.7` dev pin reaches generated projects the same way.

Not affected:

- cotravel has no pyclig code (`cli: false`); it re-locks to pick up pkgdx 0.9.
- `pkgdx-consumer`, `mpctraj` & `dataclocklib` use old pkgdx with no pyclig dependency.

Optional adoption, in later consumer PRs:

| Primitive | pkgdx | dkais | Cost |
| --- | --- | --- | --- |
| `emit` | - | `_cli.py:246-285`, `_tsv` goes | None if byte-identical |
| `row`, `summary` | `_row`, closing line, `quiet` | `summarise` human branch | pkgdx ledger tests |
| `status`, `progress` | `_cli.py:223-227` | `_report.py:209-236` | pkgdx spinner test |
| `hint`, `notice(items=)` | `_note` | grouped failures | dkais `test_cli.py:391-392` |
| `ctx.pager` | - | `list` | Manual check only |
| `help` | Automatic | Automatic | None |

## Verification

**Evaluator (P8), fresh Fable agent.** Brief: this plan & `git diff 76dba75...HEAD`. It is told not
to trust the implementer's summary. Consumer scratch clones start from each `origin/develop`.

1. Gate on Python 3.11, 3.13 & 3.14.
2. Reversion check: in a scratch worktree, revert each feature commit's `src/` hunk and confirm its
   tests fail.
3. Behaviour by real subprocess: `| cut -f1` keeps tabs; `--json` parses; `FORCE_COLOR=1` on a pipe
   stays plain; `-q`; `[/b]`, `:warning:` & `\x9b` in input; `help` per the Item 5 table.
4. Design rules: no new dependency, `-X importtime` shows no `rich.progress`, `rich.table`,
   `rich.live`, `rich.traceback`, `rich.logging`, `importlib.metadata` or `_conformance`.
5. Scratch clones on a wheel of the branch:
   - dkais & pkgdx suites unmodified: predicted 0 failures; `assert_conforms` clean.
   - A generated `cli=True` project: `test_main` passes, `prog help` works.
   - `dkais help list`, `pkgdx help init`, `dkais list --start 2026-10 | cut -f1` (one public bucket
     read, as in round 3).
   - pkgdx 0.7.0 from PyPI on the branch, to prove the fallback case above runs.
   - Median of 15 for `--help`, `-v` & `import` against 0.3.0; `test_fast_paths_skip_heavy_imports`.
6. Writes "Round 4" in `docs/evaluation.md`, in the format of round 3: per-row verdict with evidence
   test, departures, remaining. Drafts transition issues with predicted failures, not filed.

A prediction that misses blocks the release until explained.

**Me, after the evaluator.** Re-run the gate & read the diff myself, spot-check three of its
verdicts, then report results as found, including any failure.

**You.** The P6 manual check, the `standard-cli.md` amendment, then PR, release 0.4.0 & the consumer
sequence, each on your say-so.
