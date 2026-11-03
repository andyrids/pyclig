"""Run a `pyclig.Command` or `Group` in-process & check it against CLIG.

```python
from pyclig.testing import assert_conforms, invoke


def test_list_plain_output_when_piped() -> None:
    \"\"\"Assert `list` prints tab-separated rows when STDOUT is a pipe.\"\"\"
    result = invoke(cli, ["list"], err_tty=True)
    assert result.exit_code == 0
    assert "\\t" in result.stdout


def test_cli_conforms() -> None:
    \"\"\"Assert the CLI follows the guidelines pyclig can check.\"\"\"
    assert_conforms(cli, ignore={"ARG-16": "`--token` also reads a file"})
```

`check` returns the `Finding`s instead of asserting; `assert_conforms`
lists them by rule ID (`docs/clig-coverage.md`), command & message. Neither
runs a command body.

License:
    SPDX-License-Identifier: Apache-2.0
"""

from collections.abc import Mapping, Sequence
from typing import IO, Any

from click.testing import CliRunner, Result
from rich.console import Console

from pyclig._conformance import Finding, assert_conforms, check
from pyclig._core import Command

__all__: list[str] = ["Finding", "assert_conforms", "check", "invoke"]

_CLEARED = (
    "COLUMNS",
    "FORCE_COLOR",
    "NO_COLOR",
    "TTY_COMPATIBLE",
    "TTY_INTERACTIVE",
)
"""Environment variables that change Rich's output, unset by default."""


def invoke(
    cli: Command,
    args: Sequence[str] = (),
    *,
    in_tty: bool = False,
    out_tty: bool = False,
    err_tty: bool = False,
    color: bool = False,
    interactive: bool = False,
    width: int = 80,
    env: Mapping[str, str | None] | None = None,
    input: str | bytes | IO[Any] | None = None,  # noqa: A002 - click's own keyword
) -> Result:
    """Run `cli` in-process, as if the standard streams were the given ones.

    NOTE: Live displays only animate with `interactive`, so output stays
    deterministic by default. The application logger is restored when the
    run ends.

    Args:
        cli: The CLI - a `pyclig.Group` or a standalone `pyclig.Command`.
        args: The command line arguments.
        in_tty: Treat STDIN as a terminal, so a prompt can be answered
            from `input`.
        out_tty: Treat STDOUT as a terminal.
        err_tty: Treat STDERR as a terminal, so a prompt can be seen -
            `pyclig.confirm` & `prompt=` options need `in_tty` & `err_tty`.
        color: Emit ANSI colour codes on both streams.
        interactive: Treat the terminal streams as interactive, so code
            gated on `console.is_interactive` (e.g. a spinner) runs - mock
            the live display itself.
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
                force_interactive=interactive and tty,
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
        pyclig_in_tty=in_tty,
        pyclig_err_tty=err_tty,
    )
