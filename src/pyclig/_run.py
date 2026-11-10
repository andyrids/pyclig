"""Run a CLI & turn its outcome into an exit code & STDERR message.

The runner is the fallback for anything a command does not handle itself.
A returned exit code passes through untouched, so a command may catch
Ctrl-C or its own errors to print a tailored message first.

| Outcome                    | STDERR                               | Exit   |
| -------------------------- | ------------------------------------ | ------ |
| `return code`              | -                                    | code   |
| `click.UsageError`         | `error:`, usage & `--help` hint      | 2      |
| Other `ClickException`     | `error:`                             | its    |
| Ctrl-C or Ctrl-Break       | `warning: interrupted`               | 130    |
| SIGTERM                    | `warning: terminated`                | 143    |
| `click.Abort` (declined)   | `error: aborted`                     | 1      |
| Exception in `errors`      | `error:` (traceback first with `-d`) | 1      |
| Broken STDOUT pipe         | - (the reader left, e.g. `head`)     | 1      |
| Any other exception        | traceback, `error:` & bug hint       | 70     |

An exception type in `errors` may carry a `hint` (printed dim, after the
message, where the eye lands) & an `exit_code` replacing 1 - honoured only
when it is a non-zero, non-bool `int`, since an error must not exit 0. Both
are read by attribute, so the application's exceptions need no pyclig
import.

A signal's notice is printed at once by the run's handler (`_signals`),
before the stack unwinds to the runner, which then only maps the code.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import contextlib
import errno
import io
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TextIO

import click
from rich.console import Console

from pyclig import _logging, _signals
from pyclig._exit import ExitCode
from pyclig._output import _plain, hint, notice, print_exception

Errors = tuple[type[Exception], ...]
"""Expected exception types, reported as `error: message` & exit 1."""

Format = Literal["human", "plain", "json"]
"""The STDOUT format a command should produce (`ctx.format`)."""

_ISSUE_LABELS = frozenset(
    {"bugreports", "bugs", "bugtracker", "issues", "issuetracker", "tracker"}
)
"""`Project-URL` labels for a bug tracker, normalised per PEP 753."""

PIPE_ERRNOS = frozenset({errno.EPIPE, errno.EINVAL})
"""A broken pipe's `OSError.errno`: EPIPE on POSIX, EINVAL on Windows."""

STATE_KEY = "pyclig.state"
"""The `ctx.meta` key holding the run's `State`."""


@dataclass
class State:
    """The state of one run, shared by every context of the run.

    Attributes:
        out: The STDOUT console.
        err: The STDERR console, shared by logging & live displays.
        package: The application package - its logger & distribution.
        errors: Expected exception types.
        debug: Whether `-d/--debug` or `<PROG>_DEBUG` was given.
        quiet: Whether `-q/--quiet` was given.
        no_input: Whether `--no-input` was given.
        in_tty: Whether STDIN is a terminal, so a prompt can be answered.
        err_tty: Whether STDERR is a terminal, so a prompt can be seen -
            the real `isatty`, which `FORCE_COLOR` does not change.
        format: The STDOUT format: `human` on a terminal, else `plain`,
            unless `--plain` or `--json` says otherwise.
        discover: Whether config files are searched for; `--config` & the
            `<PROG>_CONFIG` file are read regardless.
        config_files: The config files read, lowest precedence first.
        dotenv: The `./.env` values, read with `Config(dotenv=True)`; they
            fill declared `envvar=` options & never reach `os.environ`.
        config_error: The first error met reading the config files, raised
            when a command is invoked, so help & version never fail on it.
        signal: The signal received, recorded by the run's handler.
        announced: Whether the handler has printed the signal's notice.
        cleaning: The depth of active `ctx.cleanup` blocks, inside which
            a first signal is recorded but does not raise.
        watcher: The outermost active block's watcher thread, or None.
        log_file: The debug log file, from `<PROG>_LOG_FILE`, or None.
    """

    out: Console
    err: Console
    package: str
    errors: Errors = ()
    debug: bool = False
    quiet: bool = False
    no_input: bool = False
    in_tty: bool = False
    err_tty: bool = False
    format: Format = "plain"
    discover: bool = True
    config_files: tuple[Path, ...] = ()
    dotenv: dict[str, str] = field(default_factory=dict)
    config_error: click.ClickException | None = None
    signal: int | None = None
    announced: bool = False
    cleaning: int = 0
    watcher: _signals.Watcher | None = None
    log_file: Path | None = None

    @property
    def can_prompt(self) -> bool:
        """Whether a prompt can be seen & answered, and was not refused."""
        return self.in_tty and self.err_tty and not self.no_input

    @property
    def env_prefix(self) -> str:
        """The `<PROG>` of `<PROG>_DEBUG`: `prefix_of` the package."""
        return prefix_of(self.package)


def prefix_of(package: str) -> str:
    """Return the environment variable prefix of a package.

    Args:
        package: The application package, e.g. `my-tool.cli`.

    Returns:
        The package upper-cased, `_` replacing every non-word character,
        e.g. `MY_TOOL_CLI`.
    """
    return re.sub(r"\W", "_", package).upper()


RUN_VARIABLES = ("DEBUG", "NO_COLOR", "CONFIG", "PROFILE", "LOG_FILE")
"""The `<PROG>_` variables a run reads."""


def cleared(callback: object, prog: str) -> dict[str, None]:
    """Return the `<PROG>_` variables of a run, unset, for a test runner.

    Args:
        callback: The command's callback, which names the package.
        prog: The program name, the package when the module is unknown.

    Returns:
        Each `RUN_VARIABLES` name, prefixed, mapped to None.
    """
    prefix = prefix_of(package_of(callback, default=prog))
    return dict.fromkeys(f"{prefix}_{var}" for var in RUN_VARIABLES)


_FALSE = frozenset({"", "0", "false", "no", "off"})
"""`<PROG>_DEBUG` & `<PROG>_NO_COLOR` values that mean off, lower-cased."""


def apply_environment(state: State) -> None:
    """Honour `<PROG>_DEBUG`, `<PROG>_NO_COLOR` & `<PROG>_LOG_FILE` first.

    NOTE: A variable is on when set, non-empty & not `0`, `false`, `no` or
    `off`, unlike bare `NO_COLOR`, which Rich honours whenever it is set.
    Neither is shown in `--help`. A later `-d` or `--no-color` is a no-op.
    `-d` from the variable means the whole run, parsing included, logs at
    `DEBUG`, so the caller configures logging from `state.debug`. A
    non-blank `<PROG>_LOG_FILE` names the debug log file, `state.log_file`.

    Args:
        state: The run's state, with the consoles to drop colour from.
    """
    prefix = state.env_prefix
    if _truthy(os.environ.get(f"{prefix}_DEBUG")):
        state.debug = True
    if _truthy(os.environ.get(f"{prefix}_NO_COLOR")):
        state.out.no_color = True
        state.err.no_color = True
    log_file = os.environ.get(f"{prefix}_LOG_FILE", "").strip()
    if log_file:
        state.log_file = Path(log_file)


def _truthy(value: str | None) -> bool:
    """Check whether an environment variable value means on."""
    return value is not None and value.strip().lower() not in _FALSE


def state_of(ctx: click.Context) -> State | None:
    """Return the run's state, if the run was started by `Command.main`.

    Args:
        ctx: Any context of the run.

    Returns:
        The state, or None outside a run.
    """
    state = ctx.meta.get(STATE_KEY)
    return state if isinstance(state, State) else None


class Interrupted(Exception):
    """Ctrl-C, carried past click so it does not become `click.Abort`."""


class Escaped(Exception):
    """An exception carried past click, which would swallow it.

    NOTE: click turns an `EOFError` into `click.Abort` & any EPIPE into a
    silent exit 1, hiding bugs.

    Attributes:
        error: The original exception.
    """

    def __init__(self, error: Exception) -> None:
        """Wrap `error`.

        Args:
            error: The original exception.
        """
        super().__init__()
        self.error = error


def configure_streams() -> None:
    """Make STDOUT & STDERR safe for any text.

    NOTE: Redirected streams default to the locale encoding (cp1252 on
    Windows), which cannot encode glyphs such as `✓` or `→`. They become
    UTF-8, unless `PYTHONIOENCODING` chose an encoding - then unencodable
    characters are replaced instead.
    """
    # Python reads an empty value as unset, so the locale still applies
    explicit = bool(os.environ.get("PYTHONIOENCODING"))
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            if explicit:
                stream.reconfigure(errors="replace")
            else:
                stream.reconfigure(encoding="utf-8")


def make_consoles() -> tuple[Console, Console]:
    """Create the STDOUT & STDERR consoles of a run.

    Returns:
        The STDOUT & STDERR consoles.
    """
    return _console(stderr=False), _console(stderr=True)


def _console(*, stderr: bool) -> Console:
    """Create a console for a standard stream, never parsing markup.

    NOTE: The console resolves `sys.stdout` / `sys.stderr` on every write
    (`file=None`), so a test runner's captured streams are honoured. Rich
    falls back to its legacy Windows renderer, which drops colour, whenever
    the stream is not a console; a pipe is written with ANSI codes instead.
    `FORCE_COLOR` means colour only: on a pipe the console keeps the colour
    system Rich would force, but stays a non-terminal, so output is neither
    wrapped nor animated. `TTY_COMPATIBLE=1` still makes a pipe a terminal.
    """
    piped = not is_tty(sys.stderr if stderr else sys.stdout)
    legacy_windows = False if sys.platform == "win32" and piped else None
    settings: dict[str, Any] = {}
    forced = os.environ.get("FORCE_COLOR")
    if piped and forced and os.environ.get("TTY_COMPATIBLE") not in {"0", "1"}:
        probe = Console(force_terminal=True, legacy_windows=legacy_windows)
        settings = {
            "force_terminal": False,
            "color_system": probe.color_system,
        }
    return Console(
        stderr=stderr,
        markup=False,
        emoji=False,
        highlight=False,
        legacy_windows=legacy_windows,
        **settings,
    )


def is_tty(stream: TextIO | None) -> bool:
    """Check whether a standard stream is a terminal.

    NOTE: A standard stream is None under `pythonw`, & a replacement stream
    may lack `isatty`.

    Args:
        stream: The stream, e.g. `sys.stdin`.

    Returns:
        Whether the stream is a terminal.
    """
    return stream is not None and hasattr(stream, "isatty") and stream.isatty()


def package_of(func: object, default: str) -> str:
    """Return the top-level package that defines `func`.

    Args:
        func: A function, e.g. a group callback.
        default: The fallback when the module is unknown.

    Returns:
        The package name, e.g. `dkais` for `dkais.__main__`.
    """
    module = str(getattr(func, "__module__", "") or "")
    if module == "__main__":
        spec = getattr(sys.modules.get("__main__"), "__spec__", None)
        module = spec.name if spec is not None else ""
    return module.partition(".")[0] or default


def version(package: str) -> str:
    """Return the installed version of the distribution of `package`.

    Args:
        package: The import package name.

    Returns:
        The version, or `0.0.0+unknown` when it is not installed.
    """
    from importlib import metadata

    try:
        return metadata.version(_distribution(package))
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


def _distribution(package: str) -> str:
    """Return the distribution providing `package`, else `package` itself.

    NOTE: Usually the distribution shares the import name, which is a cheap
    lookup; `packages_distributions` scans every installed distribution, so
    it is the fallback. An editable install is not listed by it.
    """
    from importlib import metadata

    try:
        metadata.distribution(package)
    except metadata.PackageNotFoundError:
        names = metadata.packages_distributions().get(package)
        return names[0] if names else package
    return package


def _project_url(package: str) -> str | None:
    """Return the bug tracker `Project-URL` of the `package` distribution."""
    from importlib import metadata

    try:
        dist = metadata.metadata(_distribution(package))
    except metadata.PackageNotFoundError:
        return None
    for entry in dist.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if re.sub(r"[^a-z0-9]", "", label.lower()) in _ISSUE_LABELS:
            return str(url).strip()
    return None


def bug_hint(prog: str, package: str) -> str | None:
    """Return the line printed after an unexpected error.

    Args:
        prog: The program name, e.g. `dkais`.
        package: The application package.

    Returns:
        The hint, or None when the distribution names no bug tracker.
    """
    url = _project_url(package)
    if url is None:
        return None
    return (
        f"This is a bug in {prog} {version(package)} - please report it at "
        f"{url}, with the output above."
    )


def execute(func: Callable[[], object], state: State, *, prog: str) -> int:
    """Call `func` & map its outcome to an exit code (see module table).

    NOTE: A signal while the outcome is being reported raises out of the
    report; the run then exits at once with the signal's code.

    Args:
        func: The command, returning an exit code or None.
        state: The run's state.
        prog: The program name, for the bug hint.

    Returns:
        The process exit code.
    """
    try:
        return _execute(func, state, prog=prog)
    except KeyboardInterrupt:
        return _signals.exit_code(state)


def _execute(func: Callable[[], object], state: State, *, prog: str) -> int:
    """Call `func` & report its outcome (see module table)."""
    try:
        result = func()
        sys.stdout.flush()
    except click.exceptions.NoArgsIsHelpError as error:
        click.echo(error.ctx.get_help() if error.ctx else "", err=True)
        return ExitCode.USAGE
    except click.UsageError as error:
        _report_usage_error(state.err, error)
        return ExitCode.USAGE
    except click.ClickException as error:
        notice(state.err, level="error", message=error.format_message())
        return error.exit_code
    except (KeyboardInterrupt, Interrupted):
        return _interrupted(state)
    except click.Abort as error:
        return _aborted(state, error)
    except Escaped as escaped:
        return _failed(escaped.error, state, prog)
    except Exception as error:
        return _failed(error, state, prog)
    if isinstance(result, int) and not isinstance(result, bool):
        return result
    return ExitCode.OK


def _report_usage_error(err: Console, error: click.UsageError) -> None:
    """Print a usage error - message, the failing command's usage & a hint."""
    notice(err, level="error", message=error.format_message())
    ctx = error.ctx
    if ctx is None:
        return
    _plain(err, f"\n{ctx.get_usage()}\n")
    pointer = help_hint(ctx)
    if pointer:
        hint(err, message=pointer)


def help_hint(ctx: click.Context) -> str | None:
    """Return the `Try 'prog --help' ...` line for a command.

    Args:
        ctx: The command's context.

    Returns:
        The hint, or None when the command has no help option.
    """
    names = sorted(ctx.help_option_names, key=len, reverse=True)
    if not names:
        return None
    return f"Try '{ctx.command_path} {names[0]}' for more information."


def _interrupted(state: State) -> int:
    """Report an interrupt, unless its handler has, & return its code.

    NOTE: A `KeyboardInterrupt` raised by code - a mocked STDIN, a test -
    records no signal, so it is reported here, after unwinding, as 130.
    """
    if not state.announced:
        if state.err.is_terminal:
            state.err.line()
        notice(state.err, level="warning", message=_signals.message(state))
    return _signals.exit_code(state)


def _aborted(state: State, error: click.Abort) -> int:
    """Report a declined or interrupted prompt & return its exit code.

    NOTE: click raises `Abort` from None at a prompt, so the Ctrl-C or EOF
    behind it survives as `__context__`. EOF (Ctrl-D) leaves a terminal on
    the prompt line, so the line is ended before `error: aborted`.
    """
    cause = error.__cause__ or error.__context__
    if isinstance(cause, KeyboardInterrupt):
        return _interrupted(state)
    err = state.err
    eof = isinstance(cause, EOFError)
    # EOF on a Windows console is Ctrl-Z + Enter: the Enter ends the line
    if eof and err.is_terminal and sys.platform != "win32":
        err.line()
    notice(err, level="error", message="aborted")
    return ExitCode.FAILURE


def _failed(error: Exception, state: State, prog: str) -> int:
    """Report an exception raised by a command & return its exit code."""
    if isinstance(error, OSError) and error.errno in PIPE_ERRNOS:
        if _stdout_broken():
            _silence_stdout()
            return ExitCode.FAILURE
    error = _trim(error)
    if isinstance(error, state.errors):
        if state.debug:
            print_exception(state.err, error)
        message = str(error).strip() or type(error).__name__
        notice(state.err, level="error", message=message)
        remedy = getattr(error, "hint", None)
        if remedy:
            hint(state.err, message=str(remedy))
        code = getattr(error, "exit_code", None)
        if isinstance(code, int) and not isinstance(code, bool) and code != 0:
            return code
        return ExitCode.FAILURE
    print_exception(state.err, error)
    detail = str(error).strip()
    message = f"unexpected {type(error).__name__}"
    notice(
        state.err,
        level="error",
        message=f"{message}: {detail}" if detail else message,
    )
    report = bug_hint(prog, state.package)
    if report:
        hint(state.err, message=report)
    written = _logging.log_failure(state.package, error)
    if written:
        hint(state.err, message=f"debug log: {written}")
    return ExitCode.INTERNAL


def _stdout_broken() -> bool:
    """Check whether STDOUT's reader has gone, by flushing it again.

    NOTE: A failed flush keeps the unwritten data, so the probe fails too
    when the pipe is broken - and succeeds for an EPIPE from any other pipe.
    """
    try:
        sys.stdout.flush()
    except OSError:
        return True
    else:
        return False


def _silence_stdout() -> None:
    """Point STDOUT at devnull, so the exit-time flush cannot raise again.

    NOTE: The approach recommended by the `signal` module docs for SIGPIPE.
    A captured STDOUT without a file descriptor is left alone.
    """
    with contextlib.suppress(OSError, ValueError, io.UnsupportedOperation):
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())


def _trim(error: Exception) -> Exception:
    """Drop the leading click & pyclig frames from a traceback.

    Args:
        error: The exception.

    Returns:
        The same exception, its traceback starting at the command.
    """
    tb = error.__traceback__
    while tb and tb.tb_next and _is_internal(tb.tb_frame.f_globals):
        tb = tb.tb_next
    return error.with_traceback(tb)


def _is_internal(namespace: dict[str, object]) -> bool:
    """Check whether a frame's module belongs to click or pyclig."""
    name = str(namespace.get("__name__", ""))
    return name.partition(".")[0] in {"click", "pyclig"}
