"""List the fruit in a bowl: human, plain & JSON output from one call.

Run from this directory:
    uv run fruit
    uv run fruit | cat
    uv run fruit --json
    uv run fruit --plain 2>/dev/null
    uv run fruit --ripe
    uv run pytest tests

License:
    SPDX-License-Identifier: Apache-2.0
"""

import click
from rich import box
from rich.table import Table

import pyclig

FRUIT: list[dict[str, object]] = [
    {"name": "apple", "colour": "red", "qty": 3, "ripe": True},
    {"name": "kiwi", "colour": "brown", "qty": None, "ripe": False},
    {"name": "lime", "colour": "green", "qty": 6, "ripe": False},
    {"name": "plum", "colour": "purple", "qty": 2, "ripe": True},
]


def _table(rows: list[dict[str, object]]) -> Table:
    """Build the table shown to a person at a terminal.

    Args:
        rows: The fruit records to show, one per table row.

    Returns:
        A table with a header rule, a right-aligned `qty` column & `-` in
        place of a missing quantity.
    """
    table = Table(box=box.SIMPLE_HEAD)
    table.add_column("name")
    table.add_column("colour")
    table.add_column("qty", justify="right")
    table.add_column("ripe")
    for row in rows:
        qty = "-" if row["qty"] is None else str(row["qty"])
        ripe = "yes" if row["ripe"] else "no"
        table.add_row(str(row["name"]), str(row["colour"]), qty, ripe)
    return table


@pyclig.command(
    "fruit",
    examples=["fruit", "fruit --json", "fruit --plain\napple\tred\t3\ttrue"],
)
@pyclig.options.json_output()
@pyclig.options.plain()
@click.option(
    "--ripe", "ripe_only", is_flag=True, help="List only ripe fruit."
)
@pyclig.pass_context
def cli(ctx: pyclig.Context, json_output: bool, ripe_only: bool) -> None:
    """List the fruit in the bowl."""
    rows = [fruit for fruit in FRUIT if fruit["ripe"] or not ripe_only]
    ctx.emit(rows, table=lambda: _table(rows), caption=f"{len(rows)} fruit")
