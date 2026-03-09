"""NiceGUI chart rendering components for Finguard."""

from __future__ import annotations

from nicegui import ui

from finguard.plots import (
    category_expenses_over_months,
    cumulative_expenses_pie,
    monthly_expenses_comparison,
    monthly_expenses_pie,
)


def render_monthly_expenses_chart(
    year: int,
    months: list[int],
    kind: str = "primary",
) -> None:
    """Render a bar chart comparing monthly expenses by category.

    Parameters
    ----------
    year:
        Calendar year.
    months:
        Up to 3 month numbers (1-12) to display.
    kind:
        ``"primary"`` or ``"secondary"``.
    """
    opts = monthly_expenses_comparison(year, months, kind)
    if opts is None:
        ui.label("No expense data available for the selected months.").classes(
            "text-gray-500"
        )
        return
    ui.echart(opts).classes("w-full").style("height: 420px")


def render_category_expenses_chart(
    year: int,
    categories: list[str],
    kind: str = "primary",
) -> None:
    """Render a line chart showing up to 3 categories over all months.

    Parameters
    ----------
    year:
        Calendar year.
    categories:
        Up to 3 category names.
    kind:
        ``"primary"`` or ``"secondary"``.
    """
    opts = category_expenses_over_months(year, categories, kind)
    if opts is None:
        ui.label("No expense data available.").classes("text-gray-500")
        return
    ui.echart(opts).classes("w-full").style("height: 420px")


def render_cumulative_expenses_pie(year: int, kind: str = "primary") -> None:
    """Render a pie chart of cumulative yearly expenses by category."""
    opts = cumulative_expenses_pie(year, kind)
    if opts is None:
        ui.label("No cumulative data available.").classes("text-gray-500")
        return
    ui.echart(opts).classes("w-full").style("height: 420px")


def render_monthly_expenses_pie(st_de, kind: str = "primary") -> None:
    """Render a pie chart of monthly expenses by category."""
    opts = monthly_expenses_pie(st_de, kind)
    if opts is None:
        ui.label("No expense data available for this month.").classes("text-gray-500")
        return
    ui.echart(opts).classes("w-full").style("height: 320px")
