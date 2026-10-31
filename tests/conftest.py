"""Shared fixtures across the `tests/` directory."""

import io
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from pyclig import Group
from tests.sample_cli import cli

SAMPLE = Path(__file__).with_name("sample_cli.py")

RunSample = Callable[..., subprocess.CompletedProcess[str]]

# Variables that change Rich's output, unset for every subprocess
_CLEARED = (
    "COLUMNS",
    "FORCE_COLOR",
    "NO_COLOR",
    "PYTHONIOENCODING",
    "SAMPLE_DATA_DIR",
    "TTY_COMPATIBLE",
    "TTY_INTERACTIVE",
)


class InterruptingInput(io.BytesIO):
    """STDIN that raises `KeyboardInterrupt` on the first read, like Ctrl-C."""

    def read(self, size: int | None = -1) -> bytes:
        """Raise `KeyboardInterrupt`, unless nothing is asked for.

        Args:
            size: The number of bytes to read.

        Returns:
            No bytes, for a zero-length read.
        """
        if size == 0:
            return b""
        raise KeyboardInterrupt

    def read1(self, size: int | None = -1) -> bytes:
        """Read as `read` does.

        Args:
            size: The number of bytes to read.

        Returns:
            No bytes, for a zero-length read.
        """
        return self.read(size)


@pytest.fixture
def sample() -> Group:
    """Return the sample CLI."""
    return cli


def sample_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a clean environment for a sample CLI subprocess.

    Args:
        env: Variables to set.

    Returns:
        The environment.
    """
    base = {k: v for k, v in os.environ.items() if k not in _CLEARED}
    root = str(Path(__file__).parents[1])
    base["PYTHONPATH"] = os.pathsep.join(
        filter(None, (root, base.get("PYTHONPATH")))
    )
    return base | dict(env or {})


@pytest.fixture
def run_sample() -> RunSample:
    """Return a function running the sample CLI in a subprocess."""

    def run(
        *args: str, env: Mapping[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SAMPLE), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=sample_env(env),
            check=False,
        )

    return run
