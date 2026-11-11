---
context-hierarchy: Layer 3
context-hierarchy-role: Reference material
immutable: false
recommended-context-tokens: 900
tags: [CLI, CLIG, roadmap]
---

# Roadmap

Every item closes rows of `docs/clig-coverage.md`, by ID, and is additive: 0.3.0 locked the
interfaces a later rule would otherwise have had to break (the runner on `Command`, run flags
through `GlobalOption`, `ctx.format`, `ctx.can_prompt`, honest consoles, the `hint` & `exit_code`
attributes). A release may ship fewer items than listed, never a breaking one.

## 0.4 - output and feedback (delivered in 0.4.0)

- `ctx.emit(records)`: one call that prints a table, plain rows or JSON by `ctx.format` (OUT-2,
  OUT-4, SUB-3)
- State-change rows & a closing summary (OUT-5, OUT-7), the pattern pkgdx hand-rolls
- `status` & `progress` gate on `ctx.err.is_interactive`, so apps stop gating by hand (OUT-14,
  ROB-3)
- A next-step hint primitive (OUT-9)
- `help` & `help <command>` (HELP-6, DOC-4)
- `ctx.pager()` for long STDOUT on a TTY, with `less -FIRX`; opt-in through `PAGER` on Windows,
  where click's `more` fallback cannot show it (OUT-19)
- Grouped failures under one header (ERR-3)

## 0.5 - configuration and environment (delivered in 0.5.0)

- XDG config & data paths (CFG-4)
- `GlobalOption` taking a value (`--config FILE`, `--profile NAME`), which precedence needs;
  0.3.0 supports flags only, and widening it later is additive (CFG-8)
- Precedence flags > environment > project > user > system (CFG-3, CFG-8)
- `.env` reading, with the limits CLIG puts on it (CFG-2, ENV-13)
- Secrets from files or STDIN (pipes, process substitution) (ENV-16, ARG-16)
- `<PROG>_DEBUG` & `<PROG>_NO_COLOR` (ENV-6, OUT-13e)
- `-o/--output`, `-p/--port` & `-u/--user` factories (ARG-6e)

## 0.6 - robustness and signals (delivered in 0.6.0)

- `with ctx.cleanup(timeout=...)`: say so at once on Ctrl-C, bound the clean-up, let a second
  Ctrl-C skip it (SIG-1, SIG-2, SIG-3)
- SIGTERM mapped like Ctrl-C (INT-5)
- Configurable network timeouts (ROB-6)
- Debug log to a file (ERR-7)
- Typed confirmation & `--confirm=name` for severe actions (ARG-11b)
- Third-party warnings & root-logger records through the run's STDERR console (OUT-18)
- Hide logs on success, show them on failure (ROB-5)

## 0.7 - closing the rows (delivered in 0.7.0)

- Static kit rules for arguments, one-letter flags, flag consistency, environment variable names
  & subcommand naming (ARG-1, ARG-3, ARG-5, ARG-6, SUB-3, SUB-4, SUB-5, ENV-2, ENV-4)
- The kit gains `samples=`: command lines it runs for real, checking the exit, `--json`, STDOUT
  & tracebacks (BAS-4, BAS-5, ERR-2)
- Evidence for Ctrl-C inside blocking I/O, import time, threaded notices & hostile environments;
  `> NUL` is plain & an empty `PYTHONIOENCODING` is unset (INT-5, ROB-2, ROB-4, ROB-9)
- `-v/--version` anywhere on the command line (ARG-15)
- `options.NoneOr`: a value, or the word `none` (ARG-14)
- A `click.File` to read refuses `-` on a terminal STDIN (HELP-18)
- Deprecated commands & parameters warn in pyclig's style (FUT-2)
- Concise help lists a few options; `docs=` & `LEARN MORE:`; examples with their output; bold
  headings (HELP-3, HELP-7, HELP-8, HELP-10, HELP-14)
- A pre-filled bug report URL on github.com & gitlab.com (ERR-8)
- `LINES` & `TERM=dumb` are honoured, as Rich reads them (ENV-10, ENV-12)

Every row is now `done`, or owned `out`. ARG-1, ARG-5, SUB-4 & SUB-5 are static kit rules, not
`samples=` ones as first planned: they need no run.

## 1.0 - API freeze

- No new rows: the public names, signatures & kit rule IDs of 0.7 are frozen
