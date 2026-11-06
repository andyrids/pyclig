"""Tests for `pyclig.paths` - per-user & system directories."""

import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import pyclig
from pyclig import paths

# (function, Windows variable, XDG variable, fallback under a home or root)
CASES = [
    (paths.config_dir, "APPDATA", "XDG_CONFIG_HOME", (".config",)),
    (paths.data_dir, "LOCALAPPDATA", "XDG_DATA_HOME", (".local", "share")),
    (paths.system_config_dir, "PROGRAMDATA", "XDG_CONFIG_DIRS", None),
]
IDS = ["config", "data", "system"]

Case = tuple[Callable[[str], Path], str, str, tuple[str, ...] | None]


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Patch `Path.home` to a temporary directory & clear every variable."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for _, windows, xdg, _ in CASES:
        monkeypatch.delenv(windows, raising=False)
        monkeypatch.delenv(xdg, raising=False)
    return tmp_path


def _fallback(case: Case, home: Path) -> Path:
    """Return the expected fallback of a case."""
    parts = case[3]
    return home.joinpath(*parts) if parts else Path("/etc/xdg")


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_windows_variable_wins_on_win32(
    case: Case, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert `win32` with its variable set uses that directory."""
    func, windows, xdg, _ = case
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv(windows, str(tmp_path / "win"))
    monkeypatch.setenv(xdg, str(tmp_path / "xdg"))
    assert func("app") == tmp_path / "win" / "app"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_windows_variable_ignored_elsewhere(
    case: Case, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert the Windows variable means nothing on another platform."""
    func, windows, xdg, _ = case
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv(windows, str(tmp_path / "win"))
    monkeypatch.setenv(xdg, str(tmp_path / "xdg"))
    assert func("app") == tmp_path / "xdg" / "app"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_win32_without_variable_uses_xdg(
    case: Case, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert `win32` without its variable falls through to XDG."""
    func, _, xdg, _ = case
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv(xdg, str(tmp_path / "xdg"))
    assert func("app") == tmp_path / "xdg" / "app"


@pytest.mark.parametrize("case", CASES, ids=IDS)
@pytest.mark.parametrize("value", ["relative/dir", ""])
def test_relative_or_empty_xdg_ignored(
    case: Case, home: Path, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert a relative or empty XDG value falls back, on any platform."""
    func, _, xdg, _ = case
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv(xdg, value)
    assert func("app") == _fallback(case, home) / "app"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_fallback_without_any_variable(
    case: Case, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert the fallback directory when nothing is set, on any platform."""
    func = case[0]
    for platform in ("linux", "darwin", "win32"):
        monkeypatch.setattr(sys, "platform", platform)
        assert func("app") == _fallback(case, home) / "app"


def test_system_config_dirs_takes_first_absolute(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert `XDG_CONFIG_DIRS` gives its first absolute entry."""
    monkeypatch.setattr(sys, "platform", "linux")
    dirs = ["relative", "", str(tmp_path / "one"), str(tmp_path / "two")]
    monkeypatch.setenv("XDG_CONFIG_DIRS", os.pathsep.join(dirs))
    assert paths.system_config_dir("app") == tmp_path / "one" / "app"


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_nothing_is_created(
    case: Case, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert the directory is returned, not made."""
    func, _, xdg, _ = case
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv(xdg, str(tmp_path / "xdg"))
    assert not func("app").exists()
    assert not (tmp_path / "xdg").exists()


def test_paths_is_a_pyclig_submodule() -> None:
    """Assert `pyclig.paths` is reachable like `pyclig.options`."""
    assert pyclig.paths is paths
    assert "paths" in pyclig.__all__
