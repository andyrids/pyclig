---
context-hierarchy: Layer 3
context-hierarchy-role: Reference material
immutable: true
recommended-context-tokens: 2500
version: 1.0.0
updated: 2026-10-30
tags: [pkgdx, prek, pre-commit, config]
---

# Toolchain - `pkgdx`

`pkgdx` is the dev dependency that carries the canonical standards. It ships the Ruff, Mypy and
PyMarkdown configs, the hook shims that apply them, and the template for the hooks it manages in
`prek.toml`.

## Commands

- `uv run pkgdx init` - Merge the `pkgdx` hooks into `prek.toml`, install the Git shims, check for
  hook updates and create `.secrets.baseline`
- `uv run pkgdx init --reset` - As `init`, but overwrite `prek.toml` (see Resetting)
- `uv run pkgdx config` - Show which config each hook uses (user or bundled) and its path
- `uv run pkgdx config --export` - Copy the bundled configs into the user config directory,
  keeping any file already there
- `uv run prek update --repo https://gitlab.com/andyrids/pkgdx` - Move the `pkgdx` hooks to the
  latest `pkgdx` release

## Hooks in `prek.toml`

`prek.toml` is shared: `pkgdx` manages its own hooks there, and the project can add its own. These
entries belong to `pkgdx`:

- The `https://gitlab.com/andyrids/pkgdx` repo and its hooks (`pkgdx-lint`, `pkgdx-format`,
  `pkgdx-markdown`, `pkgdx-secrets`)
- The `pkgdx-typing` hook in the `local` repo
- The `check-toml`, `check-yaml` and `detect-private-key` hooks in the `builtin` repo

Their behaviour is set by the `pkgdx` release, not by the project:

- MUST NOT edit or remove the `pkgdx` entries by hand
- COULD add custom `local` hooks next to `pkgdx-typing`, or remote hooks as new `[[repos]]` entries

On an existing `prek.toml`, `init` only adds what is missing - repos matched by `repo`, hooks by
`id` - and never edits or removes an entry, `rev` included. Project hooks survive it.

## Resetting

`uv run pkgdx init --reset` overwrites `prek.toml` with the `pkgdx` template, losing every project
hook, remote repo and edit.

- MUST copy project hooks out of `prek.toml` before a reset, and add them back after

## Upgrading

1. `uv lock --upgrade-package pkgdx`, then `uv sync`
2. `uv run prek update --repo https://gitlab.com/andyrids/pkgdx` to move `rev` to the same release.
   The remote hooks are defined in the `pkgdx` repo at that `rev`, so they follow it.
3. `pkgdx-typing` is copied into `prek.toml` in full, so neither step refreshes it. When the
   `pkgdx` CHANGELOG reports a change to it, apply it with a reset (see Resetting).

## Config overrides

Each hook resolves its config when it runs: a file of the same name in the user config directory
replaces the bundled one, otherwise the bundled one is used.

- Directory: `PKGDX_CONFIG_DIR`, else `%APPDATA%\pkgdx` (Windows), else `$XDG_CONFIG_HOME/pkgdx`
  or `~/.config/pkgdx`
- Files: `ruff.toml`, `mypy.ini`, `pymarkdown.toml`, and `hooks.toml` (read only by `pkgdx init`)
- An override replaces the whole file - nothing is merged, so it stops following `pkgdx` releases
- `PKGDX_CONFIG_DIR` MUST be set wherever the hooks run, CI included. Unset, the hooks fall back to
  the platform directory and then the bundled configs without warning; set to a path that is not an
  existing directory, they fail with exit code 1 (`pkgdx-secrets` is unaffected)

## Installation

`pkgdx` is a dev dependency, published to PyPI and the GitLab package registry. Projects generated
from the template resolve it from the GitLab registry through an explicit index (see
`toolchain-uv.md`).
