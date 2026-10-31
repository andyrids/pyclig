"""__init__ for pyclig."""

import contextlib
from importlib import metadata

__all__: list[str] = []

with contextlib.suppress(metadata.PackageNotFoundError):
    __version__: str = metadata.version("pyclig")
