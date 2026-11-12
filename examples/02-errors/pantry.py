"""Take items from a pantry: a pyclig group, its errors & exit codes.

Run from this directory:
    uv run pantry
    uv run pantry help take
    uv run pantry take; echo $?
    uv run pantry take kiwi; echo $?
    uv run pantry take mango; echo $?
    uv run pantry take apple --count 0; echo $?
    uv run pantry crash; echo $?
    uv run pantry -d take mango

License:
    SPDX-License-Identifier: Apache-2.0
"""

import click

import pyclig

STOCK = {"apple": 3, "kiwi": 0, "pear": 5}


class PantryError(Exception):
    """An expected pantry failure, shown as one line with exit code 1."""


class OutOfStockError(PantryError):
    """An item has too little stock for the request.

    Attributes:
        hint: The next step, printed under the error message.
        exit_code: The exit code used in place of the default 1.
    """

    hint = "Run `pantry list` to see what is in stock."
    exit_code = 3


@pyclig.group(
    "pantry",
    examples=["pantry list", "pantry take apple --count 2"],
    errors=(PantryError,),
)
def cli() -> None:
    """Take items from a small pantry."""


@cli.command("list")
def list_() -> None:
    """List each item & its stock count."""
    for item, count in STOCK.items():
        click.echo(f"{item}\t{count}")


@cli.command(
    no_args_is_help=True,
    examples=["pantry take apple --count 2\ntook 2 apple, 1 left"],
)
@click.argument("item")
@click.option(
    "--count",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="How many to take.",
)
def take(item: str, count: int) -> None:
    """Take an item from the pantry."""
    if item not in STOCK:
        raise PantryError(f"no item named {item}")
    if count > STOCK[item]:
        raise OutOfStockError(f"only {STOCK[item]} {item} left")
    click.echo(f"took {count} {item}, {STOCK[item] - count} left")


@cli.command()
def crash() -> None:
    """Fail with a bug, to show an unexpected error."""
    raise RuntimeError("this is a bug")
