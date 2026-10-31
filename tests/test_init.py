"""Smoke tests for the `pyclig` package."""

import pyclig


def test_version() -> None:
    """Assert the installed package exposes a version string."""
    assert isinstance(pyclig.__version__, str)
