"""Tests for `pyclig._config` - config files under click's `default_map`."""

import os
import subprocess
import sys
from pathlib import Path

import click
import pytest
from click.testing import CliRunner, Result

import pyclig
from pyclig import _run
from pyclig.testing import invoke
from tests.conftest import sample_env

DEMO = pyclig.Config(name="demo", project=".demo.toml", profiles=True)


def _set_region(
    ctx: click.Context, param: click.Parameter, value: str
) -> None:
    """Share `--region` with the commands below."""
    ctx.meta["app.region"] = value


@pyclig.group("demo", config=DEMO)
@click.option(
    "--region",
    cls=pyclig.GlobalOption,
    type=str,
    callback=_set_region,
    help="The region.",
)
def demo() -> None:
    """Demonstrate config files."""


@demo.command()
@click.option("--level", type=int, default=0, envvar="DEMO_LEVEL")
@click.option("--tag", "tags", multiple=True)
@pyclig.pass_context
def show(ctx: pyclig.Context, level: int, tags: tuple[str, ...]) -> None:
    """Print the resolved values & the files read."""
    state = _run.state_of(ctx)
    files = ";".join(str(p) for p in state.config_files) if state else ""
    click.echo(
        f"level={level} tags={list(tags)} region={ctx.meta.get('app.region')}"
        f" quiet={ctx.quiet}"
    )
    click.echo(f"files={files}")


@demo.group()
def nested() -> None:
    """Nest a group."""


@nested.command()
@click.option("--depth", type=int, default=0)
def leaf(depth: int) -> None:
    """Print `--depth`."""
    click.echo(f"depth={depth}")


class Dirs:
    """The system, user & project config files of a test, plus their env."""

    def __init__(self, root: Path) -> None:
        """Create the directories under `root`."""
        self.system = root / "system" / "demo" / "config.toml"
        self.user = root / "user" / "demo" / "config.toml"
        self.project = root / "project" / ".demo.toml"
        for file in (self.system, self.user, self.project):
            file.parent.mkdir(parents=True)
        self.env = {
            "PROGRAMDATA": str(root / "system"),
            "XDG_CONFIG_DIRS": str(root / "system"),
            "APPDATA": str(root / "user"),
            "XDG_CONFIG_HOME": str(root / "user"),
        }


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Dirs:
    """Return the config files of a run started in the project directory."""
    dirs = Dirs(tmp_path)
    monkeypatch.chdir(dirs.project.parent)
    return dirs


def run(dirs: Dirs, args: list[str], **env: str) -> Result:
    """Run `demo` with discovery on & the directories in the environment."""
    return invoke(demo, args, env=dirs.env | env, config_files=True)


LAYERS = [
    "default",
    "default_map",
    "system",
    "user",
    "project",
    "profile",
    "env",
    "flag",
]


@pytest.mark.parametrize("top", range(len(LAYERS)), ids=LAYERS)
def test_precedence_matrix(dirs: Dirs, top: int) -> None:
    """Assert each layer outranks every layer below it."""
    layers = LAYERS[: top + 1]
    if "system" in layers:
        dirs.system.write_text("[show]\nlevel = 2\n")
    if "user" in layers:
        dirs.user.write_text("[show]\nlevel = 3\n")
    project = "[show]\nlevel = 4\n" if "project" in layers else ""
    if "profile" in layers:
        project += "[profiles.p.show]\nlevel = 5\n"
    if project:
        dirs.project.write_text(project)
    args = ["--profile", "p", "show"] if "profile" in layers else ["show"]
    if "flag" in layers:
        args += ["--level", "7"]
    env = dirs.env | ({"DEMO_LEVEL": "6"} if "env" in layers else {})
    default_map = {"show": {"level": 1}} if "default_map" in layers else None
    result = CliRunner().invoke(
        demo,
        args,
        env=env,
        default_map=default_map,
        pyclig_discover=True,
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith(f"level={top} ")


def test_no_files_is_a_no_op(dirs: Dirs) -> None:
    """Assert a run without any config file reads nothing."""
    result = run(dirs, ["show"])
    assert result.stdout == "level=0 tags=[] region=None quiet=False\nfiles=\n"


def test_files_are_recorded_low_to_high(dirs: Dirs) -> None:
    """Assert the loaded files are recorded: system, user, then project."""
    for file in (dirs.system, dirs.user, dirs.project):
        file.write_text("")
    result = run(dirs, ["show"])
    assert result.stdout.endswith(
        f"files={dirs.system};{dirs.user};{dirs.project}\n"
    )


def test_debug_logs_the_files(dirs: Dirs) -> None:
    """Assert `-d` logs each file as it is loaded."""
    dirs.user.write_text("")
    result = run(dirs, ["-d", "show"])
    assert f"loaded config {dirs.user}" in result.stderr


def test_tables_merge_and_lists_replace(dirs: Dirs) -> None:
    """Assert nested tables merge across files while lists are replaced."""
    dirs.user.write_text('[show]\ntags = ["a", "b"]\nlevel = 1\n')
    dirs.project.write_text('[show]\ntags = ["c"]\n')
    result = run(dirs, ["show"])
    assert result.stdout.startswith("level=1 tags=['c'] ")


def test_top_level_keys_configure_the_root_only(dirs: Dirs) -> None:
    """Assert `region` & `quiet` reach the root & `level` does not cascade."""
    dirs.project.write_text('region = "eu"\nquiet = true\nlevel = 9\n')
    result = run(dirs, ["show"])
    assert result.stdout.startswith("level=0 tags=[] region=eu quiet=True")


def test_nested_group_tables(dirs: Dirs) -> None:
    """Assert `[nested.leaf]` configures the leaf of a nested group."""
    dirs.project.write_text("[nested.leaf]\ndepth = 3\n")
    assert run(dirs, ["nested", "leaf"]).stdout == "depth=3\n"


def test_unknown_keys_are_ignored(dirs: Dirs) -> None:
    """Assert keys naming no option or command change nothing."""
    dirs.project.write_text("bogus = 1\n[show]\nnope = 2\n[other]\nx = 1\n")
    assert run(dirs, ["show"]).exit_code == 0


def test_project_file_found_upward(
    dirs: Dirs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert the nearest project file above the working directory wins."""
    dirs.project.write_text("[show]\nlevel = 4\n")
    deep = dirs.project.parent / "a" / "b"
    deep.mkdir(parents=True)
    (dirs.project.parent / "a" / ".demo.toml").write_text(
        "[show]\nlevel = 8\n"
    )
    monkeypatch.chdir(deep)
    assert run(dirs, ["show"]).stdout.startswith("level=8 ")


def test_config_option_replaces_discovered_files(
    dirs: Dirs, tmp_path: Path
) -> None:
    """Assert `--config FILE` is the only file read, flags & env still win."""
    dirs.system.write_text("[show]\nlevel = 2\n")
    dirs.project.write_text(
        "[show]\nlevel = 4\n[profiles.p.show]\nlevel = 5\n"
    )
    other = tmp_path / "other.toml"
    other.write_text("[show]\nlevel = 1\n[profiles.p.show]\nlevel = 9\n")
    result = run(dirs, ["--config", str(other), "show"])
    assert (
        result.stdout
        == f"level=1 tags=[] region=None quiet=False\nfiles={other}\n"
    )
    result = run(dirs, ["--config", str(other), "--profile", "p", "show"])
    assert result.stdout.startswith("level=9 ")
    result = run(dirs, ["--profile", "p", "--config", str(other), "show"])
    assert result.stdout.startswith("level=9 ")
    result = run(dirs, ["--config", str(other), "show"], DEMO_LEVEL="6")
    assert result.stdout.startswith("level=6 ")


def test_config_and_profile_from_env(dirs: Dirs, tmp_path: Path) -> None:
    """Assert `TESTS_CONFIG` & `TESTS_PROFILE` name the file & profile."""
    other = tmp_path / "other.toml"
    other.write_text("[show]\nlevel = 1\n[profiles.p.show]\nlevel = 9\n")
    result = run(dirs, ["show"], TESTS_CONFIG=str(other))
    assert result.stdout.startswith("level=1 ")
    result = run(dirs, ["show"], TESTS_CONFIG=str(other), TESTS_PROFILE="p")
    assert result.stdout.startswith("level=9 ")


def test_config_option_at_a_subcommand(dirs: Dirs, tmp_path: Path) -> None:
    """Assert `demo show --config f` applies `f` to `show`."""
    other = tmp_path / "other.toml"
    other.write_text("[show]\nlevel = 1\n[profiles.p.show]\nlevel = 9\n")
    result = run(dirs, ["show", "--config", str(other)])
    assert result.stdout.startswith("level=1 ")
    result = run(dirs, ["show", "--config", str(other), "--profile", "p"])
    assert result.stdout.startswith("level=9 ")


def test_profile_at_a_subcommand_reuses_the_files(dirs: Dirs) -> None:
    """Assert `demo show --profile p` applies the discovered files' profile."""
    dirs.project.write_text(
        "[show]\nlevel = 4\n[profiles.p.show]\nlevel = 5\n"
    )
    assert run(dirs, ["show", "--profile", "p"]).stdout.startswith("level=5 ")


def test_profile_sections_rank_project_then_user_then_system(
    dirs: Dirs,
) -> None:
    """Assert a profile section outranks every main section."""
    dirs.system.write_text("[profiles.p.show]\nlevel = 5\n")
    dirs.project.write_text("[show]\nlevel = 4\n")
    assert run(dirs, ["--profile", "p", "show"]).stdout.startswith("level=5 ")
    dirs.user.write_text("[profiles.p.show]\nlevel = 6\n")
    assert run(dirs, ["--profile", "p", "show"]).stdout.startswith("level=6 ")


def test_missing_config_file_is_a_usage_error(
    dirs: Dirs, tmp_path: Path
) -> None:
    """Assert a missing or directory `--config` exits 2."""
    result = run(dirs, ["--config", str(tmp_path / "nope.toml"), "show"])
    assert result.exit_code == 2
    assert "does not exist" in result.stderr
    result = run(dirs, ["--config", str(tmp_path), "show"])
    assert result.exit_code == 2
    assert "is a directory" in result.stderr


def test_bad_toml_exits_1_naming_the_file(dirs: Dirs) -> None:
    """Assert a file that cannot be parsed or decoded is reported, exit 1."""
    dirs.project.write_text("[show\nlevel = 1\n")
    result = run(dirs, ["show"])
    assert result.exit_code == 1
    assert result.stderr.startswith(
        f"error: cannot read config {dirs.project}: "
    )
    dirs.project.write_bytes(b"\xff\xfe")
    result = run(dirs, ["show"])
    assert result.exit_code == 1
    assert result.stderr.startswith(
        f"error: cannot read config {dirs.project}: "
    )


def test_unknown_profile_is_a_usage_error_naming_the_files(dirs: Dirs) -> None:
    """Assert `--profile x` with no `[profiles.x]` anywhere exits 2."""
    result = run(dirs, ["--profile", "x", "show"])
    assert result.exit_code == 2
    assert "profile 'x' is not defined: no config file found" in result.stderr
    dirs.user.write_text("[profiles.p]\n")
    dirs.project.write_text("")
    result = run(dirs, ["--profile", "x", "show"])
    assert result.exit_code == 2
    assert f"profile 'x' is not defined in {dirs.user}, {dirs.project}" in (
        result.stderr
    )


def test_command_key_must_be_a_table(dirs: Dirs) -> None:
    """Assert `show = 1` is a config error, exit 1, at any level."""
    dirs.project.write_text("show = 1\n")
    result = run(dirs, ["show"])
    assert result.exit_code == 1
    assert result.stderr == "error: config: [show] must be a table, not int\n"
    dirs.project.write_text("[nested]\nleaf = 'x'\n")
    result = run(dirs, ["nested", "leaf"])
    assert result.exit_code == 1
    assert "[nested.leaf] must be a table" in result.stderr
    dirs.project.write_text("[profiles]\np = 1\n")
    assert run(dirs, ["--profile", "p", "show"]).exit_code == 1


def test_table_selects_a_section_of_the_project_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert `table=` reads one section & a file without it is empty."""

    @pyclig.command(
        "tool",
        config=pyclig.Config(
            name="tool", project="pyproject.toml", table="tool.demo"
        ),
    )
    @click.option("--level", type=int, default=0)
    def tool(level: int) -> None:
        """Print `--level`."""
        click.echo(f"level={level}")

    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.demo]\nlevel = 4\n")
    assert invoke(tool, config_files=True).stdout == "level=4\n"
    (tmp_path / "pyproject.toml").write_text("[tool.other]\nlevel = 4\n")
    assert invoke(tool, config_files=True).stdout == "level=0\n"
    (tmp_path / "pyproject.toml").write_text("[tool]\ndemo = 1\n")
    result = invoke(tool, config_files=True)
    assert result.exit_code == 1
    assert "[tool.demo] must be a table" in result.stderr


def test_invoke_reads_no_files_by_default(dirs: Dirs, tmp_path: Path) -> None:
    """Assert `invoke` skips discovery unless `config_files=True`."""
    dirs.project.write_text("[show]\nlevel = 4\n")
    result = invoke(demo, ["show"], env=dirs.env)
    assert result.stdout == "level=0 tags=[] region=None quiet=False\nfiles=\n"
    other = tmp_path / "other.toml"
    other.write_text("[show]\nlevel = 1\n")
    assert invoke(demo, ["--config", str(other), "show"]).stdout.startswith(
        "level=1 "
    )


def test_config_only_on_the_root() -> None:
    """Assert `add_command` rejects a subcommand with `config=`."""

    @pyclig.command("sub", config=pyclig.Config())
    def sub() -> None:
        """Do nothing."""

    with pytest.raises(TypeError, match="sub sets config="):
        demo.add_command(sub)


def test_help_lists_config_options(dirs: Dirs) -> None:
    """Assert the root shows both options in full with their env vars."""
    text = run(dirs, ["--help"]).stdout
    assert "--config FILE" in text
    assert "TESTS_CONFIG]" in text
    assert "--profile NAME" in text
    assert "TESTS_PROFILE]" in text
    assert "--config, --profile, --region, -d/--debug" in (
        run(dirs, ["show", "--help"]).stdout
    )


SCRIPT = '''
import click
import pyclig


@pyclig.group(
    "demo",
    config=pyclig.Config(name="demo", project=".demo.toml", profiles=True),
)
def cli() -> None:
    """Demonstrate config files."""


@cli.command()
@click.option("--level", type=int, default=0, help="The level.")
def show(level: int) -> None:
    """Print the level."""
    click.echo(f"level={level}")


if __name__ == "__main__":
    cli()
'''


@pytest.mark.parametrize(
    ("args", "env"),
    [
        (["--help"], {}),
        (["-v"], {}),
        (["show", "--help"], {}),
        (
            [],
            {
                "_DEMO_COMPLETE": "bash_complete",
                "COMP_WORDS": "demo sh",
                "COMP_CWORD": "1",
            },
        ),
    ],
    ids=["help", "version", "sub-help", "completion"],
)
def test_help_version_and_completion_read_no_file(
    tmp_path: Path, args: list[str], env: dict[str, str]
) -> None:
    """Assert a malformed project file never stops help, `-v` & completion."""
    script = tmp_path / "demo_cli.py"
    script.write_text(SCRIPT)
    (tmp_path / ".demo.toml").write_text("[show\n")

    def run_script(
        *extra: str, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-X", "importtime", str(script), *extra],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=sample_env(env),
            check=False,
        )

    result = run_script(*args, env=env)
    assert result.returncode == 0, result.stderr[-500:]
    assert "tomllib" not in result.stderr
    result = run_script("show", env={})
    assert result.returncode == 1
    assert "error: cannot read config" in result.stderr


def test_config_option_named_like_the_project_file_selects_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert `--config pyproject.toml` reads `table=`, another file whole."""

    @pyclig.command(
        "tool",
        config=pyclig.Config(
            name="tool", project="pyproject.toml", table="tool.demo"
        ),
    )
    @click.option("--level", type=int, default=0)
    def tool(level: int) -> None:
        """Print `--level`."""
        click.echo(f"level={level}")

    monkeypatch.chdir(tmp_path)
    named = tmp_path / "elsewhere" / "pyproject.toml"
    named.parent.mkdir()
    named.write_text("level = 9\n[tool.demo]\nlevel = 4\n")
    assert invoke(tool, ["--config", str(named)]).stdout == "level=4\n"
    named.write_text("level = 9\n[tool.other]\nlevel = 4\n")
    assert invoke(tool, ["--config", str(named)]).stdout == "level=0\n"
    whole = tmp_path / "other.toml"
    whole.write_text("level = 9\n[tool.demo]\nlevel = 4\n")
    assert invoke(tool, ["--config", str(whole)]).stdout == "level=9\n"


@pyclig.group("dot", config=pyclig.Config(name="dot", dotenv=True))
def dot() -> None:
    """Demonstrate `.env`."""


@dot.command()
@click.option("--level", type=int, default=0, envvar="DOT_LEVEL")
@click.option("--token", envvar="DOT_TOKEN")
@click.option("--name", "names", multiple=True, envvar="DOT_NAMES")
@click.option("--alt", envvar=["DOT_ALT_A", "DOT_ALT_B"])
def dump(
    level: int, token: str | None, names: tuple[str, ...], alt: str | None
) -> None:
    """Print the resolved values & the real environment."""
    click.echo(
        f"level={level} token={token} names={list(names)} alt={alt} "
        f"env={os.environ.get('DOT_LEVEL')}"
    )


def test_dotenv_fills_declared_envvars_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert `.env` feeds `envvar=` options, skips secrets & stays private."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "# a comment\n"
        "export DOT_LEVEL=3\n"
        '\nDOT_NAMES="a b"  # quoted keeps the space, the comment goes\n'
        "DOT_ALT_B='single'\n"
        "DOT_TOKEN=hunter2\n"
    )
    result = invoke(dot, ["dump"], config_files=True)
    assert result.stdout == (
        "level=3 token=None names=['a', 'b'] alt=single env=None\n"
    )
    assert result.stderr == ""


def test_dotenv_below_the_environment_above_the_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert env > `.env` > project file."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".dot.toml").write_text("[dump]\nlevel = 4\n")
    assert invoke(dot, ["dump"], config_files=True).stdout.startswith(
        "level=4 "
    )
    (tmp_path / ".env").write_text("DOT_LEVEL=3\n")
    assert invoke(dot, ["dump"], config_files=True).stdout.startswith(
        "level=3 "
    )
    result = invoke(dot, ["dump"], env={"DOT_LEVEL": "5"}, config_files=True)
    assert result.stdout.startswith("level=5 ")


def test_dotenv_parse_rules_and_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert comments, quotes & a BOM parse, and a bad line only warns."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_bytes(
        b"\xef\xbb\xbfDOT_LEVEL=3 # trailing comment\n"
        b"this is not a pair\n"
        b"\n"
        b"DOT_ALT_A=a # b\n"
        b"9BAD=x\n"
    )
    result = invoke(dot, ["dump"], config_files=True)
    assert result.stdout.startswith("level=3 token=None names=[] alt=a ")
    assert result.stderr == (
        "warning: .env:2: not KEY=VALUE, ignored\n"
        "warning: .env:5: not KEY=VALUE, ignored\n"
    )


def test_dotenv_is_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Assert `.env` is read only with `dotenv=True` & discovery on."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DEMO_LEVEL=3\nDOT_LEVEL=3\n")
    assert invoke(demo, ["show"], config_files=True).stdout.startswith(
        "level=0 "
    )
    assert invoke(dot, ["dump"]).stdout.startswith("level=0 ")
    (tmp_path / ".env").unlink()
    assert invoke(dot, ["dump"], config_files=True).stdout.startswith(
        "level=0 "
    )


def test_secret_pattern_is_shared_with_the_kit() -> None:
    """Assert `.env` & ENV-15 use one `_SECRET` definition."""
    from pyclig import _config, _conformance

    assert _conformance._SECRET is _config._SECRET
    assert _config._SECRET.search("DOT_TOKEN")
    assert not _config._SECRET.search("DOT_TOKEN_FILE")
