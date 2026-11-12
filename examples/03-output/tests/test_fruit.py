"""Tests for the fruit example, written with `pyclig.testing`.

Run from the member directory:
    uv run pytest tests

License:
    SPDX-License-Identifier: Apache-2.0
"""

import json

from fruit import cli

from pyclig.testing import assert_conforms, invoke


def test_terminal_gets_a_table() -> None:
    """A terminal on STDOUT gets the table & its caption."""
    result = invoke(cli, out_tty=True)
    assert result.exit_code == 0
    assert "apple" in result.stdout
    assert "4 fruit" in result.stdout


def test_pipe_gets_plain_records() -> None:
    """A pipe gets tab-separated records, with the caption on STDERR."""
    result = invoke(cli)
    assert result.exit_code == 0
    assert result.stdout.splitlines()[:2] == [
        "apple\tred\t3\ttrue",
        "kiwi\tbrown\t\tfalse",
    ]
    assert "4 fruit" in result.stderr


def test_json_keeps_none() -> None:
    """`--json` prints the records unchanged, with `None` as `null`."""
    result = invoke(cli, ["--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)[1] == {
        "name": "kiwi",
        "colour": "brown",
        "qty": None,
        "ripe": False,
    }


def test_ripe_filters_the_records() -> None:
    """`--ripe` leaves only the ripe fruit."""
    result = invoke(cli, ["--ripe", "--plain"])
    assert result.exit_code == 0
    assert len(result.stdout.splitlines()) == 2


def test_conforms() -> None:
    """The command passes the CLIG conformance kit."""
    assert_conforms(cli, samples=[[], ["--json"], ["--ripe", "--plain"]])
