"""Run flags: options about how a run behaves, accepted on every command.

| Flag           | Effect                                               |
| -------------- | ---------------------------------------------------- |
| `-d, --debug`  | `DEBUG` logging as soon as it is parsed              |
| `-q, --quiet`  | No `info` lines or animation; notices & hints stay   |
| `--no-color`   | No colour on either console; bold & dim stay         |

`RUN_FLAGS` are on every `pyclig.Command`; an application declares its own
with `click.option(..., cls=pyclig.GlobalOption)` on the command whose
subtree accepts it, usually the root group. A command's own option with the
same spelling wins: the run flag keeps its other names, or steps aside.

License:
    SPDX-License-Identifier: Apache-2.0
"""

from collections.abc import Callable, Collection, Sequence
from typing import Any

import click

from pyclig import _logging, _output, _run


class GlobalOption(click.Option):
    """A run flag, accepted on its command & every command below it.

    NOTE: Eager & never passed to the command function: the callback acts
    as soon as the flag is parsed, before or after a command name, so `-d`
    applies even when a later option is invalid.
    """

    def __init__(
        self,
        param_decls: Sequence[str],
        *,
        callback: Callable[[click.Context, click.Parameter, bool], Any],
        **kwargs: Any,
    ) -> None:
        """Create the flag.

        Args:
            param_decls: The flag names, e.g. `["--trace"]`.
            callback: Called with the context, this flag & whether it was
                given, each time a command parses it.
            **kwargs: Keyword `click.Option` arguments, e.g. `help`.
        """
        super().__init__(
            param_decls,
            is_flag=True,
            is_eager=True,
            expose_value=False,
            callback=callback,
            **kwargs,
        )

    def without(self, names: Collection[str]) -> "GlobalOption | None":
        """Return this flag minus `names`, which a command's own options take.

        Args:
            names: The option names already taken.

        Returns:
            Itself when no name clashes, a copy with the remaining names, or
            None when none remain.
        """
        kept = [opt for opt in self.opts if opt not in names]
        if len(kept) == len(self.opts):
            return self
        if not kept:
            return None
        assert self.name is not None
        assert self.callback is not None
        return GlobalOption(
            [*kept, self.name], callback=self.callback, help=self.help
        )


def _debug(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Switch the run's logging to `DEBUG` as soon as `-d` is parsed."""
    state = _run.state_of(ctx)
    if value and state and not state.debug and not ctx.resilient_parsing:
        state.debug = True
        _logging.configure(state.package, state.err, debug=True)


def _quiet(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Drop `info` lines & animation; notices, hints & STDOUT stay."""
    state = _run.state_of(ctx)
    if value and state and not ctx.resilient_parsing:
        state.quiet = True
        _output.silence(state.err)


def _no_color(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Drop colour from both consoles, keeping bold & dim, like `NO_COLOR`."""
    state = _run.state_of(ctx)
    if value and state and not ctx.resilient_parsing:
        state.out.no_color = True
        state.err.no_color = True


DEBUG = GlobalOption(
    ["-d", "--debug"], callback=_debug, help="Show debug logging output."
)
QUIET = GlobalOption(
    ["-q", "--quiet"],
    callback=_quiet,
    help="Hide informational messages & progress.",
)
NO_COLOR = GlobalOption(
    ["--no-color"], callback=_no_color, help="Print without colour."
)

RUN_FLAGS: tuple[GlobalOption, ...] = (DEBUG, QUIET, NO_COLOR)
"""The run flags every `pyclig.Command` accepts."""


def inherited(ctx: click.Context) -> list[GlobalOption]:
    """Return the global options declared by the ancestors of `ctx`.

    Args:
        ctx: The command's context.

    Returns:
        The flags, outermost command first.
    """
    found: list[GlobalOption] = []
    parent = ctx.parent
    while parent is not None:
        found[:0] = [
            p for p in parent.command.params if isinstance(p, GlobalOption)
        ]
        parent = parent.parent
    return found


def for_command(
    params: Sequence[click.Parameter], ctx: click.Context
) -> list[GlobalOption]:
    """Return the global options a command accepts beside its own `params`.

    Args:
        params: The command's own parameters, whose names win.
        ctx: The command's context.

    Returns:
        The inherited flags, then the run flags, minus any taken name.
    """
    taken = {name for p in params for name in (*p.opts, *p.secondary_opts)}
    flags = (flag.without(taken) for flag in (*inherited(ctx), *RUN_FLAGS))
    return [flag for flag in flags if flag is not None]
