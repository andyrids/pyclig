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

## 0.5 - configuration and environment

- XDG config & data paths (CFG-4)
- `GlobalOption` taking a value (`--config FILE`, `--profile NAME`), which precedence needs;
  0.3.0 supports flags only, and widening it later is additive (CFG-8)
- Precedence flags > environment > project > user > system (CFG-3, CFG-8)
- `.env` reading, with the limits CLIG puts on it (CFG-2, ENV-13)
- Secrets from files, pipes or a secret store (ENV-16, ARG-16)
- `<PROG>_DEBUG` & `<PROG>_NO_COLOR` (ENV-6, OUT-13e)
- `-o/--output`, `-p/--port` & `-u/--user` factories (ARG-6e)

## 0.6 - robustness and signals

- `with ctx.cleanup(timeout=...)`: say so at once on Ctrl-C, bound the clean-up, let a second
  Ctrl-C skip it (SIG-1, SIG-2, SIG-3)
- SIGTERM mapped like Ctrl-C (INT-5)
- Configurable network timeouts (ROB-6)
- Debug log to a file (ERR-7)
- Typed confirmation & `--confirm=name` for severe actions (ARG-11b)
- Third-party warnings & root-logger records through the run's STDERR console (OUT-18)
- Hide logs on success, show them on failure (ROB-5)

## 1.0 - API freeze

- Every row `done`, or owned `out`
- The kit gains `samples=` for checks that need a run with input (ARG-1, ARG-5, SUB-4, SUB-5)
