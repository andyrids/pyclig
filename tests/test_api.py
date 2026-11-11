"""The public API lock - `tests/api.txt` is the frozen surface of pyclig."""

import enum
import inspect
import re
import types
import typing
from pathlib import Path

import pyclig
from pyclig import _conformance, options, paths, testing

SNAPSHOT = Path(__file__).with_name("api.txt")
MODULES = (pyclig, options, paths, testing)
CLASSES = (
    ("pyclig.Context", pyclig.Context),
    ("pyclig.Command", pyclig.Command),
    ("pyclig.Group", pyclig.Group),
    ("pyclig.GlobalOption", pyclig.GlobalOption),
    ("pyclig.Config", pyclig.Config),
    ("pyclig.testing.Finding", testing.Finding),
)
EMPTY = inspect.Parameter.empty
EXPORTED = {
    getattr(module, name): f"{module.__name__}.{name}"
    for module in (pyclig, testing)
    for name in module.__all__
    if isinstance(getattr(module, name), type)
}
"""The public path of each exported class: `_` modules are not API."""


def ann(hint: object) -> str:
    """Render an annotation the same way on every supported Python.

    Args:
        hint: The annotation, as `inspect.signature` returns it.

    Returns:
        The annotation as text.

    Raises:
        TypeError: If the annotation has no stable rendering yet.
    """
    if isinstance(hint, str):
        return repr(hint)
    if hint is None or hint is type(None):
        return "None"
    if isinstance(hint, typing.TypeVar | typing.ParamSpec):
        return f"~{hint.__name__}"
    if hint is ...:
        return "..."
    if isinstance(hint, list):
        return f"[{', '.join(ann(item) for item in hint)}]"
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is typing.Union or origin is types.UnionType:
        return " | ".join(ann(arg) for arg in args)
    if origin is typing.Literal:
        return f"Literal[{', '.join(repr(arg) for arg in args)}]"
    if origin is not None:
        return f"{ann(origin)}[{', '.join(ann(arg) for arg in args)}]"
    if isinstance(hint, type) or getattr(hint, "__module__", "") == "typing":
        module = hint.__module__.replace("pathlib._local", "pathlib")
        name = hint.__qualname__
        path = name if module == "builtins" else f"{module}.{name}"
        return EXPORTED.get(hint, path)
    raise TypeError(f"no stable rendering for the annotation {hint!r}")


def signature(function: object) -> str:
    """Render a callable's signature: names, kinds, annotations & defaults.

    Args:
        function: A function, as found in a module or a class `__dict__`.

    Returns:
        The signature as text, e.g. `(name: str, *, quiet: bool = False)`.
    """
    sig = inspect.signature(function)
    parts: list[str] = []
    kinds = [parameter.kind for parameter in sig.parameters.values()]
    for index, parameter in enumerate(sig.parameters.values()):
        kind = parameter.kind
        if kind is parameter.KEYWORD_ONLY and (
            parameter.VAR_POSITIONAL not in kinds
            and kinds.index(parameter.KEYWORD_ONLY) == index
        ):
            parts.append("*")
        part = {
            parameter.VAR_POSITIONAL: "*",
            parameter.VAR_KEYWORD: "**",
        }.get(kind, "") + parameter.name
        if parameter.annotation is not EMPTY:
            part += f": {ann(parameter.annotation)}"
        if parameter.default is not EMPTY:
            part += f" = {parameter.default!r}"
        parts.append(part)
        if kind is parameter.POSITIONAL_ONLY and (
            index + 1 == len(kinds) or kinds[index + 1] is not kind
        ):
            parts.append("/")
    text = f"({', '.join(parts)})"
    if sig.return_annotation is not EMPTY:
        text += f" -> {ann(sig.return_annotation)}"
    return text


def describe(value: object) -> str:
    """Render one public object as the value of its snapshot line.

    Args:
        value: A module attribute or a class `__dict__` entry.

    Returns:
        The text after the key.
    """
    if isinstance(value, types.ModuleType):
        return "module"
    if isinstance(value, property):
        setter = "" if value.fset is None else " settable"
        return f"property{setter} {signature(value.fget)}"
    if isinstance(value, classmethod | staticmethod):
        return f"{type(value).__name__} {signature(value.__func__)}"
    if typing.get_origin(value) is not None:
        return f"= {ann(value)}"
    if isinstance(value, type) and issubclass(value, enum.Enum):
        return "enum"
    if isinstance(value, type):
        init = value.__dict__.get("__init__")
        return "class" if init is None else f"class {signature(init)}"
    if callable(value):
        return signature(value)
    return f"= {value!r}"


def names(module: types.ModuleType) -> list[str]:
    """Return a module's public names: `__all__`, or what it defines.

    Args:
        module: One of the four public modules.

    Returns:
        The names a user may import from it.
    """
    if hasattr(module, "__all__"):
        return list(module.__all__)
    return [
        name
        for name, value in vars(module).items()
        if not name.startswith("_")
        and not isinstance(value, typing.TypeVar)
        and getattr(value, "__module__", None) == module.__name__
    ]


def current() -> dict[str, str]:
    """Render the public API of this install as snapshot entries.

    Returns:
        The value of each entry by its key.
    """
    entries: dict[str, str] = {}
    for module in MODULES:
        for name in names(module):
            key = f"{module.__name__}.{name}"
            entries[key] = describe(getattr(module, name))
    for member in pyclig.ExitCode:
        entries[f"pyclig.ExitCode.{member.name}"] = str(member.value)
    for path, cls in CLASSES:
        for name, value in vars(cls).items():
            if name.startswith("_"):
                continue
            # A class held as an attribute is named, not described again.
            named = f"= {ann(value)}" if isinstance(value, type) else None
            entries[f"{path}.{name}"] = named or describe(value)
    source = inspect.getsource(_conformance)
    for rule in re.findall(r'Finding\("([A-Z]+-\d+[a-z]?)"', source):
        entries[f"rule:{rule}"] = ""
    return entries


def line(key: str, value: str) -> str:
    """Return one snapshot line.

    Args:
        key: The entry's key.
        value: The entry's value, empty for a rule ID.

    Returns:
        The line, without a trailing space.
    """
    return f"{key} {value}".rstrip()


def test_public_api_is_frozen() -> None:
    """Assert the public API is exactly what `tests/api.txt` records."""
    text = SNAPSHOT.read_text(encoding="utf-8")
    lines = [row for row in text.splitlines() if row and row[0] != "#"]
    assert lines == sorted(set(lines)), "api.txt is not sorted & unique"
    frozen = dict((row.split(" ", 1) + [""])[:2] for row in lines)
    now = current()
    report: list[str] = []
    removed = sorted(frozen.keys() - now.keys())
    changed = sorted(
        k for k in frozen.keys() & now.keys() if frozen[k] != now[k]
    )
    added = sorted(now.keys() - frozen.keys())
    if removed:
        report.append("removed (breaking - needs 2.0); the lines to delete:")
        report += [f"  {line(key, frozen[key])}" for key in removed]
    if changed:
        report.append(
            "changed (breaking unless it only adds an optional parameter or "
            "reorders keyword-only ones); the current lines:"
        )
        report += [f"  {line(key, now[key])}" for key in changed]
    if added:
        report.append("added (add the line deliberately); the current lines:")
        report += [f"  {line(key, now[key])}" for key in added]
    assert not report, "tests/api.txt differs:\n" + "\n".join(report)
