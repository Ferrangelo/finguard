"""Cashflow tab."""

from __future__ import annotations

import calendar

from nicegui import ui

from finguard.df_operations import (
    _INCOME_CATEGORIES,
    Cashflow,
)
from finguard.plots import cashflow_bar_chart, income_pie_chart
from finguard.ui_helpers import _safe_eval_expr


def build_cashflow_tab(st, _refreshables):
    """Build the Cashflow tab content.

    Registers ``cashflow_content`` in *_refreshables*.
    """

    @ui.refreshable
    def cashflow_content():
        cf = Cashflow(year=st.year)
        cf.recompute()

        ui.label(f"Cashflow \u2014 {st.year}").classes(
            "text-lg font-bold mt-2 mb-4"
        )

        month_abbrs = [calendar.month_abbr[m] for m in range(1, 13)]
        derived = {"Income", "Spending", "Saving", "Saving %"}

        with (
            ui.element("table")
            .classes("w-full border-collapse text-sm")
            .style("border-spacing: 0")
        ):
            # Header
            with ui.element("thead"):
                with ui.element("tr"):
                    ui.element("th").classes(
                        "text-left px-2 py-1 border-b border-r"
                    ).style("min-width:160px")
                    for abbr in month_abbrs:
                        with (
                            ui.element("th")
                            .classes("text-right px-2 py-1 border-b border-r")
                            .style("min-width:80px")
                        ):
                            ui.label(abbr).classes("text-xs font-bold")

            # Body
            with ui.element("tbody"):
                all_cats = list(_INCOME_CATEGORIES) + list(
                    ["Income", "Spending", "Saving", "Saving %"]
                )
                for cat in all_cats:
                    is_derived = cat in derived
                    # Separator line before Income row
                    border_top = " border-t-2" if cat == "Income" else ""

                    with ui.element("tr").classes(border_top):
                        # Category label
                        weight = "font-bold" if is_derived else ""
                        with ui.element("td").classes(
                            f"px-2 py-1 border-r {weight}"
                        ):
                            ui.label(cat).classes("text-xs")

                        # Month cells
                        for m in range(1, 13):
                            col = f"{m:02d}"
                            val = cf._get_value(cat, col)

                            with ui.element("td").classes(
                                "px-1 py-0 border-r text-right"
                            ):
                                if is_derived:
                                    # Read-only derived value
                                    if cat == "Saving %":
                                        txt = f"{val:.1f}%"
                                    else:
                                        txt = f"{val:.2f}"

                                    if cat == "Spending":
                                        color = "text-red-400"
                                    elif cat in ("Saving", "Saving %"):
                                        color = (
                                            "text-green-400"
                                            if val > 0
                                            else "text-red-400"
                                            if val < 0
                                            else ""
                                        )
                                    else:
                                        color = ""

                                    ui.label(txt).classes(
                                        f"text-xs font-bold {color}"
                                    )
                                else:
                                    # Editable income input
                                    def _make_handler(_cf=cf, _m=m, _cat=cat):
                                        def handler(e):
                                            try:
                                                v = (
                                                    _safe_eval_expr(str(e.sender.value))
                                                    if e.sender.value not in (None, "")
                                                    else 0.0
                                                )
                                            except (ValueError, TypeError, ZeroDivisionError, SyntaxError):
                                                return
                                            e.sender.value = str(v) if v != 0.0 else ""
                                            e.sender.update()
                                            _cf.set_income(
                                                month=_m,
                                                category=_cat,
                                                value=v,
                                            )
                                            cashflow_content.refresh()

                                        return handler

                                    inp = ui.input(
                                        value=str(val) if val != 0.0 else "",
                                    ).classes("w-20").props(
                                        "dense borderless"
                                        ' input-class="text-right text-xs"'
                                    )
                                    inp.on("blur", _make_handler())

        # -- Charts below the table ------------------------------------------
        with ui.row().classes("w-full gap-4 mt-4"):
            with ui.card().classes("flex-1"):
                bar_opts = cashflow_bar_chart(st.year)
                if bar_opts:
                    ui.echart(bar_opts).classes("w-full h-80")
                else:
                    ui.label("No cashflow data to chart.").classes("text-sm text-gray-400")

            with ui.card().classes("flex-1"):
                pie_opts = income_pie_chart(st.year)
                if pie_opts:
                    ui.echart(pie_opts).classes("w-full h-80")
                else:
                    ui.label("No income data to chart.").classes("text-sm text-gray-400")

    cashflow_content()
    _refreshables["cashflow_content"] = cashflow_content
