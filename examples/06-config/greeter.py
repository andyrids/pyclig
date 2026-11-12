"""Greet someone as configured: config files, profiles & precedence.

Run from this directory:
    uv run greeter hello
    uv run greeter --profile loud hello
    GREETER_PROFILE=loud uv run greeter hello
    GREETER_NAME=Bob uv run greeter hello
    uv run greeter hello --name Cy --region us
    uv run greeter -d hello
    uv run greeter where
    cd ../.. && uv run --package greeter greeter hello

A value comes from the command line, then the environment, then the
profile, then `.greeter.toml`. The last line runs outside this directory,
so no project file is found & it prints `hello world`.

License:
    SPDX-License-Identifier: Apache-2.0
"""

from pathlib import Path

import click

import pyclig
from pyclig import paths

PROJECT_FILE = ".greeter.toml"


def _region(ctx: click.Context, param: click.Parameter, value: str) -> None:
    """Share `--region` with the subcommands through `ctx.meta`.

    Args:
        ctx: The context the option was parsed in.
        param: The `--region` option.
        value: The region given on the command line, by the environment
            or by a config file.
    """
    del param
    ctx.meta["greeter.region"] = value


def _project_file() -> Path | None:
    """Find `.greeter.toml` from the working directory upward.

    Returns:
        The nearest project file, or None when there is none.
    """
    here = Path.cwd()
    for directory in (here, *here.parents):
        file = directory / PROJECT_FILE
        if file.is_file():
            return file
    return None


@pyclig.group(
    "greeter",
    examples=[
        "greeter hello",
        "greeter --profile loud hello",
        "greeter where",
    ],
    config=pyclig.Config(profiles=True),
)
@click.option(
    "--region",
    cls=pyclig.GlobalOption,
    type=str,
    callback=_region,
    help="The region to greet from.",
)
def cli() -> None:
    """Greet people, as configured by .greeter.toml."""


@cli.command()
@click.option(
    "--name",
    default="world",
    envvar="GREETER_NAME",
    show_envvar=True,
    help="Who to greet.",
)
@click.option("--shout", is_flag=True, help="Greet in capitals.")
@pyclig.pass_context
def hello(ctx: pyclig.Context, name: str, shout: bool) -> None:
    """Greet NAME, from the region when one is set."""
    region = ctx.meta.get("greeter.region")
    greeting = f"hello {name}"
    if region:
        greeting += f", from {region}"
    click.echo(greeting.upper() if shout else greeting)


@cli.command()
def where() -> None:
    """Print the config files, from the nearest to the furthest."""
    click.echo(f"project\t{_project_file() or 'none'}")
    click.echo(f"user\t{paths.config_dir('greeter') / 'config.toml'}")
    click.echo(f"system\t{paths.system_config_dir('greeter') / 'config.toml'}")
