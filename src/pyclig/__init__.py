"""A click wrapper with Command Line Interface Guidelines (CLIG) paradigms.

License:
    SPDX-License-Identifier: Apache-2.0
"""

from pyclig import options
from pyclig._core import (
    Command,
    Context,
    Group,
    command,
    confirm,
    group,
    pass_context,
    run,
)
from pyclig._exit import ExitCode
from pyclig._flags import GlobalOption
from pyclig._output import hanging, hint, info, notice

__all__: list[str] = [
    "Command",
    "Context",
    "ExitCode",
    "GlobalOption",
    "Group",
    "command",
    "confirm",
    "group",
    "hanging",
    "hint",
    "info",
    "notice",
    "options",
    "pass_context",
    "run",
]


def __getattr__(name: str) -> str:
    """Resolve `__version__` on first access, not at import.

    Args:
        name: The attribute name.

    Returns:
        The installed version, or `0.0.0+unknown` without metadata.

    Raises:
        AttributeError: For any other name.
    """
    if name == "__version__":
        from pyclig._run import version

        return version("pyclig")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
