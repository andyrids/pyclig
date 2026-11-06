---
context-hierarchy: Layer 3
context-hierarchy-role: Reference material
immutable: false
recommended-context-tokens: 2500
tags: [CLI, CLIG, coverage, conformance]
---

# CLIG coverage

Attribution: the rules paraphrase the [Command Line Interface Guidelines](https://clig.dev/) by
Aanand Prasad, Ben Firshman, Carl Tashian & Eva Parish, licensed
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). The wording is condensed; this
file is shared under the same licence.

CLIG is the requirement. Every actionable rule has a row here, and the IDs are the one namespace
shared by `pyclig.testing.assert_conforms`, `docs/roadmap.md` and the CHANGELOG. Status is as of
0.5.0; the roadmap says which release closes a gap. Evidence names the code or test that shows it,
so it stays true across line moves.

Status: `done` means pyclig delivers it, `done (click)` or `done (rich)` that a dependency does;
`partial` means part of the rule; `gap` means nothing yet.

Owner: `auto` pyclig does it with no application code; `interface` pyclig offers what the
application calls; `check` the application's job, which the kit can verify; `out` beyond a
library's reach.

## Basics

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| BAS-1 | Use a parser library | done (click) | `pyclig.group`, `pyclig.command` | auto |
| BAS-2 | Zero on success, non-zero on failure | done | `_run.execute`; kit probes | auto |
| BAS-3 | Map codes to the main failure modes | done | `exit_code` on `errors=` types | interface |
| BAS-4 | Output to STDOUT, machine-readable too | partial | `ctx.out`; kit: STDOUT clean | check |
| BAS-5 | Messages & errors to STDERR | done | `notice`, `EventHandler`; kit probes | auto |

## Help

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| HELP-1 | `-h` & `--help`, subcommands too | done | Root `Context` default; kit probes | auto |
| HELP-2 | Concise help when arguments are missing | done | `get_concise_help` | auto |
| HELP-3 | Concise help content | partial | No flag list; kit: flag help text | auto |
| HELP-4 | `-h` ignores whatever else is passed | done | `parse_args`, `resolve_command` | auto |
| HELP-5 | Don't overload `-h` | done | An app `-h` leaves help on `--help` only | check |
| HELP-6 | `help` & `help <command>` | done | `help [NAME...]` on every group | auto |
| HELP-7 | Support path in the top-level help | partial | `epilog`; crash hint has the URL | auto |
| HELP-8 | Link help to web docs, per subcommand | partial | `epilog` only | interface |
| HELP-9 | Lead with examples | done | `Command.format_help`; kit: `examples=` on the root | auto |
| HELP-10 | Examples build up, show output | partial | One-line examples only | check |
| HELP-11 | Cheat sheet or web page for many examples | gap | None | out |
| HELP-12 | Tutorial for complex integrations | gap | None | out |
| HELP-13 | Common flags & commands first | done | Definition order kept | check |
| HELP-14 | Bold headings, safe when piped | partial | Upper-case headings, no bold | auto |
| HELP-15 | Suggest a likely correction | done (click) | Did-you-mean, commands & options | auto |
| HELP-16 | Offer to run the correction | gap | Suggestion only | interface |
| HELP-17 | Never silently run the corrected command | done (click) | No abbreviations | auto |
| HELP-18 | Pipe expected, STDIN a TTY: help & exit | partial | `secret('-')` refuses | interface |

## Documentation

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| DOC-1 | Web documentation | gap | Application concern | out |
| DOC-2 | Terminal documentation matching the install | done (click) | `--help` | auto |
| DOC-3 | Man pages | gap | No generator | out |
| DOC-4 | Documentation reachable through the tool | done | See HELP-6 | auto |

## Output

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| OUT-1 | Human first; detect a TTY per stream | done | Honest consoles | auto |
| OUT-2 | Line-based, `grep`-able output | done | `ctx.emit`: TSV rows off a TTY | interface |
| OUT-3 | `--plain` for one record per line | done | `options.plain()`, `ctx.format` | interface |
| OUT-4 | `--json` for formatted JSON | done | `ctx.emit` with `--json` | interface |
| OUT-5 | Output on success, kept brief | done | `summary`; dropped by `-q` | interface |
| OUT-6 | `-q` suppresses non-essential output | done | Drops `info` & animation | auto |
| OUT-7 | Say so when state changes | done | `row` | interface |
| OUT-8 | Current state easy to see | gap | Application concern | out |
| OUT-9 | Suggest the next commands | done | `pyclig.hint`, kept by `-q` | interface |
| OUT-10 | Boundary crossings are explicit | gap | Application concern | out |
| OUT-11 | Dense, scannable layout | done (rich) | `ctx.out` | interface |
| OUT-12 | Colour with intention, sparingly | done | Prefixes only (`notice`) | auto |
| OUT-13a | No colour off a TTY, per stream | done | `test_forced_colour_means_colour_only` | auto |
| OUT-13b | `NO_COLOR` set & non-empty | done (rich) | `test_no_color_removes_colour` | auto |
| OUT-13c | `TERM=dumb` | done (rich) | Rich console | auto |
| OUT-13d | `--no-color` | done | `_flags.NO_COLOR` | auto |
| OUT-13e | `MYAPP_NO_COLOR` | done | `_run.apply_environment` | auto |
| OUT-14 | No animation off a TTY | done | `status` & `progress`, interactive only | interface |
| OUT-15 | Symbols & emoji where clearer | done | UTF-8 streams; `hanging(head=)` | check |
| OUT-16 | Developer detail only when verbose | done | `-d` | auto |
| OUT-17 | Usability feedback from outsiders | gap | Process concern | out |
| OUT-18 | No log labels or context by default | partial | Prefixes; levels only with `-d` | auto |
| OUT-19 | Pager on a TTY only, `less -FIRX` | done | `ctx.pager`; opt-in on Windows | interface |

## Errors

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| ERR-1 | Rewrite expected errors for humans | done | `errors=` with `hint` | interface |
| ERR-2 | High signal-to-noise ratio | partial | Tracebacks hidden for `errors=` | check |
| ERR-3 | Group similar errors under one header | done | `notice(items=)` | interface |
| ERR-4 | Most important information last | done | Hints & the `--help` pointer print last | auto |
| ERR-5 | Red sparingly | done | `notice` prefix only | auto |
| ERR-6 | Traceback & bug instructions when unexpected | done | `_run._failed` | auto |
| ERR-7 | Debug log to a file | gap | Roadmap 0.6 | interface |
| ERR-8 | Pre-filled bug report URL | partial | Plain `Issues` URL | auto |

## Arguments and flags

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| ARG-1 | Prefer flags to arguments | gap | Unchecked (kit, 1.0) | check |
| ARG-2 | Full-length version of every flag | done | Kit: a flag with no long form | check |
| ARG-3 | One-letter flags for common options only | gap | Unchecked | check |
| ARG-4 | Several arguments for several files | partial (click) | `nargs=-1` | interface |
| ARG-5 | Two or more differing arguments is a warning sign | gap | Unchecked (kit, 1.0) | check |
| ARG-6 | Standard names where a standard exists | partial | Kit: `-f` not `--force` | check |
| ARG-6a | Standard names: `-a`, `-f`, `-n`, `--json` | done | `pyclig.options`; kit | interface |
| ARG-6b | Standard names: `-d`, `-h`, `--version` | done | Run flags; `-v` means version | auto |
| ARG-6c | Standard names: `--no-input` | done | `_flags.NO_INPUT` | auto |
| ARG-6d | Standard names: `-q` | done | `_flags.QUIET` | auto |
| ARG-6e | Standard names: `-o`, `-p`, `-u` | done | `options.output/port/user` | interface |
| ARG-7 | Defaults suit most users | gap | Judgement | out |
| ARG-8 | Prompt for missing input | done | `prompt=` on STDERR, gated | interface |
| ARG-9 | Never require a prompt; skip off a TTY | done | Default, else fail naming the flag | auto |
| ARG-10 | Confirm danger; `--force` for scripts | done | `confirm`, `options.force()` | interface |
| ARG-11a | Mild or moderate danger: prompt, dry run | done | `confirm`, `dry_run()` | interface |
| ARG-11b | Severe danger: type the name, `--confirm=name` | gap | Roadmap 0.6 | interface |
| ARG-12 | Watch for implicit destruction | gap | Application concern | out |
| ARG-13 | `-` for STDIN & STDOUT | done (click) | `click.File` | interface |
| ARG-14 | A word like `none` for an optional value | gap | No type | interface |
| ARG-15 | Order independence | partial | Run flags anywhere; `-v` at the root only | check |
| ARG-16 | No secrets from flags; file or STDIN | done | Kit; `options.secret` | check |

## Interactivity

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| INT-1 | Prompt only when STDIN is a TTY | done | `ctx.can_prompt` (STDIN & STDERR) | interface |
| INT-2 | `--no-input` fails & names the flag | done | Names `--force` or the option | auto |
| INT-3 | Hide a password as it is typed | done (click) | `hide_input` | interface |
| INT-4 | Make it clear how to exit | gap | No hint | out |
| INT-5 | Ctrl-C works during network I/O | partial | Runner; apps poll by hand | interface |
| INT-6 | Document the escape for wrappers | gap | Application concern | out |

## Subcommands

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| SUB-1 | Subcommands for complexity | done (click) | `pyclig.group` | out |
| SUB-2 | Shared flags, config & storage | done | Run flags, `GlobalOption`, `Config` | interface |
| SUB-3 | Same flag names & output format | partial | Kit: plain click child; `ctx.emit` | check |
| SUB-4 | Consistent naming, noun-verb order | gap | Unchecked | check |
| SUB-5 | No confusable names | gap | Unchecked | check |

## Robustness

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| ROB-1 | Validate early with a clear error | done (click) | Types, `UsageError` | interface |
| ROB-2 | Print within 100 ms; say so before network | partial | Import about 60 ms | check |
| ROB-3 | Progress or an ETA for long work | done | `progress` | interface |
| ROB-4 | Parallel without interleaving | partial | Atomic prints | interface |
| ROB-5 | Hide logs on success, show on failure | partial | Transient feedback; 0.6 | interface |
| ROB-6 | Configurable network timeouts | gap | Roadmap 0.6 | interface |
| ROB-7 | Re-running resumes | gap | Application concern | out |
| ROB-8 | Crash-only design | gap | Application concern | out |
| ROB-9 | Expect misuse & odd environments | partial | `None` streams; per-run state | auto |

## Future-proofing

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| FUT-1 | Keep changes additive | gap | Policy; the roadmap is additive | out |
| FUT-2 | Warn before a breaking change | partial (click) | `deprecated=` | interface |
| FUT-3 | Scripts use `--plain` or `--json` | done | Per-command format flags | interface |
| FUT-4 | No catch-all subcommand | done (click) | None | check |
| FUT-5 | No arbitrary abbreviations | done (click) | None | check |
| FUT-6 | No time bombs or blocking analytics | done | pyclig makes no network calls | check |

## Signals

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| SIG-1 | Ctrl-C: say so at once, before clean-up | partial | Printed after unwinding (0.6) | auto |
| SIG-2 | Time out clean-up | gap | Roadmap 0.6 | interface |
| SIG-3 | Second Ctrl-C skips clean-up & says so | gap | Roadmap 0.6 | interface |
| SIG-4 | Expect a previous clean-up never ran | gap | Application concern | out |

## Configuration

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| CFG-1 | Per-invocation settings: flags & env | done (click) | `envvar=` | interface |
| CFG-2 | Per-machine settings: flags, env, `.env` | done | `Config(dotenv=True)` | interface |
| CFG-3 | Per-project settings in a versioned file | done | `Config.project` | interface |
| CFG-4 | XDG locations | done | `pyclig.paths`; `tests/test_paths.py` | interface |
| CFG-5 | Consent before editing others' config | gap | Application concern | out |
| CFG-6 | A new file rather than appending | gap | Application concern | out |
| CFG-7 | Dated comment in a system file | gap | Application concern | out |
| CFG-8 | Precedence: flags, env, project, user | done | `test_precedence_matrix` | interface |

## Environment variables

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| ENV-1 | Env vars for contextual behaviour | done (click) | `envvar=` | interface |
| ENV-2 | Portable names | gap | Unchecked | check |
| ENV-3 | Single-line values | gap | Unchecked | out |
| ENV-4 | Don't reuse common names | gap | Unchecked | check |
| ENV-5 | `NO_COLOR` & `FORCE_COLOR` | done | `FORCE_COLOR` means colour only | auto |
| ENV-6 | `DEBUG` | done | `<PROG>_DEBUG`; `test_debug_variable_turns_on_debug_logging` | auto |
| ENV-7 | `EDITOR` | done (click) | `click.edit` | interface |
| ENV-8 | Proxy variables | gap | HTTP library's job | out |
| ENV-9 | `SHELL`, `TMPDIR`, `HOME` | gap | Standard library or application | out |
| ENV-10 | `TERM`, `TERMINFO`, `TERMCAP` | partial (rich) | `TERM` only | auto |
| ENV-11 | `PAGER` | done (click) | `echo_via_pager` | interface |
| ENV-12 | `LINES` & `COLUMNS` | partial (rich) | `COLUMNS` | auto |
| ENV-13 | Read a local `.env` | done | `Config(dotenv=True)`; `read_dotenv` | interface |
| ENV-14 | `.env` is not a config file | done | Fills `envvar=` only, never `os.environ` | auto |
| ENV-15 | No secrets from env vars | done | Kit: a `_TOKEN`-like `envvar=`; `.env` skips | check |
| ENV-16 | Secrets via file, pipe, socket or service | done | `options.secret` | interface |

## Naming, distribution and analytics

| ID | Rule | Status | Evidence | Owner |
| --- | --- | --- | --- | --- |
| NAME-1 | A simple, memorable word | gap | Could lint the group name | out |
| NAME-2 | Lowercase, dashes only if needed | gap | Could lint the group name | out |
| NAME-3 | Short | gap | Could lint the group name | out |
| NAME-4 | Easy to type | gap | Could lint the group name | out |
| DIST-1 | A single binary or native package | gap | Packaging | out |
| DIST-2 | Easy to uninstall | gap | Packaging | out |
| ANA-1 | No phoning home without consent | done | pyclig collects nothing | out |
| ANA-2 | Explicit about what is collected | done | pyclig collects nothing | out |
| ANA-3 | Opt in, or easy to disable | done | pyclig collects nothing | out |
| ANA-4 | Instrument docs & downloads instead | done | pyclig collects nothing | out |
| ANA-5 | Talk to users | done | pyclig collects nothing | out |

## Checked by the kit

`pyclig.testing.check` & `assert_conforms` report these rows, by ID, without running a command
body: HELP-1, HELP-3, HELP-9, BAS-2, BAS-5, ARG-2, ARG-6, ARG-16, ENV-15 & SUB-3. A finding the
application accepts is silenced with `ignore={"ARG-16": "reason"}`; the reason is required.

## Delivered in 0.3.0

BAS-3, HELP-2, HELP-4, HELP-9, OUT-1, OUT-3, OUT-6, OUT-13a, OUT-13d, ERR-1, ERR-4, ARG-2, ARG-6c,
ARG-6d, ARG-8, ARG-9, ARG-16, INT-1, INT-2, SUB-2, FUT-3, ENV-5 & ENV-15 moved to `done`.

## Delivered in 0.4.0

HELP-6, DOC-4, OUT-2, OUT-4, OUT-5, OUT-7, OUT-9, OUT-14, OUT-19, ERR-3 & ROB-3 moved to `done`;
ROB-5 to `partial`, closing in 0.6. OUT-5's owner became `interface`: the kit cannot judge
"brief". OUT-19 pages on Windows only when `PAGER` is set, as click's `more` fallback garbles
UTF-8 and cannot scroll.

## Delivered in 0.5.0

CFG-2, CFG-3, CFG-4, CFG-8, ENV-6, ENV-13, ENV-14, ENV-16, OUT-13e & ARG-6e moved to `done`;
HELP-18 to `partial`: `options.secret("-")` refuses a terminal STDIN with a usage error, while
`click.File("-")` still blocks. ENV-14's owner became `auto`: `.env` fills declared `envvar=`
options only and never `os.environ`, so no kit check was needed. Top-level config keys do not
cascade into subcommand tables (click's `default_map` shape); a shared setting is a value
`GlobalOption`. `--config FILE` selects `table` only when named like the project file.
