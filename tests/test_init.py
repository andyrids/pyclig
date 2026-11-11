"""Tests for the `pyclig` package - import side effects & version."""

import json
import subprocess
import sys

import pyclig

_PROBE = """
import json, logging, signal, sys, warnings
import pathlib  # the baseline: Python 3.11's pathlib loads urllib.parse
import rich
shown = warnings.showwarning
before = set(sys.modules)
import pyclig
new = set(sys.modules) - before
heavy = (
    "rich.traceback", "rich.logging", "pygments", "importlib.metadata",
    "rich.progress", "rich.table", "rich.box",
    "pyclig._conformance", "pyclig.testing", "click.testing", "tomllib",
    "socket", "urllib.parse", "platform",
)
print(json.dumps({
    "heavy": sorted(m for m in new if m.startswith(heavy)),
    "root_handlers": len(logging.getLogger().handlers),
    "rich_console": rich._console is not None,
    "sigint_default": (
        signal.getsignal(signal.SIGINT) is signal.default_int_handler
    ),
    "sigterm_default": signal.getsignal(signal.SIGTERM) is signal.SIG_DFL,
    "showwarning_kept": warnings.showwarning is shown,
}))
"""


def test_import_has_no_side_effects() -> None:
    """Assert `import pyclig` leaves global state, signal handlers,
    `showwarning` & heavy modules alone."""
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
        "sigint_default": True,
        "sigterm_default": True,
        "showwarning_kept": True,
    }


def test_import_takes_under_100_ms() -> None:
    """Assert `import pyclig` is quick enough to feel instant: best of 3."""
    times: list[int] = []
    for _ in range(3):
        result = subprocess.run(
            [sys.executable, "-X", "importtime", "-c", "import pyclig"],
            capture_output=True,
            text=True,
            check=True,
        )
        rows = (line.split("|") for line in result.stderr.splitlines())
        times += [int(r[1]) for r in rows if r[-1] == " pyclig"]
    assert len(times) == 3
    assert min(times) < 100_000, times


def test_version() -> None:
    """Assert the installed package exposes a version string."""
    assert isinstance(pyclig.__version__, str)
    assert pyclig.__version__ != "0.0.0+unknown"
