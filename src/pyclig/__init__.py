"""A click wrapper with Command Line Interface Guidelines (CLIG) paradigms.

License:
    SPDX-License-Identifier: Apache-2.0
"""

from pyclig import options
from pyclig._core import Command, Context, Group, group, pass_context
from pyclig._exit import ExitCode
from pyclig._output import hanging, info, notice
from pyclig._run import run

__all__: list[str] = [
    "Command",
    "Context",
    "ExitCode",
    "Group",
    "group",
    "hanging",
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
