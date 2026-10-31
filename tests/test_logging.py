"""Tests for `pyclig._logging` - handlers scoped to a run."""

import logging

import pytest

from pyclig import Group
from pyclig.testing import invoke


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
