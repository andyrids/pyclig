"""Process exit codes shared by every `pyclig` application.

The codes let a script tell a usage mistake from a failed run, a crash or a
Ctrl-C. `USAGE` is click's own code for usage errors; `INTERNAL` is sysexits
`EX_SOFTWARE`.

License:
    SPDX-License-Identifier: Apache-2.0
"""

from enum import IntEnum


class ExitCode(IntEnum):
    """A process exit code.

    NOTE: Members pass `int` type checks (`IntEnum`), so a command can return
    one & `sys.exit` accepts it.

    Attributes:
        OK: Success.
        FAILURE: The command ran but failed, e.g. a download error.
        USAGE: The command line was invalid.
        INTERNAL: An unexpected exception, i.e. a bug.
        INTERRUPT: Interrupted by Ctrl-C (128 + `SIGINT`).
    """

    OK = 0
    FAILURE = 1
    USAGE = 2
    INTERNAL = 70
    INTERRUPT = 130
