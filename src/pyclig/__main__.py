"""Main entry point for pyclig."""

import logging

logger = logging.getLogger(__package__)


def main() -> int:
    """Provide a unified `pyclig` CLI entrypoint.

    Returns:
        The process exit code.
    """
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
