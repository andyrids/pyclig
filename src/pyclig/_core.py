"""click classes applying the CLIG conventions to a command or group.

A `pyclig.command()` or `pyclig.group()` gets, on top of click:

- per-run Rich consoles (`ctx.out`, `ctx.err`), created when the run starts
- `-d/--debug` on every command, accepted before or after the command name
- `-v/--version`, read from the distribution metadata only when asked
- `-h` as well as `--help`, `USAGE:` & upper-case headings, examples first
  & concise help when a group runs bare or a command lacks its arguments
- the runner, which maps every outcome to an exit code (see `pyclig._run`)

License:
    SPDX-License-Identifier: Apache-2.0
"""

import contextlib
import functools
import sys
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Concatenate,
    NoReturn,
    ParamSpec,
    TypeVar,
)

import click
from rich.console import Console

from pyclig import _config, _flags, _logging, _output, _run
from pyclig._exit import ExitCode
from pyclig._flags import GlobalOption

if TYPE_CHECKING:
    from rich.table import Table

P = ParamSpec("P")
R = TypeVar("R")


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
    shares, so `ctx.obj` stays free for the application. A root context
    takes `-h` & `--help` as its help option names unless given others;
    subcontexts inherit their parent's, as in click.
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
        parent = args[1] if len(args) > 1 else kwargs.get("parent")
        if parent is None and kwargs.get("help_option_names") is None:
            kwargs["help_option_names"] = ["-h", "--help"]
        super().__init__(*args, **kwargs)
        if pyclig_state is not None:
            self.meta[_run.STATE_KEY] = pyclig_state

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """Invoke a callback, raising a deferred config file error first.

        NOTE: click calls every command & group callback through here, so
        a `ConfigError` kept on the state surfaces before any application
        code runs with defaults that miss the config. `--help`, `help sub`
        & `-v` exit earlier, in parsing & command resolution.

        Args:
            *args: The callback & its positional arguments.
            **kwargs: The callback's keyword arguments.

        Returns:
            The callback's return value.
        """
        state = _run.state_of(self)
        if state is not None and state.config_error is not None:
            raise state.config_error
        return super().invoke(*args, **kwargs)

    @property
    def out(self) -> Console:
        """The STDOUT console, for the command's output."""
        return _require_state(self).out

    @property
    def err(self) -> Console:
        """The STDERR console, for messages, logs & live displays."""
        return _require_state(self).err

    @property
    def quiet(self) -> bool:
        """Whether `-q/--quiet` was given: print only what the user needs."""
        return _require_state(self).quiet

    @property
    def format(self) -> _run.Format:
        """The STDOUT format to produce: `human`, `plain` or `json`.

        NOTE: `human` on a terminal, else `plain`; `--plain` & `--json`
        (`pyclig.options`) override it, `--json` winning in any order.
        """
        return _require_state(self).format

    @property
    def can_prompt(self) -> bool:
        """Whether STDIN & STDERR are terminals and `--no-input` was not given.

        NOTE: `pyclig.confirm` & click `prompt=` options check this
        themselves; read it before an interactive flow of your own.
        """
        return _require_state(self).can_prompt

    def emit(
        self,
        records: Iterable[Mapping[str, object]],
        *,
        table: Callable[[], "Table"] | None = None,
        caption: str | None = None,
    ) -> None:
        """Print `records` to STDOUT in the run's format.

        - `json`: an indented list, other values as `str()`; no caption.
          `NaN` & infinities are not JSON: convert them first, or the run
          fails as a bug (exit 70) rather than print what parsers reject.
        - `plain`: TSV without a header, the first record's keys as the
          columns; the caption goes to `info(ctx.err)`.
        - `human`: `table()`, or a `SIMPLE_HEAD` table with a column per
          key; the caption is set below it.

        Plain cells: `None` is empty, bools are `true`/`false`, tabs &
        newlines become one space and a missing key is empty, so `cut` &
        `awk` see one row per record. With no records, JSON prints `[]`,
        the others print nothing and the caption goes to `info`.

        NOTE: `table` is a factory because cells often depend on other
        fields; it also keeps `rich.table` off the fast paths.

        Args:
            records: The rows, as mappings.
            table: Builds the human table, e.g. with aligned columns.
            caption: A line about the rows, e.g. `3 archives, 2.1 MB`.
        """
        _output.emit(
            self.out,
            self.err,
            fmt=self.format,
            records=records,
            table=table,
            caption=caption,
        )

    @contextlib.contextmanager
    def pager(self) -> Iterator[None]:
        """Page what the block prints on `ctx.out`, in `human` format only.

        ```python
        with ctx.pager():
            ctx.emit(rows, table=make_table, caption=caption)
        ```

        The page goes through `click.echo_via_pager`, so `PAGER` is
        honoured and `less` gets `LESS=-FIRX` when `LESS` is unset. A
        no-op in `plain` & `json`, which are for pipes; `-q` marks STDERR
        only, so a `human` run still pages. On Windows paging is opt-in:
        with `PAGER` blank the output prints directly, because click's
        fallback there is `more`, which garbles UTF-8 & cannot scroll;
        `PAGER=less` (Git for Windows ships one) pages in colour.

        NOTE: Output is held until the block ends, then paged in one go.
        If the block raises, what it printed is flushed to STDOUT unpaged.
        `click.echo` inside the block bypasses the page and prints at once.

        Yields:
            Nothing; the pager runs when the block ends.
        """
        if self.format != "human" or not _output.pages_by_default():
            yield
            return
        with self.out.pager(pager=_output._ClickPager(), styles=True):
            yield


def _require_state(ctx: click.Context) -> _run.State:
    """Return the run's state, or raise when there is none."""
    state = _run.state_of(ctx)
    if state is None:
        raise RuntimeError(
            "the consoles exist only within a run started by a pyclig "
            "command's main() - or by pyclig.testing.invoke"
        )
    return state


def _package(ctx: click.Context) -> str:
    """Return the application package of the run."""
    state = _run.state_of(ctx)
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
                f"{f.__name__} must be a pyclig.Command, "
                "not a plain click command"
            )
        return f(ctx, *args, **kwargs)

    return functools.update_wrapper(new_func, f)


def confirm(ctx: click.Context, *, message: str, force: bool) -> None:
    """Ask the user to confirm a large or destructive action.

    | Case                          | Outcome                                |
    | ----------------------------- | -------------------------------------- |
    | `force`                       | Returns, without a prompt              |
    | STDIN or STDERR not a terminal| `error:` naming `--force`, usage - 2   |
    | `--no-input`                  | `error:` naming both flags, usage - 2  |
    | `y` / `yes`                   | Returns                                |
    | `n`, empty answer, EOF        | `error: aborted` - exit 1              |
    | Ctrl-C                        | `warning: interrupted` - exit 130      |

    NOTE: Without a terminal on STDIN nobody can answer, and without one on
    STDERR (`2>log`) nobody sees the question, so the run fails with a
    usage error naming the flag a script should pass. Call it before
    starting any live display (`Progress`, `Status`). Under `CliRunner`
    (`pyclig.testing.invoke`) click also echoes the typed answer to STDERR.

    ```python
    @cli.command()
    @pyclig.options.force()
    @pyclig.pass_context
    def purge(ctx: pyclig.Context, force: bool) -> None:
        \"\"\"Delete every archive.\"\"\"
        pyclig.confirm(ctx, message="Delete every archive?", force=force)
    ```

    Args:
        ctx: The command's context.
        message: The question, e.g. `Delete 12 archives?`.
        force: Skip the prompt, e.g. for `-f/--force`.

    Raises:
        click.UsageError: When the run cannot prompt.
        click.Abort: When the prompt is declined or interrupted.
    """
    if force:
        return
    state = _require_state(ctx)
    if not state.can_prompt:
        raise click.UsageError(
            f"confirmation needed, but {_cannot_prompt(state)} - "
            "pass `--force` to proceed",
            ctx=ctx,
        )
    click.confirm(message, default=False, abort=True, err=True)


def _cannot_prompt(state: _run.State) -> str:
    """Return why the run cannot prompt, for a usage error."""
    if state.no_input:
        return "`--no-input` was given"
    return "there is no terminal to ask on"


def _prompt(
    option: click.Option,
    prompt: Callable[[click.Context], Any],
    ctx: click.Context,
) -> Any:
    """Prompt for `option` on STDERR; otherwise its default, or fail.

    NOTE: click prompts on STDOUT, where a `prog > file` would hide the
    question; the prompt is a message, so STDOUT is redirected to STDERR
    for its duration. When the run cannot prompt, the option's own default
    (`default=`, callable or from `default_map`) is the answer - the
    guidelines ask for a failure only when input is required. A flag
    prompting without a default fails, as click would force an answer.

    Args:
        option: The option with `prompt=`.
        prompt: click's `prompt_for_value`, bound to `option`.
        ctx: The command's context.

    Returns:
        The answer or the default, processed later by the option's type.

    Raises:
        click.UsageError: When the run cannot prompt & there is no default.
    """
    state = _run.state_of(ctx)
    if state is not None and not state.can_prompt:
        default = click.Parameter.get_default(option, ctx)
        if default is not None and not option.value_is_missing(default):
            return default
        raise click.UsageError(
            f"{option.get_error_hint(ctx)} needs a value, but "
            f"{_cannot_prompt(state)} - pass it on the command line",
            ctx=ctx,
        )
    with contextlib.redirect_stdout(sys.stderr):
        return prompt(ctx)


def _show_version(ctx: click.Context) -> str:
    """Return the `-v/--version` line, e.g. `dkais 0.1.0`."""
    return f"{ctx.find_root().info_name} {_run.version(_package(ctx))}"


def _help_if_asked(ctx: click.Context, args: Sequence[str]) -> None:
    """Show the help & exit 0 when a help flag appears before any `--`.

    NOTE: A help name the command's own options take (`-h/--host`) is not
    a help flag there, as click's `get_help_option_names` decides.

    Args:
        ctx: The context whose help to show.
        args: The arguments as given, before parsing consumed them.
    """
    command = ctx.command
    if ctx.resilient_parsing or not command.add_help_option:
        return
    head = args[: args.index("--")] if "--" in args else args
    if set(command.get_help_option_names(ctx)) & set(head):
        click.echo(ctx.get_help(), color=ctx.color)
        ctx.exit()


class Command(click.Command):
    """A click command with the run flags, the pyclig help layout & runner.

    NOTE: The run flags (`-d`, `-q`, `--no-color`, `--no-input` & any
    `GlobalOption` of an ancestor) are added by `get_params`, so parsing,
    help & completion all see them; a command's own option with the same
    spelling wins. An option with `prompt=` prompts on STDERR; when the run
    cannot prompt it takes its default, or fails naming itself without
    one. Usage errors raised while
    parsing are bound to this command, so they show its usage. `main` runs
    the command with fresh consoles & logging; `errors` is read from the
    command `main` is called on.

    Attributes:
        examples: Example invocations, listed under `EXAMPLES:`.
        errors: Expected exception types, reported without a traceback.
    """

    context_class = Context

    def __init__(
        self,
        name: str | None = None,
        *,
        examples: Iterable[str] = (),
        errors: _run.Errors = (),
        config: _config.Config | None = None,
        **kwargs: Any,
    ) -> None:
        """Create the command.

        Args:
            name: The command name.
            examples: Example invocations, listed under `EXAMPLES:` before
                the options.
            errors: Expected exception types, reported without a traceback.
                Only the root command's are read.
            config: The configuration files to read, adding `--config` (&
                `--profile`) as the first options. Root command only.
            **kwargs: Keyword `click.Command` arguments;
                `options_metavar` defaults to `[options]`.
        """
        kwargs.setdefault("options_metavar", "[options]")
        super().__init__(name, **kwargs)
        self.examples = tuple(examples)
        self.errors = errors
        self.config = config
        if config is not None:
            self.params[:0] = _config.options(config)
        for param in self.params:
            if not isinstance(param, click.Option):
                continue
            if param.prompt is not None:
                gated = functools.partial(
                    _prompt, param, param.prompt_for_value
                )
                setattr(param, "prompt_for_value", gated)
            if param.envvar:
                resolve = functools.partial(
                    _config.dotenv_value, param, param.resolve_envvar_value
                )
                setattr(param, "resolve_envvar_value", resolve)

    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
        """Return the own parameters, the global options, then help.

        Args:
            ctx: The command's context.

        Returns:
            The parameters, in parsing & help order.
        """
        help_option = self.get_help_option(ctx)
        own = [p for p in super().get_params(ctx) if p is not help_option]
        tail = [help_option] if help_option is not None else []
        return [*own, *_flags.for_command(own, ctx), *tail]

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Parse the arguments; a help flag wins over any usage error.

        NOTE: click's parser pops from `args`, so the list is snapshotted
        first. A usage error raised while parsing is bound to `ctx`, so it
        shows this command's usage.

        Args:
            ctx: The command's context.
            args: The arguments to parse.

        Returns:
            The arguments left over for a subcommand.
        """
        if not args and self.no_args_is_help and not ctx.resilient_parsing:
            click.echo(self.get_concise_help(ctx), err=True)
            ctx.exit(ExitCode.USAGE)
        given = list(args)
        try:
            return super().parse_args(ctx, args)
        except click.UsageError as error:
            if error.ctx is None:
                error.ctx = ctx
            _help_if_asked(ctx, given)
            raise

    def format_help(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Write the help: usage, description, examples, options & epilog.

        NOTE: Examples lead, as the CLI guidelines ask; a group's options
        section lists its commands first (see `Group.format_options`).

        Args:
            ctx: The command's context.
            formatter: The help formatter.
        """
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_examples(ctx, formatter)
        self.format_arguments(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_epilog(ctx, formatter)

    def format_examples(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Write the `EXAMPLES:` section, one invocation per line.

        Args:
            ctx: The command's context.
            formatter: The help formatter.
        """
        if not self.examples:
            return
        with formatter.section("Examples"):
            for example in self.examples:
                formatter.write(f"{'':>{formatter.current_indent}}{example}\n")

    def format_options(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Write `OPTIONS:`, then `GLOBAL OPTIONS:`.

        NOTE: The root (or a standalone command) lists its global options in
        full. A subcommand lists those it declares itself in full & the rest
        on one line, pointing at the root's help.

        Args:
            ctx: The command's context.
            formatter: The help formatter.
        """
        own: list[tuple[str, str]] = []
        full: list[tuple[str, str]] = []
        brief: list[click.Parameter] = []
        for param in self.get_params(ctx):
            record = param.get_help_record(ctx)
            if record is None or isinstance(param, click.Argument):
                continue
            if not isinstance(param, GlobalOption):
                own.append(record)
            elif ctx.parent is None or param in self.params:
                full.append(record)
            else:
                brief.append(param)
        if own:
            with formatter.section("Options"):
                formatter.write_dl(own)
        if full or brief:
            with formatter.section("Global options"):
                if full:
                    formatter.write_dl(full)
                if brief:
                    names = ", ".join("/".join(p.opts) for p in brief)
                    root = ctx.find_root().command_path
                    formatter.write_text(f"{names} - see '{root} --help'.")

    def get_concise_help(self, ctx: click.Context) -> str:
        """Return the concise help, printed when a command needs arguments.

        Args:
            ctx: The command's context.

        Returns:
            The help without its options, ending with a `--help` hint.
        """
        formatter = ctx.make_formatter()
        self.format_concise_help(ctx, formatter)
        hint = _run.help_hint(ctx)
        if hint:
            formatter.write_paragraph()
            formatter.write_text(hint)
        return formatter.getvalue().rstrip("\n")

    def format_concise_help(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Write the concise help: usage, description & examples.

        Args:
            ctx: The command's context.
            formatter: The help formatter.
        """
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_examples(ctx, formatter)

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
            prog_name: The program name, defaulting to the command name.
            complete_var: The shell completion environment variable.
            standalone_mode: Ignored.
            windows_expand_args: Expand globs & variables on Windows.
            **extra: Keyword `click.Context` arguments.
        """
        make_consoles = extra.pop("pyclig_consoles", _run.make_consoles)
        in_tty = extra.pop("pyclig_in_tty", None)
        err_tty = extra.pop("pyclig_err_tty", None)
        discover = extra.pop("pyclig_discover", True)
        _run.configure_streams()
        out, err = make_consoles()
        prog = prog_name or self.name or "main"
        package = _run.package_of(self.callback, default=prog)
        state = _run.State(
            out,
            err,
            package,
            self.errors,
            in_tty=_run.is_tty(sys.stdin) if in_tty is None else in_tty,
            err_tty=_run.is_tty(sys.stderr) if err_tty is None else err_tty,
            format="human" if out.is_terminal else "plain",
            discover=discover,
        )
        _run.apply_environment(state)
        click_main = super().main
        with _logging.scoped(package):
            _logging.configure(package, err, debug=state.debug)
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
        """Invoke the command, carrying Ctrl-C, EOF & pipe errors past click.

        NOTE: click would print a blank line, report "Aborted!" or exit
        silently. A group's `super().invoke` is `click.Group.invoke`, so one
        translation covers groups & commands, and an error translated by a
        subcommand passes the outer levels untouched.

        Args:
            ctx: The command's context.

        Returns:
            The command's return value.

        Raises:
            Interrupted: On Ctrl-C.
            Escaped: Carrying an `EOFError` or a pipe `OSError`.
        """
        try:
            return super().invoke(ctx)
        except KeyboardInterrupt as error:
            raise _run.Interrupted from error
        except EOFError as error:
            raise _run.Escaped(error) from error
        except OSError as error:
            if error.errno in _run.PIPE_ERRNOS:
                raise _run.Escaped(error) from error
            raise


class Group(Command, click.Group):
    """A click group running the CLIG conventions (see module docstring).

    NOTE: Subcommands default to `pyclig.Command` & nested groups to
    `pyclig.Group`, so `@cli.command()` & `@cli.group()` inherit `-d`.
    """

    command_class = Command
    group_class = type

    def __init__(
        self,
        name: str | None = None,
        commands: Any = None,
        *,
        invoke_without_command: bool = True,
        subcommand_metavar: str | None = "<command>",
        **kwargs: Any,
    ) -> None:
        """Create the group.

        Args:
            name: The group name.
            commands: The initial subcommands, by name or as a sequence.
            invoke_without_command: Run without a subcommand, printing the
                concise help.
            subcommand_metavar: The command placeholder in the usage line.
            **kwargs: Keyword `Command` & `click.Group` arguments, e.g.
                `examples`, `errors` & `context_settings`.
        """
        super().__init__(
            name,
            commands=commands,
            invoke_without_command=invoke_without_command,
            subcommand_metavar=subcommand_metavar,
            **kwargs,
        )

    def list_commands(self, ctx: click.Context) -> list[str]:
        """List the subcommands in the order they were added.

        NOTE: click sorts them by name; the order a CLI defines them in is
        usually its workflow, e.g. `list`, `download`, `process`.

        Args:
            ctx: The group's context.

        Returns:
            The subcommand names.
        """
        return list(self.commands)

    def add_command(self, cmd: click.Command, name: str | None = None) -> None:
        """Add a subcommand, rejecting one that sets `errors=` or `config=`.

        NOTE: The runner reads `errors` from the root only, so a subcommand's
        would be ignored silently; config files are read for the whole run.

        Args:
            cmd: The subcommand.
            name: Its name, defaulting to `cmd.name`.

        Raises:
            TypeError: When `cmd` sets `errors=` or `config=`.
        """
        if isinstance(cmd, Command):
            for keyword, value in (
                ("errors", cmd.errors),
                ("config", cmd.config),
            ):
                if value:
                    raise TypeError(
                        f"{name or cmd.name} sets {keyword}=, which only the "
                        "root command may do"
                    )
        super().add_command(cmd, name)

    def invoke(self, ctx: click.Context) -> Any:
        """Invoke the group, printing concise help when no command is given.

        Args:
            ctx: The group's context.

        Returns:
            The subcommand's return value.
        """
        state = _run.state_of(ctx)
        if (
            state is not None
            and state.config_error is not None
            and not ctx.resilient_parsing
        ):
            # Let `help sub` & `sub --help` answer first (they exit here),
            # then fail before this group's own callback runs
            args = [*getattr(ctx, "_protected_args", ()), *ctx.args]
            if args:
                name, cmd, rest = self.resolve_command(ctx, args)
                if cmd is not None:
                    cmd.make_context(name, rest, parent=ctx)
            raise state.config_error
        result = super().invoke(ctx)
        if ctx.invoked_subcommand is None:
            click.echo(self.get_concise_help(ctx))
        return result

    def format_options(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Write the `COMMANDS:` section, then the options as a `Command`.

        NOTE: Explicit, because `pyclig.Command` precedes `click.Group` in
        the method resolution order.

        Args:
            ctx: The group's context.
            formatter: The help formatter.
        """
        self.format_commands(ctx, formatter)
        Command.format_options(self, ctx, formatter)

    def format_concise_help(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Write the concise help printed for a bare invocation.

        Args:
            ctx: The group's context.
            formatter: The help formatter.
        """
        header = _show_version(ctx)
        formatter.write_text(
            f"{self.short_help} [{header}]" if self.short_help else header
        )
        self.format_help_text(ctx, formatter)
        formatter.write_paragraph()
        self.format_usage(ctx, formatter)
        self.format_commands(ctx, formatter)
        self.format_examples(ctx, formatter)

    def resolve_command(
        self, ctx: click.Context, args: list[str]
    ) -> tuple[str | None, click.Command | None, list[str]]:
        """Resolve the subcommand; a help flag wins over an unknown name.

        `help [NAME...]` shows the help of the named command, or of this
        group, & exits 0, unless the group has a `help` command of its own.
        It is never in `.commands`, so it is not listed under `COMMANDS:`.

        NOTE: Options before `help` are parsed first, so a required root
        option errors before `prog help` can answer.

        Args:
            ctx: The group's context.
            args: The remaining arguments, the command name first.

        Returns:
            The command name, the command & the arguments after it.
        """
        if (
            args
            and args[0] == "help"
            and not ctx.resilient_parsing
            and self.get_command(ctx, "help") is None
        ):
            self._help_command(ctx, args[1:])
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            _help_if_asked(ctx, args)
            raise

    def _help_command(self, ctx: click.Context, args: list[str]) -> NoReturn:
        """Show the help of the command `args` name, or of `ctx`, & exit 0.

        NOTE: Each name resolves through `resolve_command`, so an unknown
        one gets click's error & suggestions. A child context is built
        without parsing, so the named command's options are not required.

        Args:
            ctx: The group's context.
            args: The arguments after `help`; dashed ones are ignored.

        Raises:
            click.UsageError: For a name that is not a command, or a
                name after a command that has no subcommands.
        """
        current = ctx
        for name in (arg for arg in args if not arg.startswith("-")):
            group = current.command
            if not isinstance(group, click.Group):
                current.fail(f"Got unexpected extra argument ({name})")
            _, sub, _ = group.resolve_command(current, [name])
            if sub is None:
                current.fail(f"No such command '{name}'.")
            current = sub.context_class(
                sub, info_name=name, parent=current, **sub.context_settings
            )
        click.echo(current.get_help(), color=ctx.color)
        ctx.exit()


def command(
    name: str | None = None,
    *,
    examples: Iterable[str] = (),
    errors: _run.Errors = (),
    config: _config.Config | None = None,
    **kwargs: Any,
) -> Callable[[Callable[..., Any]], Command]:
    """Create a standalone `pyclig.Command` with `-v/--version`.

    NOTE: For a CLI with several commands use `pyclig.group`; a command of
    a group gets everything a standalone command does.

    Args:
        name: The program name, e.g. `tool`.
        examples: Example invocations, listed under `EXAMPLES:`.
        errors: Expected exception types, reported as `error: message` &
            exit 1 - the traceback is shown only with `-d`.
        config: The configuration files to read, adding `--config` (&
            `--profile` with `profiles=True`).
        **kwargs: Keyword `click.Command` arguments, e.g. `epilog`.

    Returns:
        A decorator turning the function into a `Command`.
    """

    def decorator(f: Callable[..., Any]) -> Command:
        return click.command(
            name,
            cls=Command,
            examples=examples,
            errors=errors,
            config=config,
            **kwargs,
        )(_versioned(f))

    return decorator


def _versioned(f: Callable[..., Any]) -> Callable[..., Any]:
    """Add `-v/--version` to a command function, minus names its options take.

    NOTE: An app's own spelling wins, as for the run flags: `-v/--verbose`
    keeps `--version` alone, and an app's own `--version` leaves nothing.
    """
    params = getattr(f, "__click_params__", [])
    taken = {name for p in params for name in (*p.opts, *p.secondary_opts)}
    names = [name for name in ("-v", "--version") if name not in taken]
    if not names:
        return f
    return click.custom_version_option(
        _show_version, *names, help="Show the version and exit."
    )(f)


def run(
    func: Callable[[], int | None], *, errors: _run.Errors = ()
) -> NoReturn:
    """Run a parser-less entry point, e.g. a pre-commit hook shim.

    NOTE: For a CLI with commands & flags use `pyclig.group` instead. `run`
    shares its error handling & logging but leaves `sys.argv` to `func`.
    It enters a `pyclig.Context`, so `func` may be a `pass_context`
    function using `ctx.err`.

    ```python
    def ruff_format() -> NoReturn:
        pyclig.run(
            lambda: core_ruff_format(sys.argv[1:]),
            errors=(exceptions.Error,),
        )
    ```

    Args:
        func: The entry point logic, returning an exit code or None.
        errors: Expected exception types, reported without a traceback.
    """
    _run.configure_streams()
    out, err = _run.make_consoles()
    prog = Path(sys.argv[0]).stem or "main"
    state = _run.State(
        out,
        err,
        _run.package_of(func, default=prog),
        errors,
        in_tty=_run.is_tty(sys.stdin),
        err_tty=_run.is_tty(sys.stderr),
        format="human" if out.is_terminal else "plain",
    )
    _run.apply_environment(state)
    ctx = Context(click.Command(prog), info_name=prog, pyclig_state=state)
    with _logging.scoped(state.package), ctx:
        _logging.configure(state.package, err, debug=state.debug)
        code = _run.execute(func, state, prog=prog)
    sys.exit(code)


def group(
    name: str | None = None,
    *,
    examples: Iterable[str] = (),
    errors: _run.Errors = (),
    config: _config.Config | None = None,
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
        config: The configuration files to read, adding `--config` (&
            `--profile` with `profiles=True`) to every command.
        **kwargs: Keyword `click.Group` arguments, e.g. `short_help` (the
            concise help summary) & `epilog`.

    Returns:
        A decorator turning the group callback into a `Group`.
    """

    def decorator(f: Callable[..., Any]) -> Group:
        return click.group(
            name,
            cls=Group,
            examples=examples,
            errors=errors,
            config=config,
            **kwargs,
        )(_versioned(f))

    return decorator
