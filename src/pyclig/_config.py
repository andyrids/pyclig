"""Configuration files, read into click's `default_map`.

`pyclig.group(..., config=Config(...))` adds `--config FILE` & (with
`profiles=True`) `--profile NAME`, then fills `ctx.default_map` before any
other option is read, so click's own order applies:

| # | Source, highest first                                        |
| - | ------------------------------------------------------------ |
| 1 | The command line                                             |
| 2 | The environment, via `envvar=`                               |
| 3 | `[profiles.NAME]` - project, then user, then system file     |
| 4 | The project file, nearest from the working directory upward  |
| 5 | The user file, `paths.config_dir(name)/config.toml`          |
| 6 | The system file, `paths.system_config_dir(name)/config.toml` |
| 7 | The application's `default_map`, then `default=`             |

Top-level keys configure the root command & a `[sub]` table its
subcommand, as `default_map` does; a shared setting is a value
`GlobalOption`. Tables merge recursively, scalars & lists are replaced.
`--config FILE` (or `<PROG>_CONFIG`) replaces the discovered files & is
read whole, and `prog sub --config FILE` applies it to `sub` & below.
`--help`, `-v` & completion read no file, and `tomllib` is imported only
when a file exists.

License:
    SPDX-License-Identifier: Apache-2.0
"""

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from pyclig import _run, paths
from pyclig._flags import GlobalOption

Table = dict[str, Any]
"""A TOML table."""

Sources = tuple[tuple[Path, str | None], ...]
"""The files to read, lowest first, each with the table to select or None."""

PROFILES = "profiles"
"""The top-level table holding `[profiles.NAME]`, never a command's."""

SOURCES_KEY = "pyclig.config_sources"
"""The `ctx.meta` key holding the run's `Sources`."""


@dataclass(frozen=True)
class Config:
    """Where a CLI's configuration files are, given as `config=`.

    Attributes:
        name: The application name: the config directories & the default
            project file. Defaults to the package (`State.package`).
        project: The project file's bare name, found from the working
            directory upward. Defaults to `.<name>.toml`.
        table: A dotted table of the project file to read, e.g.
            `tool.<name>` in a `pyproject.toml`. The file is read whole
            without it.
        profiles: Add `--profile NAME`, choosing a `[profiles.NAME]` table
            that outranks the files' main tables.
        dotenv: Read `./.env` into declared `envvar=` options.
    """

    name: str | None = None
    project: str | None = None
    table: str | None = None
    profiles: bool = False
    dotenv: bool = False


class ConfigError(click.ClickException):
    """A config file that cannot be read, or has the wrong shape: exit 1."""


def options(config: Config) -> list[click.Option]:
    """Return the options `config=` adds to a command, `--config` first.

    Args:
        config: The configuration layout.

    Returns:
        `--config`, then `--profile` with `profiles=True`.
    """
    added: list[click.Option] = [ConfigOption(config)]
    if config.profiles:
        added.append(ProfileOption())
    return added


def _ignore(ctx: click.Context, param: click.Parameter, value: Any) -> None:
    """Do nothing: `ConfigOption.handle_parse_result` does the work."""


class _PrefixedOption(GlobalOption):
    """A value option also read from `<PROG>_<SUFFIX>` in the environment."""

    suffix: str

    def resolve_envvar_value(self, ctx: click.Context) -> str | None:
        """Return `<PROG>_<SUFFIX>` when set & non-empty.

        Args:
            ctx: The command's context.

        Returns:
            The value, or None outside a run or when unset.
        """
        state = _run.state_of(ctx)
        if state is None:
            return super().resolve_envvar_value(ctx)
        return os.environ.get(f"{state.env_prefix}_{self.suffix}") or None

    def get_help_record(self, ctx: click.Context) -> tuple[str, str] | None:
        """Return the help record, naming the environment variable.

        Args:
            ctx: The command's context.

        Returns:
            The names & help, or None when hidden.
        """
        record = super().get_help_record(ctx)
        state = _run.state_of(ctx)
        if record is None or state is None:
            return record
        names, text = record
        return names, f"{text}  [env var: {state.env_prefix}_{self.suffix}]"


class ProfileOption(_PrefixedOption):
    """`--profile NAME`: choose the `[profiles.NAME]` tables."""

    suffix = "PROFILE"

    def __init__(self) -> None:
        """Create the option."""
        super().__init__(
            ["--profile", "pyclig_profile"],
            type=str,
            metavar="NAME",
            callback=_ignore,
            help="Use the [profiles.NAME] tables of the config files.",
        )


class ConfigOption(_PrefixedOption):
    """`--config FILE`: read FILE instead of the discovered files.

    NOTE: The files are read in `handle_parse_result`, which click runs
    for every parameter whether given or not, so discovery happens at the
    root even without `--config`. A subcommand only acts on a `--config`
    or `--profile` given at its level; the rest it inherits through
    `default_map`. Nothing is read under `resilient_parsing` (completion),
    nor when a help flag is still among the arguments, so `prog sub --help`
    works with a broken config file, as `prog --help` does.
    """

    suffix = "CONFIG"

    def __init__(self, config: Config) -> None:
        """Create the option.

        Args:
            config: The configuration layout.
        """
        super().__init__(
            ["--config", "pyclig_config"],
            type=click.Path(exists=True, dir_okay=False, path_type=Path),
            metavar="FILE",
            callback=_ignore,
            help="Read defaults from FILE instead of the config files.",
        )
        self.config = config

    def handle_parse_result(
        self, ctx: click.Context, opts: Mapping[str, Any], args: list[str]
    ) -> tuple[Any, list[str]]:
        """Fill `ctx.default_map` from the files, then check its shape.

        Args:
            ctx: The command's context.
            opts: The parsed options.
            args: The remaining arguments.

        Returns:
            The value & the remaining arguments, as click does.
        """
        value, args = super().handle_parse_result(ctx, opts, args)
        state = _run.state_of(ctx)
        help_ahead = not set(ctx.help_option_names).isdisjoint(args)
        if ctx.resilient_parsing or state is None or help_ahead:
            return value, args
        explicit = value if isinstance(value, Path) else None
        profile = _profile(ctx, opts)
        if ctx.parent is None or explicit is not None or profile is not None:
            _apply(ctx, state, self.config, explicit, profile)
        _check_shape(ctx)
        return value, args


def _profile(ctx: click.Context, opts: Mapping[str, Any]) -> str | None:
    """Return the profile given at this level, through the sibling option."""
    for param in ctx.command.get_params(ctx):
        if isinstance(param, ProfileOption):
            value, _ = param.consume_value(ctx, opts)
            return value if isinstance(value, str) and value else None
    return None


def _apply(
    ctx: click.Context,
    state: _run.State,
    config: Config,
    explicit: Path | None,
    profile: str | None,
) -> None:
    """Read the files & merge their tables for `ctx` into its `default_map`.

    Args:
        ctx: The context to configure.
        state: The run's state, recording the files read.
        config: The configuration layout.
        explicit: The `--config` file, replacing discovery.
        profile: The `--profile` name, or None.

    Raises:
        ConfigError: When a file cannot be read or has the wrong shape.
        click.BadParameter: When no file defines `profile`.
    """
    name = config.name or state.package
    sources: Sources
    if explicit is not None:
        sources = ((explicit, None),)
    elif ctx.parent is not None and SOURCES_KEY in ctx.meta:
        sources = ctx.meta[SOURCES_KEY]
    elif state.discover:
        sources = _discover(config, name)
    else:
        sources = ()
    ctx.meta[SOURCES_KEY] = sources
    logger = logging.getLogger(state.package)
    layers: list[tuple[Path, Table]] = []
    for path, table in sources:
        doc = _load(path)
        layers.append((path, _select(path, doc, table) if table else doc))
        logger.debug("loaded config %s", path)
    state.config_files = tuple(path for path, _ in layers)
    docs = [
        {k: v for k, v in doc.items() if k != PROFILES} for _, doc in layers
    ]
    if profile is not None:
        docs += _profile_sections(ctx, profile, layers)
    below = _below_root(ctx)
    merged: Table = dict(ctx.default_map or {})
    for doc in docs:
        merged = _merge(merged, _descend(doc, below))
    ctx.default_map = merged


def _discover(config: Config, name: str) -> Sources:
    """Return the system, user & nearest project file that exist."""
    found: list[tuple[Path, str | None]] = []
    for base in (paths.system_config_dir(name), paths.config_dir(name)):
        file = base / "config.toml"
        if file.is_file():
            found.append((file, None))
    project = config.project or f".{name}.toml"
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        file = directory / project
        if file.is_file():
            found.append((file, config.table))
            break
    return tuple(found)


def _load(path: Path) -> Table:
    """Parse a TOML file, importing `tomllib` only now."""
    import tomllib

    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except (OSError, ValueError) as error:  # TOMLDecodeError is a ValueError
        raise ConfigError(f"cannot read config {path}: {error}") from error


def _select(path: Path, doc: Table, table: str) -> Table:
    """Return the dotted `table` of `doc`, or an empty table when absent."""
    keys = table.split(".")
    node: Any = doc
    for depth, key in enumerate(keys, 1):
        node = node.get(key)
        if node is None:
            return {}
        if not isinstance(node, dict):
            raise ConfigError(
                f"cannot read config {path}: [{'.'.join(keys[:depth])}] "
                f"must be a table, not {type(node).__name__}"
            )
    return dict(node)


def _profile_sections(
    ctx: click.Context, profile: str, layers: list[tuple[Path, Table]]
) -> list[Table]:
    """Return every file's `[profiles.NAME]` table, lowest file first."""
    sections: list[Table] = []
    for path, doc in layers:
        profiles = doc.get(PROFILES, {})
        if not isinstance(profiles, dict):
            raise ConfigError(
                f"cannot read config {path}: [{PROFILES}] must be a table"
            )
        if profile in profiles:
            section = profiles[profile]
            if not isinstance(section, dict):
                raise ConfigError(
                    f"cannot read config {path}: [{PROFILES}.{profile}] must"
                    f" be a table, not {type(section).__name__}"
                )
            sections.append(section)
    if not sections:
        files = ", ".join(str(path) for path, _ in layers)
        where = f" in {files}" if files else ": no config file found"
        param = next(
            p
            for p in ctx.command.get_params(ctx)
            if isinstance(p, ProfileOption)
        )
        raise click.BadParameter(
            f"profile '{profile}' is not defined{where}", ctx=ctx, param=param
        )
    return sections


def _below_root(ctx: click.Context) -> list[str]:
    """Return the command names from the root's child down to `ctx`."""
    names: list[str] = []
    node: click.Context | None = ctx
    while node is not None and node.parent is not None:
        names.append(node.info_name or "")
        node = node.parent
    names.reverse()
    return names


def _descend(doc: Table, names: list[str]) -> Table:
    """Return the table of `doc` at `names`, or an empty one when absent."""
    node: Any = doc
    for depth, name in enumerate(names, 1):
        node = node.get(name)
        if node is None:
            return {}
        if not isinstance(node, dict):
            raise ConfigError(
                f"config: [{'.'.join(names[:depth])}] must be a table, not "
                f"{type(node).__name__}"
            )
    return dict(node)


def _check_shape(ctx: click.Context) -> None:
    """Fail when a subcommand's key of `ctx.default_map` is not a table."""
    command = ctx.command
    if not isinstance(command, click.Group) or not ctx.default_map:
        return
    below = _below_root(ctx)
    for name in command.commands:
        value = ctx.default_map.get(name)
        if value is not None and not isinstance(value, dict):
            raise ConfigError(
                f"config: [{'.'.join([*below, name])}] must be a table, not "
                f"{type(value).__name__}"
            )


def _merge(base: Mapping[str, Any], over: Mapping[str, Any]) -> Table:
    """Merge `over` into `base`: tables recurse, scalars & lists replace."""
    merged = dict(base)
    for key, value in over.items():
        current = merged.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merged[key] = _merge(current, value)
        else:
            merged[key] = value
    return merged
