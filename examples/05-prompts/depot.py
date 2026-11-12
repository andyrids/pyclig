"""Purge build caches: confirmations, secrets & the non-TTY refusal.

Run from this directory:
    uv run depot purge build -n
    uv run depot purge --all
    uv run depot purge --all </dev/null; echo $?
    uv run depot --no-input drop wheels; echo $?
    uv run depot drop wheels
    echo s3cret | uv run depot login -u ada --token-file -

`purge --all` & `drop wheels` prompt on a terminal. Without one, or with
`--no-input`, they exit with code 2 & name the flag to pass instead.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import click

import pyclig
from pyclig import options

CACHES = {"build": 120, "docs": 15, "wheels": 340}


def _check(ctx: pyclig.Context, names: list[str]) -> None:
    """Fail with a usage error when a name is not a known cache.

    Args:
        ctx: The command's context, used to report the failure.
        names: The cache names to check.
    """
    for name in names:
        if name not in CACHES:
            known = ", ".join(CACHES)
            ctx.fail(f"no cache named {name!r} - choose from {known}")


@pyclig.group(
    "depot",
    examples=[
        "depot purge build --dry-run",
        "depot purge --all --force",
        "depot drop wheels --confirm wheels",
    ],
)
def cli() -> None:
    """Manage a depot of build caches."""


@cli.command()
@click.argument("names", nargs=-1)
@options.select_all()
@options.dry_run()
@options.force()
@pyclig.pass_context
def purge(
    ctx: pyclig.Context,
    names: tuple[str, ...],
    select_all: bool,
    dry_run: bool,
    force: bool,
) -> None:
    """Empty the named caches, after a confirmation."""
    chosen = list(CACHES) if select_all else list(names)
    if not chosen:
        ctx.fail("name a cache, or pass --all")
    _check(ctx, chosen)
    if dry_run:
        for name in chosen:
            click.echo(f"would remove {name}")
        return
    pyclig.confirm(ctx, message=f"Remove {len(chosen)} caches?", force=force)
    for name in chosen:
        pyclig.row(
            ctx.err,
            mark="✓",
            label=name,
            detail=f"{CACHES[name]} MB freed",
            width=8,
        )


@cli.command()
@click.argument("name")
@options.confirm_name()
@pyclig.pass_context
def drop(ctx: pyclig.Context, name: str, confirmed: str | None) -> None:
    """Drop a cache for good, after its name is typed."""
    _check(ctx, [name])
    pyclig.confirm_name(
        ctx,
        message=f"Drop the {name} cache for good?",
        name=name,
        confirmed=confirmed,
    )
    pyclig.summary(ctx.err, message=f"dropped {name}")


@cli.command()
@options.user(default="me")
@options.secret("token", required=True)
def login(user: str, token: str) -> None:
    """Log in with a token read from a file or STDIN."""
    click.echo(f"logged in as {user} with a {len(token)}-character token")
