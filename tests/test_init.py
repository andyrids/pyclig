"""Tests for the `pyclig` package - import side effects & version."""

import json
import subprocess
import sys
from typing import get_args

import pyclig
from tests.conftest import DEPENDENCIES

_PROBE = f"""
import json, logging, signal, sys, warnings
{DEPENDENCIES}  # the baseline: what these load is not pyclig's doing
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
print(json.dumps(dict(
    heavy=sorted(m for m in new if m.startswith(heavy)),
    root_handlers=len(logging.getLogger().handlers),
    rich_console=rich._console is not None,
    sigint_default=(
        signal.getsignal(signal.SIGINT) is signal.default_int_handler
    ),
    sigterm_default=signal.getsignal(signal.SIGTERM) is signal.SIG_DFL,
    showwarning_kept=warnings.showwarning is shown,
)))
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


_VENDORS = frozenset({"click", "rich"})
"""The dependencies whose import time is not pyclig's to spend."""

_IMPORT_BUDGET = 50_000
"""Microseconds `import pyclig` may add over click & rich: about twice what
the slowest supported interpreter needs on a developer machine."""


def _added_import_time() -> int:
    """Return the microseconds `import pyclig` adds over click & rich.

    NOTE: `-X importtime` lists a module after everything it imports, indented
    one level deeper, so read backwards each row's ancestors are known. The
    cumulative time of every outermost click or rich module is taken off
    pyclig's own.
    """
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", "import pyclig"],
        capture_output=True,
        text=True,
        check=True,
    )
    path: list[str] = []
    total = vendored = 0
    for line in reversed(result.stderr.splitlines()):
        cells = line.split("|")
        if len(cells) != 3 or not cells[1].strip().isdigit():
            continue
        name = cells[2].strip()
        del path[(len(cells[2]) - len(cells[2].lstrip())) // 2 :]
        nested = any(n.partition(".")[0] in _VENDORS for n in path)
        if name == "pyclig":
            total = int(cells[1])
        elif "pyclig" in path and not nested:
            if name.partition(".")[0] in _VENDORS:
                vendored += int(cells[1])
        path.append(name)
    assert total > vendored > 0, result.stderr
    return total - vendored


def test_import_adds_little_over_its_dependencies() -> None:
    """Assert pyclig's own share of `import pyclig` is small: best of 3.

    NOTE: The whole import is mostly click & rich, and its absolute time is
    the machine's; what pyclig adds on top is what it controls.
    """
    times = [_added_import_time() for _ in range(3)]
    assert min(times) < _IMPORT_BUDGET, times


def test_version() -> None:
    """Assert the installed package exposes a version string."""
    assert isinstance(pyclig.__version__, str)
    assert pyclig.__version__ != "0.0.0+unknown"


def test_signature_types_are_exported() -> None:
    """Assert the aliases the public signatures use can be imported."""
    assert get_args(pyclig.Format) == ("human", "plain", "json")
    assert get_args(pyclig.Level) == ("error", "warning")
    assert pyclig.Errors == tuple[type[Exception], ...]
    assert {"Errors", "Format", "Level"} <= set(pyclig.__all__)
