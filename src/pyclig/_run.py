"""Run a CLI & turn its outcome into an exit code & STDERR message.

The runner is the fallback for anything a command does not handle itself.
A returned exit code passes through untouched, so a command may catch
Ctrl-C or its own errors to print a tailored message first.

| Outcome                    | STDERR                               | Exit   |
| -------------------------- | ------------------------------------ | ------ |
| `return code`              | -                                    | code   |
| `click.UsageError`         | `error:`, usage & `--help` hint      | 2      |
| Other `ClickException`     | `error:`                             | its    |
| Ctrl-C                     | `warning: interrupted`               | 130    |
| `click.Abort` (declined)   | `error: aborted`                     | 1      |
| Exception in `errors`      | `error:` (traceback first with `-d`) | 1      |
| Broken STDOUT pipe         | - (the reader left, e.g. `head`)     | 1      |
| Any other exception        | traceback, `error:` & bug hint       | 70     |

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
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, TextIO

import click
from rich.console import Console

from pyclig import _logging
from pyclig._exit import ExitCode
from pyclig._output import _plain, info, notice, print_exception

Errors = tuple[type[Exception], ...]
"""Expected exception types, reported as `error: message` & exit 1."""

_ISSUE_LABELS = frozenset(
    {"bugreports", "bugs", "bugtracker", "issues", "issuetracker", "tracker"}
)
"""`Project-URL` labels for a bug tracker, normalised per PEP 753."""

PIPE_ERRNOS = frozenset({errno.EPIPE, errno.EINVAL})
"""A broken pipe's `OSError.errno`: EPIPE on POSIX, EINVAL on Windows."""


@dataclass
class State:
    """The state of one run, shared by every context of the run.

    Attributes:
        out: The STDOUT console.
        err: The STDERR console, shared by logging & live displays.
        package: The application package - its logger & distribution.
        errors: Expected exception types.
        debug: Whether `-d/--debug` was given.
        in_tty: Whether STDIN is an interactive terminal, so a prompt can
            be answered.
    """

    out: Console
    err: Console
    package: str
    errors: Errors = ()
    debug: bool = False
    in_tty: bool = False


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
    explicit = "PYTHONIOENCODING" in os.environ
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
    """
    piped = not is_tty(sys.stderr if stderr else sys.stdout)
    return Console(
        stderr=stderr,
        markup=False,
        emoji=False,
        highlight=False,
        legacy_windows=False if sys.platform == "win32" and piped else None,
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

    Args:
        func: The command, returning an exit code or None.
        state: The run's state.
        prog: The program name, for the bug hint.

    Returns:
        The process exit code.
    """
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
        return _interrupted(state.err)
    except click.Abort as error:
        return _aborted(state.err, error)
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
    hint = help_hint(ctx)
    if hint:
        info(err, message=hint)


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


def _interrupted(err: Console) -> int:
    """Report Ctrl-C & return `ExitCode.INTERRUPT`."""
    if err.is_terminal:
        err.line()
    notice(err, level="warning", message="interrupted")
    return ExitCode.INTERRUPT


def _aborted(err: Console, error: click.Abort) -> int:
    """Report a declined or interrupted prompt & return its exit code.

    NOTE: click raises `Abort` from None at a prompt, so the Ctrl-C or EOF
    behind it survives as `__context__`. EOF (Ctrl-D) leaves a terminal on
    the prompt line, so the line is ended before `error: aborted`.
    """
    cause = error.__cause__ or error.__context__
    if isinstance(cause, KeyboardInterrupt):
        return _interrupted(err)
    if isinstance(cause, EOFError) and err.is_terminal:
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
        return ExitCode.FAILURE
    print_exception(state.err, error)
    detail = str(error).strip()
    message = f"unexpected {type(error).__name__}"
    notice(
        state.err,
        level="error",
        message=f"{message}: {detail}" if detail else message,
    )
    hint = bug_hint(prog, state.package)
    if hint:
        info(state.err, message=hint)
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


def run(func: Callable[[], int | None], *, errors: Errors = ()) -> NoReturn:
    """Run a parser-less entry point, e.g. a pre-commit hook shim.

    NOTE: For a CLI with commands & flags use `pyclig.group` instead. `run`
    shares its error handling & logging but leaves `sys.argv` to `func`.

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
    configure_streams()
    out, err = make_consoles()
    prog = Path(sys.argv[0]).stem or "main"
    state = State(out, err, package_of(func, default=prog), errors)
    with _logging.scoped(state.package):
        _logging.configure(state.package, err, debug=False)
        code = execute(func, state, prog=prog)
    sys.exit(code)
