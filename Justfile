[unix]
set shell := ["bash", "-euo", "pipefail", "-c"]

[windows]
set shell := ["pwsh.exe", "-c"]

set dotenv-load := true

[default]
@_:
    just --list

[doc("Setup development environment & pre-commit hooks")]
[group("DEV")]
setup:
    uv sync
    uv run prek install

[doc("Create `coverage` report")]
[group("DEV")]
coverage *FLAGS:
    @uv run coverage run -m pytest {{FLAGS}}
    @uv run coverage report --show-missing --skip-covered --fail-under=90
    @uv run coverage xml
    @uv run coverage html

[doc("Git prune (aggressive)")]
[group("DEV")]
git-prune:
    git gc --prune=now --aggressive

[doc("Symlink `AGENTS.md` -> `CLAUDE.md`")]
[group("DEV")]
symlink-agents:
    @uv run python -c "import pathlib; p=pathlib.Path('CLAUDE.md'); p.unlink(missing_ok=True); p.symlink_to('AGENTS.md')"
