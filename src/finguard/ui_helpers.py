"""Shared constants and utility functions for the Finguard UI."""

from __future__ import annotations

import ast
import calendar
import operator
from datetime import date

import polars as pl

from finguard.paths import get_dbs_root

_MONTH_NAMES: dict[int, str] = {i: calendar.month_name[i] for i in range(1, 13)}

_EXPENSE_COLUMNS = [
    {
        "name": "expense_name",
        "label": "Name",
        "field": "expense_name",
        "align": "left",
        "sortable": True,
    },
    {
        "name": "expense_date",
        "label": "Date",
        "field": "expense_date",
        "align": "left",
        "sortable": True,
    },
    {
        "name": "expense_amount",
        "label": "Amount",
        "field": "expense_amount",
        "align": "right",
        "sortable": True,
    },
    {"name": "currency", "label": "Cur", "field": "currency", "align": "center"},
    {
        "name": "expense_in_ref_currency",
        "label": "Ref Amount",
        "field": "expense_in_ref_currency",
        "align": "right",
        "sortable": True,
    },
    {
        "name": "primary_category",
        "label": "Primary",
        "field": "primary_category",
        "align": "left",
        "sortable": True,
    },
    {
        "name": "secondary_category",
        "label": "Secondary",
        "field": "secondary_category",
        "align": "left",
        "sortable": True,
    },
    {"name": "actions", "label": "", "field": "actions", "align": "center"},
]


# ---------------------------------------------------------------------------
# Safe math expression evaluator
# ---------------------------------------------------------------------------

_SAFE_OPS: dict[type, object] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval_expr(expr: str) -> float:
    """Safely evaluate a simple arithmetic expression (+-*/ and parentheses)."""
    tree = ast.parse(expr.strip(), mode="eval")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_eval(node.operand))
        raise ValueError(f"Unsupported expression: {ast.dump(node)}")

    return _eval(tree)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _discover_years() -> list[int]:
    """Return sorted years with data directories, always including the current year."""
    root = get_dbs_root()
    years: set[int] = {date.today().year}
    for child in root.iterdir():
        if child.is_dir():
            try:
                years.add(int(child.name))
            except ValueError:
                pass
    return sorted(years)


def _df_to_rows(df: pl.DataFrame) -> list[dict]:
    """Convert a Polars DataFrame to a list of dicts for ``ui.table``."""
    rows = df.to_dicts()
    for i, row in enumerate(rows):
        row.setdefault("id", i)
        for key, val in row.items():
            if isinstance(val, date):
                row[key] = val.isoformat()
            elif isinstance(val, float):
                row[key] = round(val, 2)
    return rows
