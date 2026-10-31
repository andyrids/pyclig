---
context-hierarchy: Layer 0
context-hierarchy-role: Global identity
immutable: false
recommended-context-tokens: 900
---

# pyclig [`pyclig`]

A Python Click wrapper with [Command Line Interface Guidelines (CLIG)](https://clig.dev/) paradigms.

This project adheres to [YAGNI](docs/guidance/standard-yagni.md) principles.

## Design rules

- Runtime dependencies are the stdlib, `click` & `rich` only.
- click owns parsing, help, completion & the test runner - do not reimplement them. pyclig adds
  the CLIG conventions on top: stream discipline, exit codes, error rendering, logging, output
  primitives & standard flags.
- No state at import: no consoles, handlers, file reads or `importlib.metadata` calls at module
  level. Keep `rich.traceback`, `rich.logging` & `importlib.metadata` off the `import pyclig` path.
- Consoles are created per run & passed in, with markup, emoji & highlighting off. One STDERR
  console per run is shared by logging & live displays.
- Messages are printed as `rich.text.Text`, never parsed as markup - they quote user input.
- A pattern is added to pyclig when a consuming CLI (dkais, pkgdx) uses it.

## Context hierarchy

Markdown files declare their layer in frontmatter - read
[standard-context-hierarchy.md](docs/guidance/standard-context-hierarchy.md) before creating or
editing one. Files marked `immutable: true` are never edited in passing: propose the change and
wait for approval.

## Reference

Standards and references live in `docs/guidance` as `standard-*.md` and `toolchain-*.md` files
(Layer 3). Load a file when its subject is in play, which can be determined by the frontmatter.
