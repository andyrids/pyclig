"""__init__ for pyclig logging module."""

import logging

from ._logging import (
    CLI_CONSOLE,
    GLOBAL_CONSOLE,
    configure_cli_logging,
)

__all__: list[str] = [
    "CLI_CONSOLE",
    "GLOBAL_CONSOLE",
    "configure_cli_logging",
]

logging.getLogger("pyclig").addHandler(logging.NullHandler())
