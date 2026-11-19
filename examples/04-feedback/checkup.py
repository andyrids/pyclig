"""Run a few system checks: feedback on STDERR, logging & quiet mode.

Run from this directory:
    uv run checkup run
    uv run checkup run --fail clock -q; echo $?
    uv run checkup run 2>/dev/null
    uv run checkup run --delay 2
    uv run checkup sync -d
    CHECKUP_DEBUG=1 uv run checkup sync
    uv run checkup sync --fail-at 3; echo $?
    CHECKUP_LOG_FILE=/tmp/checkup.log uv run checkup sync

Press Ctrl-C during `checkup run --delay 2` to see `warning: interrupted`
& exit code 130.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import logging
import time

import click

import pyclig

logger = logging.getLogger(__name__)

CHECKS = ("disk", "network", "clock", "cache")
STEPS = 4


class CheckupError(Exception):
    """An expected checkup failure, shown as one line with exit code 1."""


@pyclig.group(
    "checkup",
    examples=[
        "checkup run",
        "checkup run --fail clock",
        "checkup sync --fail-at 3",
    ],
    errors=(CheckupError,),
)
def cli() -> None:
    """Run system checks & show how they went."""


@cli.command("run")
@click.option(
    "--fail",
    "failing",
    multiple=True,
    type=click.Choice(CHECKS),
    metavar="CHECK",
    help="Make CHECK fail; repeatable.",
)
@click.option(
    "--delay",
    type=click.FloatRange(min=0),
    default=0.3,
    show_default=True,
    metavar="SECONDS",
    help="Pause per check, to watch the spinner.",
)
@pyclig.pass_context
def run_checks(
    ctx: pyclig.Context, failing: tuple[str, ...], delay: float
) -> int:
    """Run every check & report the ones that fail."""
    with pyclig.status(ctx.err, message="Loading checks"):
        time.sleep(delay)
    pyclig.info(ctx.err, message=f"running {len(CHECKS)} checks")
    with pyclig.progress(ctx.err) as bar:
        task = bar.add_task("Checking", total=len(CHECKS))
        for _ in CHECKS:
            time.sleep(delay)
            bar.advance(task)
    for name in CHECKS:
        failed = name in failing
        pyclig.row(
            ctx.err,
            mark="!" if failed else "✓",
            label=name,
            detail="failed" if failed else "ok",
            width=8,
            essential=failed,
        )
    if failing:
        pyclig.notice(
            ctx.err,
            level="error",
            message=f"{len(failing)} of {len(CHECKS)} checks failed",
            items=[f"{name}: forced by --fail" for name in failing],
        )
        pyclig.hint(
            ctx.err, message="Re-run without --fail to see every check pass."
        )
        return pyclig.ExitCode.FAILURE
    pyclig.summary(ctx.err, message=f"{len(CHECKS)} checks passed")
    return pyclig.ExitCode.OK


@cli.command()
@click.option(
    "--fail-at",
    type=click.IntRange(min=1),
    metavar="STEP",
    help="Fail at STEP, to replay the held log lines.",
)
@pyclig.pass_context
def sync(ctx: pyclig.Context, fail_at: int | None) -> None:
    """Sync in steps, holding the log lines unless a step fails."""
    logger.debug("starting sync")
    logger.warning("the cache is stale")
    with ctx.logs_on_failure():
        for step in range(1, STEPS + 1):
            logger.info("synced step %d", step)
            if step == fail_at:
                raise CheckupError(f"step {step} failed")
    pyclig.summary(ctx.err, message=f"{STEPS} steps synced")
