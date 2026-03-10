"""NetWorth tab: investments, liquidity, credits/debts, and total net worth."""

from __future__ import annotations

import calendar

import polars as pl
from nicegui import ui

from finguard.df_operations import (
    _INVESTMENT_CATEGORIES,
    _LIQUIDITY_CATEGORIES,
    CreditsDebts,
    InvestmentHoldings,
    Liquidity,
)
from finguard.ui_tables import _build_investment_table, _build_simple_value_table


def build_networth_tab(st, _refreshables):
    """Build the NetWorth tab content with sub-tabs.

    Registers ``investment_content``, ``liquidity_content``,
    ``credits_debts_content``, and ``total_networth_content`` in *_refreshables*.
    """

    # Sub-tabs for NetWorth
    with ui.tabs().classes("w-full") as networth_tabs:
        ui.tab("Investments").props("no-caps")
        ui.tab("Liquidity").props("no-caps")
        ui.tab("Credits/Debts").props("no-caps")
        ui.tab("Total NetWorth").props("no-caps")

    with ui.tab_panels(networth_tabs, value="Investments").classes("w-full"):
        with ui.tab_panel("Liquidity"):

            @ui.refreshable
            def liquidity_content():
                liq = Liquidity(year=st.year)
                month_abbrs = [calendar.month_abbr[m] for m in range(1, 13)]

                # -- Add asset form --
                with ui.card().classes("mb-4"):
                    ui.label("Add Liquidity Asset").classes(
                        "text-sm font-semibold mb-2"
                    )
                    with ui.row().classes("items-end gap-4"):
                        inp_name = ui.input("Asset name").classes("w-48")
                        inp_cat = ui.select(
                            options=_LIQUIDITY_CATEGORIES,
                            label="Category",
                            value=_LIQUIDITY_CATEGORIES[0],
                        ).classes("w-40")
                        inp_cur = ui.input("Currency", value="E").classes(
                            "w-24"
                        )

                        def do_add_liq():
                            name = inp_name.value.strip()
                            if not name:
                                ui.notify(
                                    "Asset name is required", type="warning"
                                )
                                return
                            try:
                                liq.add_asset(
                                    name,
                                    inp_cat.value,
                                    inp_cur.value.strip() or "E",
                                )
                                inp_name.value = ""
                                liquidity_content.refresh()
                                _refreshables[
                                    "total_networth_content"
                                ].refresh()
                                ui.notify(
                                    f"Asset '{name}' added", type="positive"
                                )
                            except ValueError as exc:
                                ui.notify(str(exc), type="negative")

                        ui.button("Add", icon="add", on_click=do_add_liq)

                if liq.df.height == 0:
                    ui.label("No liquidity assets yet.").classes(
                        "text-gray-500"
                    )
                else:
                    _build_simple_value_table(
                        df=liq.df,
                        name_col="asset_name",
                        type_col="category",
                        month_abbrs=month_abbrs,
                        set_fn=liq.set_value,
                        remove_fn=liq.remove_asset,
                        rename_fn=liq.rename_asset,
                        set_category_fn=liq.set_category,
                        categories=_LIQUIDITY_CATEGORIES,
                        refresh_fn=liquidity_content.refresh,
                        on_cell_change=lambda: _refreshables[
                            "total_networth_content"
                        ].refresh(),
                    )

            liquidity_content()
            _refreshables["liquidity_content"] = liquidity_content

        with ui.tab_panel("Credits/Debts"):

            @ui.refreshable
            def credits_debts_content():
                cd = CreditsDebts(year=st.year)
                month_abbrs = [calendar.month_abbr[m] for m in range(1, 13)]

                # -- Add entry form --
                with ui.card().classes("mb-4"):
                    ui.label("Add Credit / Debt").classes(
                        "text-sm font-semibold mb-2"
                    )
                    ui.label(
                        "Positive values = credit, negative values = debt"
                    ).classes("text-xs text-gray-500 mb-1")
                    with ui.row().classes("items-end gap-4"):
                        inp_name = ui.input("Name").classes("w-48")
                        inp_cur = ui.input("Currency", value="E").classes(
                            "w-24"
                        )

                        def do_add_cd():
                            name = inp_name.value.strip()
                            if not name:
                                ui.notify("Name is required", type="warning")
                                return
                            try:
                                cd.add_entry(
                                    name,
                                    inp_cur.value.strip() or "E",
                                )
                                inp_name.value = ""
                                credits_debts_content.refresh()
                                _refreshables[
                                    "total_networth_content"
                                ].refresh()
                                ui.notify(
                                    f"Entry '{name}' added", type="positive"
                                )
                            except ValueError as exc:
                                ui.notify(str(exc), type="negative")

                        ui.button("Add", icon="add", on_click=do_add_cd)

                if cd.df.height == 0:
                    ui.label("No credits or debts yet.").classes(
                        "text-gray-500"
                    )
                else:
                    _build_simple_value_table(
                        df=cd.df,
                        name_col="name",
                        type_col=None,
                        month_abbrs=month_abbrs,
                        set_fn=cd.set_value,
                        remove_fn=cd.remove_entry,
                        rename_fn=cd.rename_entry,
                        refresh_fn=credits_debts_content.refresh,
                        on_cell_change=lambda: _refreshables[
                            "total_networth_content"
                        ].refresh(),
                    )

            credits_debts_content()
            _refreshables["credits_debts_content"] = credits_debts_content

        with ui.tab_panel("Total NetWorth"):

            @ui.refreshable
            def _total_networth_content():
                inv = InvestmentHoldings(year=st.year)
                liq = Liquidity(year=st.year)
                cd = CreditsDebts(year=st.year)
                month_abbrs = [calendar.month_abbr[m] for m in range(1, 13)]
                mcols = [f"{m:02d}" for m in range(1, 13)]

                # Compute investment totals per category per month
                inv_val = inv.df_value
                inv_by_cat: dict[str, list[float]] = {}
                for cat in _INVESTMENT_CATEGORIES:
                    cat_df = inv_val.filter(pl.col("category") == cat)
                    inv_by_cat[cat] = [
                        cat_df[c].sum() if cat_df.height else 0.0
                        for c in mcols
                    ]
                inv_totals = [
                    sum(inv_by_cat[cat][i] for cat in _INVESTMENT_CATEGORIES)
                    for i in range(12)
                ]

                # Compute liquidity totals per month
                liq_totals = [
                    liq.df[c].sum() if liq.df.height else 0.0 for c in mcols
                ]

                # Compute credits/debts totals (positive=credit, negative=debt)
                cd_totals = [
                    cd.df[c].sum() if cd.df.height else 0.0 for c in mcols
                ]

                net_totals = [
                    inv_totals[i] + liq_totals[i] + cd_totals[i]
                    for i in range(12)
                ]

                # Previous December net worth for January change
                prev_year = st.year - 1
                try:
                    p_inv = InvestmentHoldings(year=prev_year)
                    p_liq = Liquidity(year=prev_year)
                    p_cd = CreditsDebts(year=prev_year)
                    dec = "12"
                    prev_dec_nw = (
                        (p_inv.df_value[dec].sum() if p_inv.df_value.height else 0.0)
                        + (p_liq.df[dec].sum() if p_liq.df.height else 0.0)
                        + (p_cd.df[dec].sum() if p_cd.df.height else 0.0)
                    )
                except Exception:
                    prev_dec_nw = None

                nw_change: list[float | None] = []
                pct_nw_change: list[float | None] = []
                for i in range(12):
                    prev = prev_dec_nw if i == 0 else net_totals[i - 1]
                    cur = net_totals[i]
                    if prev is not None and prev != 0.0 and cur:
                        nw_change.append(cur - prev)
                        pct_nw_change.append((cur - prev) / prev * 100)
                    elif prev is not None and cur:
                        nw_change.append(cur - prev)
                        pct_nw_change.append(None)
                    else:
                        nw_change.append(None)
                        pct_nw_change.append(None)

                ui.label(f"Net Worth \u2014 {st.year}").classes(
                    "text-lg font-bold mt-2 mb-4"
                )

                rows_data = [
                    *[(cat, inv_by_cat[cat]) for cat in _INVESTMENT_CATEGORIES],
                    ("Liquidity", liq_totals),
                    ("Credits/Debts", cd_totals),
                    ("Net Worth", net_totals),
                    ("NW Change", nw_change),
                    ("% NW Change", pct_nw_change),
                ]

                with (
                    ui.element("table")
                    .classes("w-full border-collapse text-sm")
                    .style("border-spacing:0")
                ):
                    with ui.element("thead"):
                        with ui.element("tr"):
                            with (
                                ui.element("th")
                                .classes(
                                    "text-left px-2 py-1 border-b border-r"
                                )
                                .style("min-width:160px")
                            ):
                                ui.label("").classes("text-xs font-bold")
                            for abbr in month_abbrs:
                                with (
                                    ui.element("th")
                                    .classes(
                                        "text-right px-2 py-1 border-b border-r"
                                    )
                                    .style("min-width:72px")
                                ):
                                    ui.label(abbr).classes("text-xs font-bold")

                    with ui.element("tbody"):
                        for label, values in rows_data:
                            is_total = label == "Net Worth"
                            is_pct = label == "% NW Change"
                            border_top = " border-t-2" if is_total else ""
                            weight = "font-bold" if is_total else ""
                            with ui.element("tr").classes(border_top):
                                with ui.element("td").classes(
                                    f"px-2 py-1 border-r text-xs {weight}"
                                ):
                                    ui.label(label)
                                for v in values:
                                    with ui.element("td").classes(
                                        "px-1 py-0 border-r text-right"
                                    ):
                                        if v is None or v == 0.0:
                                            txt = ""
                                        elif is_pct:
                                            txt = f"{v:,.2f}%"
                                        else:
                                            txt = f"{v:,.2f}"
                                        ui.label(txt).classes(
                                            f"text-xs {weight}"
                                        )

            _refreshables["total_networth_content"] = _total_networth_content
            _total_networth_content()

        with ui.tab_panel("Investments"):

            @ui.refreshable
            def investment_content():
                inv = InvestmentHoldings(year=st.year)

                # -- Add asset form ------------------------------------------
                with ui.card().classes("mb-4"):
                    ui.label("Add Asset").classes("text-sm font-semibold mb-2")
                    with ui.row().classes("items-end gap-4"):
                        inp_asset = ui.input("Asset name").classes("w-48")
                        inp_cat = ui.select(
                            options=_INVESTMENT_CATEGORIES,
                            label="Category",
                            value=_INVESTMENT_CATEGORIES[0],
                        ).classes("w-40")
                        inp_link = ui.input("Link (optional)").classes("w-64")

                        def do_add_asset():
                            name = inp_asset.value.strip()
                            if not name:
                                ui.notify(
                                    "Asset name is required", type="warning"
                                )
                                return
                            try:
                                inv.add_asset(
                                    name, inp_cat.value, inp_link.value.strip()
                                )
                                inp_asset.value = ""
                                inp_link.value = ""
                                investment_content.refresh()
                                ui.notify(
                                    f"Asset '{name}' added", type="positive"
                                )
                            except ValueError as exc:
                                ui.notify(str(exc), type="negative")

                        ui.button("Add", icon="add", on_click=do_add_asset)

                if inv.df.height == 0:
                    ui.label("No assets yet.").classes("text-gray-500")
                else:
                    month_abbrs = [calendar.month_abbr[m] for m in range(1, 13)]

                    @ui.refreshable
                    def value_table_content():
                        ui.label(
                            f"Value \u2014 {st.year} (quantity \u00d7 price)"
                        ).classes("text-lg font-bold mt-2 mb-4")

                        _build_investment_table(
                            inv=inv,
                            df=inv.df_value,
                            month_abbrs=month_abbrs,
                            editable=False,
                            set_fn=None,
                            show_delete=False,
                            refresh_fn=None,
                        )

                    # -- Sub-tabs: Holdings / Prices / Value -----------------
                    with ui.tabs().classes("w-full") as inv_subtabs:
                        ui.tab("Holdings").props("no-caps")
                        ui.tab("Prices").props("no-caps")
                        ui.tab("Value").props("no-caps")

                    with ui.tab_panels(inv_subtabs, value="Holdings").classes(
                        "w-full"
                    ):
                        # ===== HOLDINGS (Quantity) ==========================
                        with ui.tab_panel("Holdings"):
                            ui.label(
                                f'Holdings \u2014 {st.year} (quantity in number of "shares")'
                            ).classes("text-lg font-bold mt-2 mb-4")

                            _build_investment_table(
                                inv=inv,
                                df=inv.df,
                                month_abbrs=month_abbrs,
                                editable=True,
                                set_fn=inv.set_quantity,
                                show_delete=True,
                                refresh_fn=investment_content.refresh,
                                on_cell_change=value_table_content.refresh,
                            )

                        # ===== PRICES =======================================
                        with ui.tab_panel("Prices"):
                            ui.label(
                                f"Prices \u2014 {st.year} (price per share)"
                            ).classes("text-lg font-bold mt-2 mb-4")

                            _build_investment_table(
                                inv=inv,
                                df=inv.df_prices,
                                month_abbrs=month_abbrs,
                                editable=True,
                                set_fn=inv.set_price,
                                value_kwarg="price",
                                show_delete=False,
                                refresh_fn=investment_content.refresh,
                                on_cell_change=value_table_content.refresh,
                            )

                        # ===== VALUE (Qty × Price) ==========================
                        with ui.tab_panel("Value"):
                            value_table_content()

            investment_content()
            _refreshables["investment_content"] = investment_content
