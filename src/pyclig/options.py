"""Standard flags, with the names the CLI guidelines recommend.

Each factory returns a `click.option` decorator; pass `help=` to describe
the flag in the application's own terms.

| Factory         | Flag              | Parameter     |
| --------------- | ----------------- | ------------- |
| `json_output()` | `--json`          | `json_output` |
| `select_all()`  | `-a`, `--all`     | `select_all`  |
| `force()`       | `-f`, `--force`   | `force`       |
| `dry_run()`     | `-n`, `--dry-run` | `dry_run`     |

```python
@cli.command()
@pyclig.options.json_output()
@pyclig.options.select_all(help="Select every archive in the bucket.")
def list_(json_output: bool, select_all: bool) -> None: ...
```

License:
    SPDX-License-Identifier: Apache-2.0
"""

from collections.abc import Callable
from typing import Any, TypeVar

import click

FC = TypeVar("FC", bound=Callable[..., Any] | click.Command)


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
    return click.option("--json", "json_output", is_flag=True, help=help)


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
