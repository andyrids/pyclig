"""Tests for `pyclig._logging` - handlers scoped to a run."""

import contextlib
import io
import logging
import re
import warnings
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

import pyclig
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


def test_debug_plain_when_colour_forced(run_sample: RunSample) -> None:
    """Assert `FORCE_COLOR` keeps the plain one-line `-d` records on a pipe."""
    result = run_sample("-d", "log", env={"FORCE_COLOR": "1"})
    assert result.returncode == 0
    lines = result.stderr.splitlines()
    assert len(lines) == 4
    assert all(PLAIN_RECORD.fullmatch(line) for line in lines)
    assert "\x1b[" not in result.stderr


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


def test_debug_variable_turns_on_debug_logging(run_sample: RunSample) -> None:
    """Assert `SAMPLE_DEBUG=1` logs at `DEBUG` without `-d`."""
    result = run_sample("log", env={"SAMPLE_DEBUG": "1"})
    assert result.returncode == 0
    lines = result.stderr.splitlines()
    assert len(lines) == 4
    assert all(PLAIN_RECORD.fullmatch(line) for line in lines)
    assert "debug record" in result.stderr


@pytest.mark.parametrize("value", ["", "0", "false", "No", "OFF", " off "])
def test_debug_variable_falsy_values_ignored(
    sample: Group, value: str
) -> None:
    """Assert an empty or false-like `<PROG>_DEBUG` leaves logging alone."""
    result = invoke(sample, ["log"], env={"TESTS_DEBUG": value})
    assert "debug record" not in result.stderr
    assert "warning record" in result.stderr


def test_debug_flag_after_variable_is_a_no_op(sample: Group) -> None:
    """Assert `-d` with `TESTS_DEBUG=1` keeps one handler & one record each."""
    result = invoke(sample, ["-d", "log"], env={"TESTS_DEBUG": "1"})
    assert result.stderr.count("debug record") == 1
    assert result.stderr.count("warning record") == 1


def _third_party() -> pyclig.Command:
    """Return a CLI whose command warns & logs as a third-party library."""

    @pyclig.command("probe")
    def probe() -> None:
        """Warn & log outside the package logger."""
        warnings.warn("old api", DeprecationWarning, stacklevel=1)
        library = logging.getLogger("thirdparty")
        library.setLevel(logging.INFO)
        library.info("library detail")
        library.warning("library notice")

    return probe


BareRoot = Callable[[], contextlib.AbstractContextManager[None]]


@pytest.fixture
def bare_root() -> Iterator[BareRoot]:
    """Return a context that empties the root logger's handlers, as no CLI
    configured them.

    NOTE: pytest adds its capture handlers to the root logger when the test
    is called, after fixtures are set up, so the root is emptied in the body.
    """

    @contextlib.contextmanager
    def emptied() -> Iterator[None]:
        saved = logging.root.handlers[:]
        logging.root.handlers[:] = []
        try:
            yield
        finally:
            logging.root.handlers[:] = saved

    yield emptied
    logging.getLogger("thirdparty").setLevel(logging.NOTSET)


@pytest.mark.filterwarnings("default")
def test_third_party_warning_prints_message_only(bare_root: BareRoot) -> None:
    """Assert `warnings.warn` prints `warning: msg`, with no path."""
    with bare_root():
        result = invoke(_third_party(), [])
    assert "warning: old api" in result.stderr.splitlines()
    assert "test_logging.py" not in result.stderr


@pytest.mark.filterwarnings("default")
def test_third_party_warning_location_under_debug(bare_root: BareRoot) -> None:
    """Assert `-d` shows where a warning was raised."""
    with bare_root():
        result = invoke(_third_party(), ["-d"])
    (line,) = [x for x in result.stderr.splitlines() if "old api" in x]
    assert PLAIN_RECORD.fullmatch(line)
    assert "test_logging.py:" in line


@pytest.mark.filterwarnings("default")
def test_third_party_logger_records(bare_root: BareRoot) -> None:
    """Assert a library WARNING is a notice & its INFO needs `-d`."""
    with bare_root():
        result = invoke(_third_party(), [])
        debug = invoke(_third_party(), ["-d"])
    assert "warning: library notice" in result.stderr.splitlines()
    assert "library detail" not in result.stderr
    assert debug.stderr.count("library detail") == 1
    assert debug.stderr.count("library notice") == 1


@pytest.mark.filterwarnings("default")
def test_third_party_notices_kept_under_quiet(bare_root: BareRoot) -> None:
    """Assert `-q` keeps library notices, as it keeps package ones."""
    with bare_root():
        result = invoke(_third_party(), ["-q"])
    lines = result.stderr.splitlines()
    assert "warning: library notice" in lines
    assert "warning: old api" in lines
    assert "library detail" not in result.stderr


@pytest.mark.filterwarnings("default")
def test_root_and_showwarning_restored_after_runs(bare_root: BareRoot) -> None:
    """Assert repeated runs leave the root logger & `showwarning` as found."""
    with bare_root():
        before = logging.root.handlers[:], logging.root.level
        shown = warnings.showwarning
        for args in ([], ["-d"]):
            invoke(_third_party(), args)
            assert (logging.root.handlers[:], logging.root.level) == before
            assert warnings.showwarning is shown


def test_configured_root_left_alone(bare_root: BareRoot) -> None:
    """Assert a root logger with a handler keeps it & `showwarning` is kept."""
    records: list[logging.LogRecord] = []

    class Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    seen: list[Callable[..., object]] = []

    @pyclig.command("probe")
    def probe() -> None:
        """Record the run's `showwarning` & log as a library."""
        seen.append(warnings.showwarning)
        logging.getLogger("thirdparty").warning("library notice")

    handler = Keep()
    with bare_root():
        logging.root.addHandler(handler)
        original = warnings.showwarning
        result = invoke(probe, [])
        assert logging.root.handlers == [handler]
    assert seen == [original]
    assert [r.getMessage() for r in records] == ["library notice"]
    assert "library notice" not in result.stderr


def test_warning_to_an_explicit_file_printed_there(
    bare_root: BareRoot,
) -> None:
    """Assert `showwarning` with a `file` still writes the warning there."""
    stream = io.StringIO()

    @pyclig.command("probe")
    def probe() -> None:
        """Show a warning to an explicit stream."""
        warnings.showwarning("old api", UserWarning, "lib.py", 3, stream)

    with bare_root():
        result = invoke(probe, [])
    assert stream.getvalue() == "lib.py:3: UserWarning: old api\n"
    assert "old api" not in result.stderr


def test_log_file_gets_debug_records(sample: Group, tmp_path: Path) -> None:
    """Assert `<PROG>_LOG_FILE` gets every record; the console is as before."""
    path = tmp_path / "debug.log"
    plain = invoke(sample, ["log"])
    result = invoke(sample, ["log"], env={"TESTS_LOG_FILE": str(path)})
    assert result.stderr == plain.stderr
    lines = path.read_text(encoding="utf-8").splitlines()
    levels = [
        m["level"] for line in lines if (m := PLAIN_RECORD.fullmatch(line))
    ]
    assert levels == ["DEBUG", "INFO", "WARNING", "ERROR"]


def test_log_file_appended(sample: Group, tmp_path: Path) -> None:
    """Assert a second run appends to the log file."""
    path = tmp_path / "debug.log"
    for _ in range(2):
        invoke(sample, ["log"], env={"TESTS_LOG_FILE": str(path)})
    assert path.read_text(encoding="utf-8").count("debug record") == 2


def test_log_file_with_debug(sample: Group, tmp_path: Path) -> None:
    """Assert `-d` prints records to the console & the file alike."""
    path = tmp_path / "debug.log"
    result = invoke(sample, ["-d", "log"], env={"TESTS_LOG_FILE": str(path)})
    assert result.stderr.count("debug record") == 1
    assert path.read_text(encoding="utf-8").count("debug record") == 1


@pytest.mark.filterwarnings("default")
def test_log_file_gets_root_records(
    bare_root: BareRoot, tmp_path: Path
) -> None:
    """Assert library records & warnings reach the file from a bare root."""
    path = tmp_path / "debug.log"
    with bare_root():
        result = invoke(_third_party(), [], env={"TESTS_LOG_FILE": str(path)})
        assert logging.root.handlers == []
    text = path.read_text(encoding="utf-8")
    assert "library notice" in text
    assert "old api" in text
    assert "library detail" not in result.stderr


def test_log_file_gets_crash_traceback(sample: Group, tmp_path: Path) -> None:
    """Assert exit 70 writes the traceback to the file & prints a hint."""
    path = tmp_path / "debug.log"
    result = invoke(
        sample, ["fail", "--kind", "crash"], env={"TESTS_LOG_FILE": str(path)}
    )
    assert result.exit_code == 70
    assert f"debug log: {path}" in result.stderr.splitlines()
    text = path.read_text(encoding="utf-8")
    assert "Traceback (most recent call last)" in text
    assert "unexpected" in text


def test_log_file_unwritable_warns(sample: Group, tmp_path: Path) -> None:
    """Assert a log file that cannot be opened warns & the run goes on."""
    result = invoke(sample, ["log"], env={"TESTS_LOG_FILE": str(tmp_path)})
    assert result.exit_code == 0
    first = result.stderr.splitlines()[0]
    assert first.startswith(
        f"warning: cannot write the debug log to {tmp_path}: "
    )
    assert "warning record" in result.stderr


def test_log_file_closed_after_run(sample: Group, tmp_path: Path) -> None:
    """Assert the file is closed when the run ends, so it can be removed."""
    path = tmp_path / "debug.log"
    invoke(sample, ["-d", "log"], env={"TESTS_LOG_FILE": str(path)})
    path.unlink()
    for logger in (logging.getLogger("tests"), logging.root):
        assert not [
            h for h in logger.handlers if hasattr(h, "_pyclig_handler")
        ]


def test_log_file_variable_cleared_by_invoke(
    sample: Group, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert `invoke` unsets an inherited `<PROG>_LOG_FILE`."""
    path = tmp_path / "debug.log"
    monkeypatch.setenv("TESTS_LOG_FILE", str(path))
    invoke(sample, ["log"])
    assert not path.exists()
