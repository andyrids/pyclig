"""Standard flags, with the names the CLI guidelines recommend.

Each factory returns a `click.option` decorator; pass `help=` to describe
the flag in the application's own terms.

| Factory         | Flag              | Parameter     | `ctx.format` |
| --------------- | ----------------- | ------------- | ------------ |
| `json_output()` | `--json`          | `json_output` | `json`       |
| `plain()`       | `--plain`         | -             | `plain`      |
| `select_all()`  | `-a`, `--all`     | `select_all`  |              |
| `force()`       | `-f`, `--force`   | `force`       |              |
| `dry_run()`     | `-n`, `--dry-run` | `dry_run`     |              |
| `secret(name)`  | `--<name>-file`   | `<name>`      |              |

The format flags go on the commands that produce records, so help never
advertises a flag a command ignores. `--json` wins over `--plain` in any
order. `secret("api-key")` adds `--api-key-file FILE` & hands the command
the file's text (`-` reads a piped STDIN), so a secret never sits on the
command line or in the environment.

```python
@cli.command()
@pyclig.options.json_output()
@pyclig.options.plain()
@pyclig.options.select_all(help="Select every archive in the bucket.")
@pyclig.pass_context
def list_(ctx: pyclig.Context, json_output: bool, select_all: bool) -> None:
    if ctx.format == "human": ...
```

License:
    SPDX-License-Identifier: Apache-2.0
"""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import click

from pyclig import _run

FC = TypeVar("FC", bound=Callable[..., Any] | click.Command)


def _set_json(ctx: click.Context, param: click.Parameter, value: bool) -> bool:
    """Record `--json` as the run's format & pass the value on."""
    state = _run.state_of(ctx)
    if value and state is not None:
        state.format = "json"
    return value


def _set_plain(
    ctx: click.Context, param: click.Parameter, value: bool
) -> None:
    """Record `--plain` as the run's format, unless `--json` was given."""
    state = _run.state_of(ctx)
    if value and state is not None and state.format != "json":
        state.format = "plain"


def json_output(
    *,
    help: str = "Output as JSON.",  # noqa: A002 - click's own keyword
) -> Callable[[FC], FC]:
    """Add `--json`, passed to the command as `json_output`.

    Args:
        help: The flag's help text.

    Returns:
        The option decorator.
    """
    return click.option(
        "--json", "json_output", is_flag=True, callback=_set_json, help=help
    )


def select_all(
    *,
    help: str = "Select all items.",  # noqa: A002 - click's own keyword
) -> Callable[[FC], FC]:
    """Add `-a/--all`, passed to the command as `select_all`.

    Args:
        help: The flag's help text.

    Returns:
        The option decorator.
    """
    return click.option("-a", "--all", "select_all", is_flag=True, help=help)


def force(
    *,
    help: str = "Proceed without confirmation.",  # noqa: A002 - click's own keyword
) -> Callable[[FC], FC]:
    """Add `-f/--force`, passed to the command as `force`.

    Args:
        help: The flag's help text.

    Returns:
        The option decorator.
    """
    return click.option("-f", "--force", is_flag=True, help=help)


def plain(
    *,
    help: str = "Print plain, one record per line.",  # noqa: A002 - click's own keyword
) -> Callable[[FC], FC]:
    """Add `--plain`, read by the command as `ctx.format == "plain"`.

    Args:
        help: The flag's help text.

    Returns:
        The option decorator.
    """
    return click.option(
        "--plain",
        is_flag=True,
        expose_value=False,
        callback=_set_plain,
        help=help,
    )


def dry_run(
    *,
    help: str = "Show what would be done, without doing it.",  # noqa: A002 - click's own keyword
) -> Callable[[FC], FC]:
    """Add `-n/--dry-run`, passed to the command as `dry_run`.

    Args:
        help: The flag's help text.

    Returns:
        The option decorator.
    """
    return click.option("-n", "--dry-run", is_flag=True, help=help)


def _read_secret(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> str | None:
    """Return the text of a secret file, or of STDIN for `-`.

    NOTE: One trailing newline (`\\n` or `\\r\\n`) is removed, as `echo` &
    editors add one. STDIN is read only when it is not a terminal, so the
    command never blocks waiting for a secret to be typed, nor echoes it.

    Raises:
        click.BadParameter: When STDIN is a terminal, the file cannot be
            read, or the secret is empty.
    """
    if value is None:
        return None
    if value == "-":
        state = _run.state_of(ctx)
        in_tty = state.in_tty if state is not None else _run.is_tty(sys.stdin)
        if in_tty:
            raise click.BadParameter(
                "STDIN is a terminal - pipe the secret in",
                ctx=ctx,
                param=param,
            )
        text = sys.stdin.read()
    else:
        try:
            text = Path(value).read_text(encoding="utf-8")
        except (OSError, ValueError) as error:
            raise click.BadParameter(
                f"cannot read {value}: {error}", ctx=ctx, param=param
            ) from error
    text = text[:-2] if text.endswith("\r\n") else text.removesuffix("\n")
    if not text:
        raise click.BadParameter("the secret is empty", ctx=ctx, param=param)
    return text


def secret(
    name: str,
    *,
    help: str | None = None,  # noqa: A002 - click's own keyword
    required: bool = False,
) -> Callable[[FC], FC]:
    """Add `--<name>-file FILE`, passing the file's text as `<name>`.

    `-` reads STDIN, so a secret store is reached by a pipe or process
    substitution: `prog login --token-file <(pass show prog/token)`.

    Args:
        name: The secret's name, e.g. `api-key` for `--api-key-file` &
            the parameter `api_key`.
        help: The option's help text.
        required: Fail with a usage error when the option is not given;
            otherwise the command receives None.

    Returns:
        The option decorator.
    """
    return click.option(
        f"--{name}-file",
        name.replace("-", "_"),
        type=click.Path(exists=True, dir_okay=False, allow_dash=True),
        required=required,
        callback=_read_secret,
        metavar="FILE",
        help=help or f"Read the {name} from FILE, or from STDIN with `-`.",
    )
