# pyclig [`pyclig`]

A Python Click wrapper with [Command Line Interface Guidelines (CLIG)](https://clig.dev/) paradigms.

## Design rules

- Runtime dependencies are the stdlib, `click` & `rich` only.
- click owns parsing, help, completion & the test runner - do not reimplement them. pyclig adds
  the CLIG conventions on top: stream discipline, exit codes, error rendering, logging, output
  primitives & standard flags.
- No state at import: no consoles, handlers, file reads or `importlib.metadata` calls at module
  level. Keep `rich.traceback`, `rich.logging`, `importlib.metadata` & `_conformance` off the
  `import pyclig` path.
- Consoles are created per run & passed in, with markup, emoji & highlighting off. One STDERR
  console per run is shared by logging & live displays.
- Messages are printed as `rich.text.Text`, never parsed as markup - they quote user input.
- CLIG is the requirement. Every actionable rule has a row in `docs/clig-coverage.md`.
- Keep `docs/cli-standard.md` and `docs/clig-coverage.md` in step with code changes.

## Commands

- `uv run pytest -v` - Run the test suite
- `uv run pytest -m conformance -v` - Run only the `conformance` tier
- `uv run prek run --all-files` - Run the formatters, linters and type checks

## Conventions

- Implement only what is asked; prefer the standard library, then an existing dependency, and ask
  before adding one.
