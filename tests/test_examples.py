"""Smoke tests for the workspace members under `examples/`."""

import functools
import importlib.util
from pathlib import Path

import pytest

import pyclig
from pyclig.testing import assert_conforms, invoke

EXAMPLES = Path(__file__).parents[1] / "examples"

SAMPLES: dict[str, list[list[str]]] = {
    "01-hello/hello.py": [[], ["--name", "Ada", "--shout"]],
    "02-errors/pantry.py": [["list"], ["take", "apple"]],
    "03-output/fruit.py": [[], ["--json"], ["--plain"], ["--ripe"]],
    "04-feedback/checkup.py": [["run", "--delay", "0"], ["sync"]],
    "05-prompts/depot.py": [
        ["purge", "--all", "-n"],
        ["purge", "build", "-f"],
        ["drop", "docs", "--confirm", "docs"],
    ],
    "06-config/greeter.py": [
        ["hello"],
        ["--region", "eu", "hello"],
        ["where"],
    ],
}


@functools.cache
def _load(path: str) -> pyclig.Command:
    """Return the `cli` of an example, loaded by its file path.

    The examples are loaded by path, not imported, because CI installs the
    root project only - the workspace members are not on `sys.path`. The
    module keeps its own name, which names its config files & env prefix.

    Args:
        path: The module's path, relative to `examples/`.

    Returns:
        The module's `cli` command.
    """
    file = EXAMPLES / path
    spec = importlib.util.spec_from_file_location(file.stem, file)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cli: pyclig.Command = module.cli
    return cli


@pytest.mark.parametrize("path", SAMPLES)
def test_example_conforms(path: str) -> None:
    """Every example passes the CLIG conformance checks."""
    assert_conforms(_load(path), samples=SAMPLES[path])


def test_pantry_unknown_item_exits_3() -> None:
    """An unknown item is a domain error that names the next command."""
    result = invoke(_load("02-errors/pantry.py"), ["take", "kiwi"])
    assert result.exit_code == 3
    assert "error:" in result.stderr
    assert "pantry list" in result.stderr


def test_pantry_usage_error_exits_2() -> None:
    """A missing argument is a usage error & STDOUT stays empty."""
    result = invoke(_load("02-errors/pantry.py"), ["take"])
    assert result.exit_code == 2
    assert result.stdout == ""


def test_fruit_piped_is_tab_separated() -> None:
    """Piped output is plain, tab-separated rows."""
    result = invoke(_load("03-output/fruit.py"))
    assert result.exit_code == 0
    assert "\t" in result.stdout


def test_depot_refuses_without_tty() -> None:
    """A confirmation without a terminal exits 2 & names `--force`."""
    result = invoke(_load("05-prompts/depot.py"), ["purge", "--all"])
    assert result.exit_code == 2
    assert "--force" in result.stderr


def test_greeter_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `loud` profile of the project file overrides its defaults."""
    monkeypatch.chdir(EXAMPLES / "06-config")
    empty = str(tmp_path)
    result = invoke(
        _load("06-config/greeter.py"),
        ["--profile", "loud", "hello"],
        config_files=True,
        env={
            "APPDATA": empty,
            "XDG_CONFIG_HOME": empty,
            "PROGRAMDATA": empty,
            "XDG_CONFIG_DIRS": empty,
            "GREETER_NAME": None,
        },
    )
    assert result.stdout == "HELLO ADA, FROM EU\n"
