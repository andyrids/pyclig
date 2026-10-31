"""A click wrapper with Command Line Interface Guidelines (CLIG) paradigms.

License:
    SPDX-License-Identifier: Apache-2.0
"""

__all__: list[str] = []


def __getattr__(name: str) -> str:
    """Resolve `__version__` on first access, not at import.

    Args:
        name: The attribute name.

    Returns:
        The installed version, or `0.0.0+unknown` without metadata.

    Raises:
        AttributeError: For any other name.
    """
    if name == "__version__":
        from importlib import metadata

        try:
            return metadata.version("pyclig")
        except metadata.PackageNotFoundError:
            return "0.0.0+unknown"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
