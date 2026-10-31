"""Run a `pyclig.Group` in-process & capture each stream.

```python
from pyclig.testing import invoke


def test_list_plain_output_when_piped() -> None:
    \"\"\"Assert `list` prints tab-separated rows when STDOUT is a pipe.\"\"\"
    result = invoke(cli, ["list"], err_tty=True)
    assert result.exit_code == 0
    assert "\\t" in result.stdout
```

License:
    SPDX-License-Identifier: Apache-2.0
"""

from collections.abc import Mapping, Sequence
from typing import IO, Any

from click.testing import CliRunner, Result
from rich.console import Console

from pyclig._core import Group

_CLEARED = (
    "COLUMNS",
    "FORCE_COLOR",
    "NO_COLOR",
    "TTY_COMPATIBLE",
    "TTY_INTERACTIVE",
)
"""Environment variables that change Rich's output, unset by default."""


def invoke(
    cli: Group,
    args: Sequence[str] = (),
    *,
    out_tty: bool = False,
    err_tty: bool = False,
    color: bool = False,
    width: int = 80,
    env: Mapping[str, str | None] | None = None,
    input: str | bytes | IO[Any] | None = None,  # noqa: A002 - click's own keyword
) -> Result:
    """Run `cli` in-process, as if STDOUT & STDERR were the given streams.

    NOTE: Live displays never animate (`force_interactive=False`). The
    application logger is restored when the run ends.

    Args:
        cli: The CLI.
        args: The command line arguments.
        out_tty: Treat STDOUT as a terminal.
        err_tty: Treat STDERR as a terminal.
        color: Emit ANSI colour codes on both streams.
        width: The console width, in cells.
        env: Environment variables to set, or unset with None. Overrides
            the cleared defaults.
        input: STDIN's content, e.g. a prompt's answer.

    Returns:
        The click result - `exit_code`, `stdout`, `stderr` & `output`.
    """

    def consoles() -> tuple[Console, Console]:
        out, err = (
            Console(
                stderr=stderr,
                force_terminal=tty,
                force_interactive=False,
                width=width,
                color_system="standard" if color else None,
                legacy_windows=False,
                markup=False,
                emoji=False,
                highlight=False,
            )
            for stderr, tty in ((False, out_tty), (True, err_tty))
        )
        return out, err

    environ: dict[str, str | None] = dict.fromkeys(_CLEARED)
    environ.update(env or {})
    return CliRunner().invoke(
        cli,
        list(args),
        input=input,
        env=environ,
        catch_exceptions=False,
        pyclig_consoles=consoles,
    )
