"""Tests for the `pyclig` package - import side effects & version."""

import json
import subprocess
import sys

import pyclig

_PROBE = """
import json, logging, sys
import rich
before = set(sys.modules)
import pyclig
new = set(sys.modules) - before
heavy = ("rich.traceback", "rich.logging", "pygments", "importlib.metadata")
print(json.dumps({
    "heavy": sorted(m for m in new if m.startswith(heavy)),
    "root_handlers": len(logging.getLogger().handlers),
    "rich_console": rich._console is not None,
}))
"""


def test_import_has_no_side_effects() -> None:
    """Assert `import pyclig` leaves global state & heavy modules alone."""
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {
        "heavy": [],
        "root_handlers": 0,
        "rich_console": False,
    }


def test_version() -> None:
    """Assert the installed package exposes a version string."""
    assert isinstance(pyclig.__version__, str)
    assert pyclig.__version__ != "0.0.0+unknown"
