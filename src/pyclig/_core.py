"""click classes applying the CLIG conventions to a command group.

A `pyclig.group()` gets, on top of click:

- per-run Rich consoles (`ctx.out`, `ctx.err`), created when the run starts
- `-d/--debug` on every command, accepted before or after the command name
- `-v/--version`, read from the distribution metadata only when asked
- `USAGE:` & upper-case headings, an `EXAMPLES:` section & concise help on
  a bare invocation
- the runner, which maps every outcome to an exit code (see `pyclig._run`)

License:
    SPDX-License-Identifier: Apache-2.0
"""

import functools
import sys
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Concatenate, NoReturn, ParamSpec, TypeVar

import click
from rich.console import Console

from pyclig import _logging, _run

P = ParamSpec("P")
R = TypeVar("R")

_STATE = "pyclig.state"


class HelpFormatter(click.HelpFormatter):
    """Help with `USAGE:` on its own line & upper-case section headings."""

    def write_usage(
        self, prog: str, args: str = "", prefix: str | None = None
    ) -> None:
        """Write the usage block, headed `USAGE:` on its own line.

        Args:
            prog: The command path, e.g. `dkais list`.
            args: The usage pieces after it.
            prefix: The heading, defaulting to `USAGE:`.
        """
        self.write(f"{'':>{self.current_indent}}{prefix or 'USAGE:'}\n")
        with self.indentation():
            super().write_usage(prog, args, prefix="")

    def write_heading(self, heading: str) -> None:
        """Write a section heading in upper case, e.g. `OPTIONS:`.

        Args:
            heading: The heading.
        """
        super().write_heading(heading.upper())


class Context(click.Context):
    """A click context with the run's STDOUT & STDERR consoles.

    NOTE: The consoles live in `ctx.meta`, which every context of a run
    shares, so `ctx.obj` stays free for the application.
    """

    formatter_class = HelpFormatter

    def __init__(
        self,
        *args: Any,
        pyclig_state: _run.State | None = None,
        **kwargs: Any,
    ) -> None:
        """Create the context.

        Args:
            *args: Positional `click.Context` arguments.
            pyclig_state: The run's state, given to the root context.
            **kwargs: Keyword `click.Context` arguments.
        """
        super().__init__(*args, **kwargs)
        if pyclig_state is not None:
            self.meta[_STATE] = pyclig_state

    @property
    def out(self) -> Console:
        """The STDOUT console, for the command's output."""
        return _require_state(self).out

    @property
    def err(self) -> Console:
        """The STDERR console, for messages, logs & live displays."""
        return _require_state(self).err


def _state(ctx: click.Context) -> _run.State | None:
    """Return the run's state, if the run was started by `Group.main`."""
    state = ctx.meta.get(_STATE)
    return state if isinstance(state, _run.State) else None


def _require_state(ctx: click.Context) -> _run.State:
    """Return the run's state, or raise when there is none."""
    state = _state(ctx)
    if state is None:
        raise RuntimeError("the consoles exist only within a pyclig.Group run")
    return state


def _package(ctx: click.Context) -> str:
    """Return the application package of the run."""
    state = _state(ctx)
    return state.package if state else ctx.find_root().info_name or ""


def pass_context(f: Callable[Concatenate[Context, P], R]) -> Callable[P, R]:
    """Pass the current `pyclig.Context` as the first argument.

    Args:
        f: The command function.

    Returns:
        The wrapped function.
    """

    def new_func(*args: P.args, **kwargs: P.kwargs) -> R:
        ctx = click.get_current_context()
        if not isinstance(ctx, Context):
            raise TypeError(
                f"{f.__name__} must be a command of a pyclig.Group, "
                "not of a plain click.Group"
            )
        return f(ctx, *args, **kwargs)

    return functools.update_wrapper(new_func, f)


def _debug(ctx: click.Context, param: click.Parameter, value: bool) -> None:
    """Switch the run's logging to `DEBUG` as soon as `-d` is parsed."""
    state = _state(ctx)
    if value and state and not state.debug and not ctx.resilient_parsing:
        state.debug = True
        _logging.configure(state.package, state.err, debug=True)


def _show_version(ctx: click.Context) -> str:
    """Return the `-v/--version` line, e.g. `dkais 0.1.0`."""
    return f"{ctx.find_root().info_name} {_run.version(_package(ctx))}"


class Command(click.Command):
    """A click command with `-d/--debug` & the pyclig help layout.

    NOTE: `-d` is eager, so it takes effect even when a later option is
    invalid. Usage errors raised while parsing are bound to this command, so
    they show its usage.
    """

    context_class = Context

    def __init__(self, name: str | None = None, **kwargs: Any) -> None:
        """Create the command.

        Args:
            name: The command name.
            **kwargs: Keyword `click.Command` arguments;
                `options_metavar` defaults to `[options]`.
        """
        kwargs.setdefault("options_metavar", "[options]")
        super().__init__(name, **kwargs)
        self.params.append(
            click.Option(
                ["-d", "--debug"],
                is_flag=True,
                is_eager=True,
                expose_value=False,
                callback=_debug,
                help="Show debug logging output.",
            )
        )

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Parse the arguments, binding a parse-time usage error to `ctx`.

        Args:
            ctx: The command's context.
            args: The arguments to parse.

        Returns:
            The arguments left over for a subcommand.
        """
        try:
            return super().parse_args(ctx, args)
        except click.UsageError as error:
            if error.ctx is None:
                error.ctx = ctx
            raise


class Group(Command, click.Group):
    """A click group running the CLIG conventions (see module docstring).

    NOTE: Subcommands default to `pyclig.Command` & nested groups to
    `pyclig.Group`, so `@cli.command()` & `@cli.group()` inherit `-d`.

    Attributes:
        examples: Example invocations, listed under `EXAMPLES:`.
        errors: Expected exception types, reported without a traceback.
    """

    command_class = Command
    group_class = type

    def __init__(
        self,
        name: str | None = None,
        commands: Any = None,
        *,
        examples: Iterable[str] = (),
        errors: _run.Errors = (),
        invoke_without_command: bool = True,
        subcommand_metavar: str | None = "<command>",
        context_settings: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create the group.

        Args:
            name: The group name.
            commands: The initial subcommands, by name or as a sequence.
            examples: Example invocations, listed under `EXAMPLES:`.
            errors: Expected exception types, reported without a traceback.
            invoke_without_command: Run without a subcommand, printing the
                concise help.
            subcommand_metavar: The command placeholder in the usage line.
            context_settings: Defaults for the context; `-h` & `--help`
                show help unless `help_option_names` is given.
            **kwargs: Keyword `click.Group` arguments.
        """
        settings = {"help_option_names": ["-h", "--help"]}
        super().__init__(
            name,
            commands=commands,
            invoke_without_command=invoke_without_command,
            subcommand_metavar=subcommand_metavar,
            context_settings=settings | (context_settings or {}),
            **kwargs,
        )
        self.examples = tuple(examples)
        self.errors = errors

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = False,
        **extra: Any,
    ) -> NoReturn:
        """Run the CLI with fresh consoles & logging, then exit.

        NOTE: Always exits with the mapped code; `standalone_mode` is
        accepted for click compatibility only. `windows_expand_args`
        defaults to False, so `*`, `~` & `%VAR%` reach commands as typed on
        every platform. Use `pyclig.testing.invoke` to run in-process.

        Args:
            args: The arguments, defaulting to `sys.argv[1:]`.
            prog_name: The program name, defaulting to the group name.
            complete_var: The shell completion environment variable.
            standalone_mode: Ignored.
            windows_expand_args: Expand globs & variables on Windows.
            **extra: Keyword `click.Context` arguments.
        """
        make_consoles = extra.pop("pyclig_consoles", _run.make_consoles)
        _run.configure_streams()
        out, err = make_consoles()
        prog = prog_name or self.name or "main"
        package = _run.package_of(self.callback, default=prog)
        state = _run.State(out, err, package, self.errors)
        click_main = super().main
        with _logging.scoped(package):
            _logging.configure(package, err, debug=False)
            code = _run.execute(
                lambda: click_main(
                    args,
                    prog,
                    complete_var,
                    standalone_mode=False,
                    windows_expand_args=windows_expand_args,
                    pyclig_state=state,
                    **extra,
                ),
                state,
                prog=prog,
            )
        sys.exit(code)

    def invoke(self, ctx: click.Context) -> Any:
        """Invoke the group, printing concise help when no command is given.

        NOTE: Ctrl-C, `EOFError` & broken pipes are carried past click,
        which would print a blank line, report "Aborted!" or exit silently.

        Args:
            ctx: The group's context.

        Returns:
            The subcommand's return value.

        Raises:
            Interrupted: On Ctrl-C.
            Escaped: Carrying an `EOFError` or a pipe `OSError`.
        """
        try:
            result = super().invoke(ctx)
        except KeyboardInterrupt as error:
            raise _run.Interrupted from error
        except EOFError as error:
            raise _run.Escaped(error) from error
        except OSError as error:
            if error.errno in _run.PIPE_ERRNOS:
                raise _run.Escaped(error) from error
            raise
        if ctx.invoked_subcommand is None:
            click.echo(self.get_concise_help(ctx))
        return result

    def get_concise_help(self, ctx: click.Context) -> str:
        """Return the concise help printed for a bare invocation.

        Args:
            ctx: The group's context.

        Returns:
            The summary & version, description, usage, commands, examples
            & a `--help` hint.
        """
        formatter = ctx.make_formatter()
        header = _show_version(ctx)
        formatter.write_text(
            f"{self.short_help} [{header}]" if self.short_help else header
        )
        self.format_help_text(ctx, formatter)
        formatter.write_paragraph()
        self.format_usage(ctx, formatter)
        self.format_commands(ctx, formatter)
        self.format_examples(ctx, formatter)
        hint = _run.help_hint(ctx)
        if hint:
            formatter.write_paragraph()
            formatter.write_text(hint)
        return formatter.getvalue().rstrip("\n")

    def format_examples(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Write the `EXAMPLES:` section, one invocation per line.

        Args:
            ctx: The group's context.
            formatter: The help formatter.
        """
        if not self.examples:
            return
        with formatter.section("Examples"):
            for example in self.examples:
                formatter.write(f"{'':>{formatter.current_indent}}{example}\n")

    def format_epilog(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Write the `EXAMPLES:` section, then the epilog.

        Args:
            ctx: The group's context.
            formatter: The help formatter.
        """
        self.format_examples(ctx, formatter)
        super().format_epilog(ctx, formatter)


def group(
    name: str | None = None,
    *,
    examples: Iterable[str] = (),
    errors: _run.Errors = (),
    **kwargs: Any,
) -> Callable[[Callable[..., Any]], Group]:
    """Create a `pyclig.Group` with `-v/--version` from a function.

    ```python
    @pyclig.group(
        "dkais",
        short_help="DMA AIS data manager",
        examples=["dkais list --start 2026-10"],
        errors=(exceptions.Error,),
    )
    def cli() -> None:
        \"\"\"Download DMA AIS archives and convert them to Parquet.\"\"\"
    ```

    Args:
        name: The program name, e.g. `dkais`.
        examples: Example invocations, listed under `EXAMPLES:`.
        errors: Expected exception types, reported as `error: message` &
            exit 1 - the traceback is shown only with `-d`.
        **kwargs: Keyword `click.Group` arguments, e.g. `short_help` (the
            concise help summary) & `epilog`.

    Returns:
        A decorator turning the group callback into a `Group`.
    """

    def decorator(f: Callable[..., Any]) -> Group:
        f = click.custom_version_option(
            _show_version,
            "-v",
            "--version",
            help="Show the version and exit.",
        )(f)
        return click.group(
            name, cls=Group, examples=examples, errors=errors, **kwargs
        )(f)

    return decorator
