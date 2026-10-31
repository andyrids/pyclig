"""A dkais-shaped sample CLI, exercising every behaviour `pyclig` maps.

Run in-process by the tests, or as a script by the subprocess tests.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import errno
import logging
import time

import click
from rich.text import Text

import pyclig

# The package logger: `tests` in-process, `sample` when run as a script
logger = logging.getLogger(__package__ or "sample")


class SampleError(Exception):
    """An expected failure of the sample CLI."""


class Year(click.ParamType[int]):
    """A four-digit year; `crash` simulates a bug in the type."""

    name = "year"

    def convert(
        self,
        value: object,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> int:
        """Convert `value` to a year.

        Args:
            value: The raw value.
            param: The parameter.
            ctx: The context.

        Returns:
            The year.
        """
        logger.debug("converting %r", value)
        if value == "crash":
            raise TypeError("the year type is broken")
        if not (
            isinstance(value, str) and value.isdigit() and len(value) == 4
        ):
            self.fail(f"invalid year `{value}` - use YYYY", param, ctx)
        return int(value)


@pyclig.group(
    "sample",
    short_help="Sample data manager",
    examples=["sample list --start 2026"],
    errors=(SampleError,),
    epilog="For more information see https://example.com/sample.",
)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Manage sample data."""
    ctx.ensure_object(dict)["root"] = "set by the group"


@cli.command("list")
@pyclig.options.json_output()
@click.option("--start", type=Year(), metavar="YEAR", help="Range start.")
@pyclig.pass_context
def list_(ctx: pyclig.Context, start: int | None, json_output: bool) -> None:
    """List sample items."""
    ctx.out.print(f"start={start} json={json_output}")


@cli.command()
@click.option(
    "--data-dir",
    type=click.Path(file_okay=False),
    envvar="SAMPLE_DATA_DIR",
    show_envvar=True,
    required=True,
)
def download(data_dir: str) -> None:
    """Download sample items."""
    click.echo(data_dir)


@cli.command(no_args_is_help=True)
@click.option("--start", type=Year())
def process(start: int) -> None:
    """Process sample items."""
    click.echo(start)


@cli.command()
@click.option(
    "--kind",
    type=click.Choice(
        ["mapped", "crash", "interrupt", "eof", "oserror", "usage", "code"]
    ),
    required=True,
)
def fail(kind: str) -> int:
    """Fail in the way given by `--kind`."""
    if kind == "mapped":
        raise SampleError("disk full [/b] :warning:")
    if kind == "crash":
        raise RuntimeError("boom")
    if kind == "interrupt":
        raise KeyboardInterrupt
    if kind == "eof":
        raise EOFError("truncated")
    if kind == "oserror":
        raise OSError(errno.EPIPE, "a child process pipe broke")
    if kind == "usage":
        raise click.UsageError("--kind usage cannot be combined")
    return pyclig.ExitCode.INTERRUPT


@cli.command()
@click.option("--lines", type=int, default=1)
@click.option("--rich", is_flag=True, help="Print through the console.")
@click.option("--delay", type=float, default=0.0)
@pyclig.pass_context
def echo(ctx: pyclig.Context, lines: int, rich: bool, delay: float) -> None:
    """Print numbered lines to STDOUT, after an optional delay."""
    time.sleep(delay)
    for i in range(lines):
        if rich:
            ctx.out.print(f"line {i}")
        else:
            click.echo(f"line {i}")


@cli.command()
@click.option("--value", required=True)
@pyclig.pass_context
def show(ctx: pyclig.Context, value: str) -> None:
    """Print `--value` to STDOUT & as a warning & a notice to STDERR."""
    ctx.out.print(value)
    logger.warning(value)
    pyclig.notice(ctx.err, level="error", message=value)


@cli.command()
@click.option("--exception", is_flag=True, help="Log an exception instead.")
def log(exception: bool) -> None:
    """Log one record per level, or an exception."""
    if exception:
        try:
            raise ValueError("bad row")
        except ValueError:
            logger.exception("row skipped")
        return
    logger.debug("debug record")
    logger.info("info record")
    logger.warning("warning record")
    logger.error("error record")


@cli.command()
def confirm() -> None:
    """Ask for confirmation, aborting when declined."""
    click.confirm("go?", abort=True)
    click.echo("went")


@cli.command()
@pyclig.pass_context
def streams(ctx: pyclig.Context) -> None:
    """Interleave `click.echo` & console output, then report the TTYs."""
    click.echo("one")
    ctx.out.print("two")
    click.echo("three")
    ctx.err.print(Text(f"out={ctx.out.is_terminal} err={ctx.err.is_terminal}"))


@cli.group()
def grp() -> None:
    """Group nested commands."""


@grp.command()
@click.pass_obj
def leaf(obj: dict[str, str]) -> None:
    """Log a debug record & print the root's `ctx.obj` entry."""
    logger.debug("leaf debug record")
    click.echo(obj["root"])


if __name__ == "__main__":
    cli()
