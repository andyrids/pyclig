"""Greet someone by name: a single pyclig command.

Run from this directory:
    uv run hello --name Ada --shout
    uv run hello -h
    uv run hello -v
    uv run hello --nme Ada; echo $?
    uv run hello --nme Ada -h
    uv run hello --no-color -h
    HELLO_DEBUG=1 uv run hello

License:
    SPDX-License-Identifier: Apache-2.0
"""

import click

import pyclig


@pyclig.command(
    "hello",
    examples=["hello\nhello world", "hello --name Ada --shout\nHELLO ADA"],
    docs="https://github.com/andyrids/pyclig#readme",
)
@click.option(
    "--name", default="world", show_default=True, help="Who to greet."
)
@click.option("--shout", is_flag=True, help="Greet in capitals.")
def cli(name: str, shout: bool) -> int:
    """Greet someone by name."""
    greeting = f"hello {name}"
    click.echo(greeting.upper() if shout else greeting)
    return pyclig.ExitCode.OK
