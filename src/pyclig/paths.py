"""Per-user & system directories: XDG everywhere but Windows.

| Function            | Windows               | XDG                         |
| ------------------- | --------------------- | --------------------------- |
| `config_dir`        | `%APPDATA%\\name`      | `$XDG_CONFIG_HOME/name`     |
| `data_dir`          | `%LOCALAPPDATA%\\name` | `$XDG_DATA_HOME/name`       |
| `system_config_dir` | `%PROGRAMDATA%\\name`  | first of `$XDG_CONFIG_DIRS` |

Each tries, in order: the Windows variable (on `win32` only, when set), an
absolute XDG variable, then the fallback - `~/.config/name`,
`~/.local/share/name` or `/etc/xdg/name`. macOS follows XDG, not
`~/Library`. A relative XDG value is ignored, `$XDG_CONFIG_DIRS` is split on
`os.pathsep`, and no directory is created. The environment, platform & home
are read on every call, so a test may patch any of them.

```python
config = pyclig.paths.config_dir("dkais") / "config.toml"
```

License:
    SPDX-License-Identifier: Apache-2.0
"""

import os
import sys
from collections.abc import Callable
from pathlib import Path

__all__: list[str] = ["config_dir", "data_dir", "system_config_dir"]


def config_dir(name: str) -> Path:
    """Return the user's configuration directory of an application.

    Args:
        name: The application name, e.g. `dkais`.

    Returns:
        `%APPDATA%\\name`, `$XDG_CONFIG_HOME/name` or `~/.config/name`.
    """
    return _resolve(
        name, "APPDATA", "XDG_CONFIG_HOME", lambda: Path.home() / ".config"
    )


def data_dir(name: str) -> Path:
    """Return the user's data directory of an application.

    Args:
        name: The application name, e.g. `dkais`.

    Returns:
        `%LOCALAPPDATA%\\name`, `$XDG_DATA_HOME/name` or
        `~/.local/share/name`.
    """
    return _resolve(
        name,
        "LOCALAPPDATA",
        "XDG_DATA_HOME",
        lambda: Path.home() / ".local" / "share",
    )


def system_config_dir(name: str) -> Path:
    """Return the system-wide configuration directory of an application.

    Args:
        name: The application name, e.g. `dkais`.

    Returns:
        `%PROGRAMDATA%\\name`, the first absolute `$XDG_CONFIG_DIRS` entry
        plus `name`, or `/etc/xdg/name`.
    """
    return _resolve(
        name, "PROGRAMDATA", "XDG_CONFIG_DIRS", lambda: Path("/etc/xdg")
    )


def _resolve(
    name: str, windows: str, xdg: str, fallback: Callable[[], Path]
) -> Path:
    """Return the first base directory that applies, plus `name`.

    Args:
        name: The application name.
        windows: The Windows variable, read on `win32` only.
        xdg: The XDG variable, honoured when absolute; a list is split on
            `os.pathsep` & its first absolute entry taken.
        fallback: Builds the base directory when neither applies.

    Returns:
        The directory, which may not exist.
    """
    base: Path | None = None
    if sys.platform == "win32" and os.environ.get(windows):
        base = Path(os.environ[windows])
    else:
        for entry in os.environ.get(xdg, "").split(os.pathsep):
            if entry and Path(entry).is_absolute():
                base = Path(entry)
                break
    return (base if base is not None else fallback()) / name
