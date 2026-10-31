"""Tests for `pyclig._logging` - handlers scoped to a run."""

import logging
import re

import pytest

from pyclig import Group
from pyclig.testing import invoke
from tests.conftest import RunSample

# A plain `-d` record: time, level, [function] message, two spaces, call site
PLAIN_RECORD = re.compile(
    r"\[\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4}\] (?P<level>[A-Z]+) +"
    r"\[\w+\] .*\S  [\w.]+\.py:\d+"
)
BOX_DRAWING = re.compile(r"[─-╿]")


@pytest.fixture
def sample_logger() -> logging.Logger:
    """Return the sample CLI's package logger, as the tests import it."""
    return logging.getLogger("tests")


def test_logger_restored_after_runs(
    sample: Group, sample_logger: logging.Logger
) -> None:
    """Assert repeated runs leave the logger's handlers & settings as found."""
    before = (
        sample_logger.handlers[:],
        sample_logger.level,
        sample_logger.propagate,
    )
    for args in (["log"], ["-d", "log"], ["fail", "--kind", "crash"]):
        invoke(sample, args)
        assert (
            sample_logger.handlers[:],
            sample_logger.level,
            sample_logger.propagate,
        ) == before


def test_logged_exception_prints_traceback(sample: Group) -> None:
    """Assert `logger.exception` prints the notice, then the traceback."""
    result = invoke(sample, ["log", "--exception"])
    assert result.stderr.startswith("error: row skipped\nTraceback")
    assert result.stderr.rstrip().endswith("ValueError: bad row")


def test_debug_plain_when_stderr_not_a_terminal(sample: Group) -> None:
    """Assert `-d` prints each record as one plain line off a terminal."""
    result = invoke(sample, ["-d", "log"])
    lines = result.stderr.splitlines()
    levels = [
        match["level"] if (match := PLAIN_RECORD.fullmatch(line)) else line
        for line in lines
    ]
    assert levels == ["DEBUG", "INFO", "WARNING", "ERROR"]
    assert " DEBUG    [log] debug record  sample_cli.py:" in lines[0]


def test_debug_plain_record_never_wraps(sample: Group) -> None:
    """Assert a plain `-d` record wider than the console stays one line."""
    result = invoke(sample, ["-d", "log"], width=40)
    lines = result.stderr.splitlines()
    assert len(lines) == 4
    for line in lines:
        assert len(line) > 40
        assert PLAIN_RECORD.fullmatch(line)


def test_debug_plain_exception_traceback(sample: Group) -> None:
    """Assert `-d` prints a logged exception's record, then a plain trace."""
    result = invoke(sample, ["-d", "log", "--exception"])
    first, second, *_ = result.stderr.splitlines()
    match = PLAIN_RECORD.fullmatch(first)
    assert match
    assert match["level"] == "ERROR"
    assert " [log] row skipped  " in first
    assert second == "Traceback (most recent call last):"
    assert result.stderr.rstrip().endswith("ValueError: bad row")
    assert not BOX_DRAWING.search(result.stderr)


def test_debug_rich_on_a_terminal(sample: Group) -> None:
    """Assert `-d` lays records out with Rich when STDERR is a terminal."""
    result = invoke(sample, ["-d", "log"], err_tty=True)
    lines = result.stderr.splitlines()
    assert "debug record" in result.stderr
    assert not any(PLAIN_RECORD.fullmatch(line) for line in lines)


def test_debug_rich_when_colour_forced(run_sample: RunSample) -> None:
    """Assert `FORCE_COLOR` keeps the styled Rich `-d` layout on a pipe."""
    result = run_sample("-d", "log", env={"FORCE_COLOR": "1"})
    assert result.returncode == 0
    assert "debug record" in result.stderr
    assert "\x1b[" in result.stderr


def test_one_handler_during_a_run(sample: Group) -> None:
    """Assert a run sees one pyclig handler, whatever ran before it."""
    for _ in range(3):
        result = invoke(sample, ["log"])
        assert result.stderr.count("warning record") == 1


def test_foreign_handler_kept_open(
    sample: Group, sample_logger: logging.Logger
) -> None:
    """Assert a run neither removes nor closes a handler it did not add."""
    records: list[logging.LogRecord] = []

    class Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Keep()
    sample_logger.addHandler(handler)
    try:
        invoke(sample, ["log"])
        assert handler in sample_logger.handlers
        sample_logger.warning("after the run")
        assert records[-1].getMessage() == "after the run"
    finally:
        sample_logger.removeHandler(handler)
