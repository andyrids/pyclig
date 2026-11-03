"""A dkais-shaped sample CLI, exercising every behaviour `pyclig` maps.

Run in-process by the tests, or as a script by the subprocess tests.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import errno
import logging
import threading
import time

import click
from rich.text import Text

import pyclig

# The package logger: `tests` in-process, `sample` when run as a script
logger = logging.getLogger(__package__ or "sample")


class SampleError(Exception):
    """An expected failure of the sample CLI."""


class HintedError(SampleError):
    """An expected failure with a remedy, printed after the message."""

    hint = "Free some space, then re-run."


class CodedError(SampleError):
    """An expected failure with its own exit code."""

    exit_code = 3


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


def _audit(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Record `--audit` for the run, wherever it is given."""
    if value:
        ctx.meta["audit"] = True


@pyclig.group(
    "sample",
    short_help="Sample data manager",
    examples=["sample list --start 2026"],
    errors=(SampleError,),
    epilog="For more information see https://example.com/sample.",
)
@click.option(
    "--audit", cls=pyclig.GlobalOption, callback=_audit, help="Audit the run."
)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Manage sample data."""
    ctx.ensure_object(dict)["root"] = "set by the group"


@cli.command(
    "list",
    examples=["sample list --start 2026", "sample list --json"],
    epilog="Items are listed oldest first.",
)
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
        [
            "mapped",
            "hinted",
            "coded",
            "crash",
            "interrupt",
            "eof",
            "oserror",
            "usage",
            "code",
        ]
    ),
    required=True,
)
def fail(kind: str) -> int:
    """Fail in the way given by `--kind`."""
    if kind == "mapped":
        raise SampleError("disk full [/b] :warning:")
    if kind == "hinted":
        raise HintedError("disk full")
    if kind == "coded":
        raise CodedError("partial")
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
@pyclig.options.force()
@pyclig.pass_context
def purge(ctx: pyclig.Context, force: bool) -> None:
    """Delete every sample item, once confirmed."""
    pyclig.confirm(ctx, message="Delete every sample item?", force=force)
    ctx.out.print("purged")


@cli.command()
@click.option("-d", "--dir", help="The destination directory.")
@pyclig.pass_context
def copy(ctx: pyclig.Context, dir: str | None) -> None:  # noqa: A002
    """Print `--dir`, which takes `-d` from the run flag."""
    logger.debug("copy debug record")
    ctx.out.print(f"dir={dir}")


@cli.command()
@pyclig.pass_context
def audit(ctx: pyclig.Context) -> None:
    """Print whether `--audit` was given anywhere."""
    ctx.out.print("audited" if ctx.meta.get("audit") else "unaudited")


@cli.command()
@pyclig.options.json_output()
@pyclig.options.plain()
@pyclig.pass_context
def rows(ctx: pyclig.Context, json_output: bool) -> None:
    """Print the run's output format & the `--json` value."""
    ctx.out.print(f"format={ctx.format} json={json_output}")


@cli.command()
@click.option("--token", prompt="Token", help="The access token.")
def login(token: str) -> None:
    """Print `--token`, prompting for it when it is not given."""
    click.echo(f"token={token}")


@cli.command()
@pyclig.pass_context
def chatter(ctx: pyclig.Context) -> None:
    """Print info from the main & a worker thread, a warning & STDOUT."""
    pyclig.info(ctx.err, message="main info")
    worker = threading.Thread(
        target=pyclig.info, args=(ctx.err,), kwargs={"message": "worker info"}
    )
    worker.start()
    worker.join()
    logger.warning("kept warning")
    ctx.err.print(Text(f"live={ctx.err.is_interactive}"))
    ctx.out.print(f"quiet={ctx.quiet}")


@cli.command()
@pyclig.pass_context
def streams(ctx: pyclig.Context) -> None:
    """Interleave `click.echo` & console output, then report the TTYs."""
    click.echo("one")
    ctx.out.print("two")
    click.echo("three")
    tty = f"out={ctx.out.is_terminal} err={ctx.err.is_terminal}"
    live = f"live={ctx.err.is_interactive} prompt={ctx.can_prompt}"
    ctx.err.print(Text(f"{tty} {live}"))


@cli.group()
def grp() -> None:
    """Group nested commands."""


@grp.command()
@click.pass_context
def leaf(ctx: click.Context) -> None:
    """Log a debug record & print the root's `ctx.obj` entry."""
    logger.debug("leaf debug record")
    click.echo(ctx.obj["root"])
    if ctx.meta.get("audit"):
        click.echo("audited")


if __name__ == "__main__":
    cli()
