"""Chart data preparation for Finguard plots (no UI imports)."""

from __future__ import annotations

import calendar

import polars as pl

from finguard.df_operations import (
    Cashflow,
    CreditsDebts,
    InvestmentHoldings,
    Liquidity,
    _INCOME_CATEGORIES,
    _INVESTMENT_CATEGORIES,
)
from finguard.paths import PRIMARIES_FILENAME, SECONDARIES_FILENAME, get_year_summary_path


def monthly_expenses_comparison(
    year: int,
    months: list[int],
    kind: str = "primary",
) -> dict | None:
    """Return ECharts option dict for a bar chart comparing expenses by category.

    Parameters
    ----------
    year:
        Calendar year.
    months:
        Up to 3 month numbers (1-12) to compare side by side.
    kind:
        ``"primary"`` or ``"secondary"`` category grouping.

    Returns
    -------
    dict or None
        ECharts option dict ready for ``ui.echart()``, or *None* if no data.
    """
    filename = PRIMARIES_FILENAME if kind == "primary" else SECONDARIES_FILENAME
    cat_col = f"{kind}_category"
    path = get_year_summary_path(year, filename)

    if not path.exists():
        return None

    df = pl.read_parquet(str(path))

    # Drop the "Total" row
    df = df.filter(pl.col(cat_col) != "Total")

    if df.height == 0:
        return None

    # Build month column labels (YYYY-MM)
    month_labels = [f"{year}-{m:02d}" for m in months]
    # Keep only months that exist in the dataframe
    available = [m for m in month_labels if m in df.columns]

    if not available:
        return None

    categories = df[cat_col].to_list()

    _SERIES_COLORS = ["#5470c6", "#91cc75", "#fac858"]

    series = []
    for idx, col in enumerate(available):
        m = int(col.split("-")[1])
        values = [round(v) for v in df[col].to_list()]
        color = _SERIES_COLORS[idx % len(_SERIES_COLORS)]
        series.append(
            {
                "name": calendar.month_abbr[m],
                "type": "bar",
                "data": values,
                "itemStyle": {"color": color},
                # No label
            }
        )

    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": [s["name"] for s in series], "textStyle": {"color": "#ffffff"}},
        "xAxis": {
            "type": "category",
            "data": categories,
            "axisLabel": {"rotate": 35, "fontSize": 16, "color": "#ffffff"},
            "axisLine": {"lineStyle": {"color": "#ffffff"}},
            "axisTick": {"lineStyle": {"color": "#ffffff"}},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"color": "#ffffff", "fontSize": 16},
            "axisLine": {"lineStyle": {"color": "#ffffff"}},
            "splitLine": {"lineStyle": {"color": "#555555"}},
        },
        "series": series,
    }


_CHART_AXIS_STYLE = {
    "axisLabel": {"color": "#ffffff", "fontSize": 16},
    "axisLine": {"lineStyle": {"color": "#ffffff"}},
    "axisTick": {"lineStyle": {"color": "#ffffff"}},
}


def category_expenses_over_months(
    year: int,
    selected_categories: list[str],
    kind: str = "primary",
) -> dict | None:
    """Return ECharts option dict for a line chart of up to 3 categories over months.

    Parameters
    ----------
    year:
        Calendar year.
    selected_categories:
        Up to 3 category names to plot as separate lines.
    kind:
        ``"primary"`` or ``"secondary"`` category grouping.

    Returns
    -------
    dict or None
        ECharts option dict ready for ``ui.echart()``, or *None* if no data.
    """
    filename = PRIMARIES_FILENAME if kind == "primary" else SECONDARIES_FILENAME
    cat_col = f"{kind}_category"
    path = get_year_summary_path(year, filename)

    if not path.exists():
        return None

    df = pl.read_parquet(str(path))
    df = df.filter(pl.col(cat_col) != "Total")

    if df.height == 0:
        return None

    # Month columns in chronological order
    month_cols = sorted(c for c in df.columns if "-" in c and c.split("-")[1].isdigit())
    if not month_cols:
        return None

    month_labels = [calendar.month_abbr[int(c.split("-")[1])] for c in month_cols]

    _SERIES_COLORS = ["#5470c6", "#91cc75", "#fac858"]

    series = []
    for idx, cat in enumerate(selected_categories[:3]):
        row = df.filter(pl.col(cat_col) == cat)
        if row.height == 0:
            values = [0] * len(month_cols)
        else:
            values = [round(row[c][0]) for c in month_cols]
        color = _SERIES_COLORS[idx % len(_SERIES_COLORS)]
        series.append(
            {
                "name": cat,
                "type": "line",
                "data": values,
                "smooth": False,
                "symbol": "circle",
                "symbolSize": 7,
                "lineStyle": {"color": color, "width": 2},
                "itemStyle": {"color": color},
                # No label
            }
        )

    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": [s["name"] for s in series], "textStyle": {"color": "#ffffff"}},
        "xAxis": {
            "type": "category",
            "data": month_labels,
            **_CHART_AXIS_STYLE,
        },

        "yAxis": {
            "type": "value",
            **_CHART_AXIS_STYLE,
            "splitLine": {"lineStyle": {"color": "#555555"}},
        },
        "series": series,
    }


def cumulative_expenses_pie(
    year: int,
    kind: str = "primary",
) -> dict | None:
    """Return ECharts option dict for a pie chart of cumulative yearly expenses."""
    filename = PRIMARIES_FILENAME if kind == "primary" else SECONDARIES_FILENAME
    cat_col = f"{kind}_category"
    path = get_year_summary_path(year, filename)

    if not path.exists():
        return None

    df = pl.read_parquet(str(path))
    df = df.filter(pl.col(cat_col) != "Total")
    if df.height == 0:
        return None

    month_cols = [c for c in df.columns if "-" in c and c.split("-")[1].isdigit()]
    if not month_cols:
        return None

    categories = df[cat_col].to_list()
    totals = [sum(df[c][i] for c in month_cols) for i in range(df.height)]
    data = [
        {"name": cat, "value": round(val)}
        for cat, val in zip(categories, totals)
        if cat and val > 0
    ]
    if not data:
        return None

    return {
        "tooltip": {"trigger": "item"},
        "legend": {"orient": "vertical", "left": "left", "textStyle": {"color": "#fff"}},
        "series": [
            {
                "type": "pie",
                "radius": "70%",
                "data": data,
                "label": {"color": "#fff", "fontSize": 16},
                "labelLine": {"lineStyle": {"color": "#fff"}},
                "itemStyle": {"borderColor": "#222", "borderWidth": 1},
            }
        ],
    }


def cashflow_bar_chart(year: int) -> dict | None:
    """Return ECharts option dict for a grouped bar chart of Income/Spending/Saving."""
    cf = Cashflow(year=year)
    cf.recompute()

    months = [calendar.month_abbr[m] for m in range(1, 13)]
    income_vals = [round(cf._get_value("Income", f"{m:02d}"), 2) for m in range(1, 13)]
    spending_vals = [round(cf._get_value("Spending", f"{m:02d}"), 2) for m in range(1, 13)]
    saving_vals = [round(cf._get_value("Saving", f"{m:02d}"), 2) for m in range(1, 13)]

    if all(v == 0 for v in income_vals + spending_vals):
        return None

    series = [
        {
            "name": "Income",
            "type": "bar",
            "data": income_vals,
            "itemStyle": {"color": "#91cc75"},
        },
        {
            "name": "Spending",
            "type": "bar",
            "data": spending_vals,
            "itemStyle": {"color": "#ee6666"},
        },
        {
            "name": "Saving",
            "type": "bar",
            "data": saving_vals,
            "itemStyle": {"color": "#5470c6"},
        },
    ]

    return {
        "title": {
            "text": "Cashflow",
            "left": "center",
            "top": 10,
            "textStyle": {"color": "#fff", "fontSize": 20},
        },
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": ["Income", "Spending", "Saving"], "textStyle": {"color": "#fff"}},
        "xAxis": {
            "type": "category",
            "data": months,
            **_CHART_AXIS_STYLE,
        },
        "yAxis": {
            "type": "value",
            **_CHART_AXIS_STYLE,
            "splitLine": {"lineStyle": {"color": "#555555"}},
        },
        "series": series,
    }


def income_pie_chart(year: int) -> dict | None:
    """Return ECharts option dict for a pie chart of yearly income by category."""
    cf = Cashflow(year=year)
    cf.recompute()

    data = []
    for cat in _INCOME_CATEGORIES:
        total = sum(cf._get_value(cat, f"{m:02d}") for m in range(1, 13))
        if total > 0:
            data.append({"name": cat, "value": round(total, 2)})

    if not data:
        return None

    return {
        "title": {
            "text": "Sources of income",
            "left": "center",
            "top": 10,
            "textStyle": {"color": "#fff", "fontSize": 20},
        },
        "tooltip": {"trigger": "item"},
        "legend": {"orient": "vertical", "left": "left", "textStyle": {"color": "#fff"}},
        "series": [
            {
                "type": "pie",
                "radius": "70%",
                "data": data,
                "label": {"color": "#fff", "fontSize": 16},
                "labelLine": {"lineStyle": {"color": "#fff"}},
                "itemStyle": {"borderColor": "#222", "borderWidth": 1},
            }
        ],
    }


# ---------------------------------------------------------------------------
# Net Worth charts
# ---------------------------------------------------------------------------

def networth_allocation_pie(year: int, month: int) -> dict | None:
    """Return ECharts option dict for a pie chart of net worth by asset type.

    Slices: each investment category, Liquidity, and Credits/Debts.

    Parameters
    ----------
    year:
        Calendar year.
    month:
        Month number (1-12) to display.
    """
    inv = InvestmentHoldings(year=year)
    liq = Liquidity(year=year)
    cd = CreditsDebts(year=year)
    col = f"{month:02d}"

    data = []
    for cat in _INVESTMENT_CATEGORIES:
        cat_df = inv.df_value.filter(pl.col("category") == cat)
        val = cat_df[col].sum() if cat_df.height else 0.0
        if val > 0:
            data.append({"name": cat, "value": round(val, 2)})

    liq_val = liq.df[col].sum() if liq.df.height else 0.0
    if liq_val > 0:
        data.append({"name": "Liquidity", "value": round(liq_val, 2)})

    cd_val = cd.df[col].sum() if cd.df.height else 0.0
    if cd_val > 0:
        data.append({"name": "Credits", "value": round(cd_val, 2)})
    elif cd_val < 0:
        data.append({"name": "Debts", "value": round(abs(cd_val), 2)})

    if not data:
        return None

    month_label = calendar.month_name[month]
    return {
        "title": {
            "text": f"Asset allocation — {month_label} {year}",
            "left": "center",
            "top": 10,
            "textStyle": {"color": "#fff", "fontSize": 20},
        },
        "tooltip": {"trigger": "item"},
        "legend": {"orient": "vertical", "left": "left", "textStyle": {"color": "#fff"}},
        "series": [
            {
                "type": "pie",
                "radius": "70%",
                "data": data,
                "label": {"color": "#fff", "fontSize": 16},
                "labelLine": {"lineStyle": {"color": "#fff"}},
                "itemStyle": {"borderColor": "#222", "borderWidth": 1},
            }
        ],
    }


def networth_evolution_line(year: int) -> dict | None:
    """Return ECharts option dict for a stacked area chart of net worth over months.

    Shows one area per component (each investment category, Liquidity,
    Credits/Debts) and a bold line for total Net Worth.
    """
    inv = InvestmentHoldings(year=year)
    liq = Liquidity(year=year)
    cd = CreditsDebts(year=year)
    mcols = [f"{m:02d}" for m in range(1, 13)]
    months = [calendar.month_abbr[m] for m in range(1, 13)]

    # Build per-component monthly series
    components: list[tuple[str, list[float]]] = []
    for cat in _INVESTMENT_CATEGORIES:
        cat_df = inv.df_value.filter(pl.col("category") == cat)
        vals = [round(cat_df[c].sum(), 2) if cat_df.height else 0.0 for c in mcols]
        components.append((cat, vals))

    liq_vals = [round(liq.df[c].sum(), 2) if liq.df.height else 0.0 for c in mcols]
    components.append(("Liquidity", liq_vals))

    cd_vals = [round(cd.df[c].sum(), 2) if cd.df.height else 0.0 for c in mcols]
    components.append(("Credits/Debts", cd_vals))

    net = [sum(comp[1][i] for comp in components) for i in range(12)]
    if all(v == 0 for v in net):
        return None

    _COLORS = ["#5470c6", "#91cc75", "#fac858", "#73c0de", "#ee6666"]

    series = []
    for idx, (name, vals) in enumerate(components):
        series.append({
            "name": name,
            "type": "line",
            "stack": "nw",
            "areaStyle": {"opacity": 0.35},
            "data": vals,
            "symbol": "none",
            "lineStyle": {"width": 1, "color": _COLORS[idx % len(_COLORS)]},
            "itemStyle": {"color": _COLORS[idx % len(_COLORS)]},
        })
    series.append({
        "name": "Net Worth",
        "type": "line",
        "data": [round(v, 2) for v in net],
        "symbol": "circle",
        "symbolSize": 6,
        "lineStyle": {"width": 3, "color": "#fff"},
        "itemStyle": {"color": "#fff"},
    })

    return {
        "title": {
            "text": f"Net Worth — {year}",
            "left": "center",
            "top": 10,
            "textStyle": {"color": "#fff", "fontSize": 20},
        },
        "tooltip": {"trigger": "axis"},
        "legend": {
            "data": [s["name"] for s in series],
            "textStyle": {"color": "#fff"},
        },
        "xAxis": {
            "type": "category",
            "data": months,
            **_CHART_AXIS_STYLE,
        },
        "yAxis": {
            "type": "value",
            **_CHART_AXIS_STYLE,
            "splitLine": {"lineStyle": {"color": "#555555"}},
        },
        "series": series,
    }


def monthly_expenses_pie(
    st_de, kind: str = "primary"
) -> dict | None:
    """Return ECharts option dict for a pie chart of monthly expenses by category.

    Parameters
    ----------
    st_de:
        DetailedExpenses instance for the selected month.
    kind:
        "primary" or "secondary" category grouping.

    Returns
    -------
    dict or None
        ECharts option dict ready for ui.echart(), or None if no data.
    """
    cat_col = f"{kind}_category"
    df = st_de.create_expenses_summary_table(cat_col)
    if df.height == 0:
        return None
    labels = df[cat_col].to_list()
    values = df["total_expense_in_ref_currency"].to_list()
    data = [
        {"name": label, "value": round(val)}
        for label, val in zip(labels, values)
        if label and val > 0
    ]
    return {
        "tooltip": {"trigger": "item"},
        "legend": {"orient": "vertical", "left": "left", "textStyle": {"color": "#fff"}},
        "series": [
            {
                "type": "pie",
                "radius": "70%",
                "data": data,
                "label": {"color": "#fff", "fontSize": 16},
                "labelLine": {"lineStyle": {"color": "#fff"}},
                "itemStyle": {"borderColor": "#222", "borderWidth": 1},
            }
        ],
    }
