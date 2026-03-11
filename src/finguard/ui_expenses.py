"""Expenses tab: detailed expenses, summary, and category mappings."""

from __future__ import annotations

import calendar
import re
from datetime import date

import polars as pl
from nicegui import ui

from finguard.config import (
    add_mapping as config_add_mapping,
)
from finguard.config import (
    get_all_mappings,
    get_mapping,
)
from finguard.config import (
    remove_mapping as config_remove_mapping,
)
from finguard.df_operations import (
    Cashflow,
    normalize_category_value,
)
from finguard.paths import (
    PRIMARIES_FILENAME,
    SECONDARIES_FILENAME,
    get_year_summary_path,
)
from finguard.ui_helpers import (
    _EXPENSE_COLUMNS,
    _MONTH_NAMES,
    _df_to_rows,
    _safe_eval_expr,
)
from finguard.ui_plots import (
    render_category_expenses_chart,
    render_cumulative_expenses_pie,
    render_monthly_expenses_chart,
    render_monthly_expenses_pie,
)


def build_expenses_tab(st, _refreshables):
    """Build the Expenses tab content with sub-tabs.

    Registers ``refresh_table`` and ``summary_content`` in *_refreshables*.
    """

    # -- data helpers --------------------------------------------------------

    def _filtered_rows() -> list[dict]:
        if st.de is None:
            return []
        df = st.de.expense_df.with_row_index("id")
        if st.filter_name:
            df = df.filter(
                pl.col("expense_name").str.contains(f"(?i){re.escape(st.filter_name)}")
            )
        if st.filter_category:
            pat = f"(?i){re.escape(st.filter_category)}"
            df = df.filter(
                pl.col("primary_category").str.contains(pat)
                | pl.col("secondary_category").str.contains(pat)
            )
        if st.filter_amount_min is not None:
            df = df.filter(pl.col("expense_amount") >= st.filter_amount_min)
        if st.filter_amount_max is not None:
            df = df.filter(pl.col("expense_amount") <= st.filter_amount_max)
        rows = _df_to_rows(df)
        for row in rows:
            d = row.get("expense_date", "")
            if isinstance(d, str) and len(d) >= 10:
                row["expense_date"] = int(d[8:10])
        return rows

    def refresh_table():
        expenses_table.rows = _filtered_rows()
        expenses_table.update()

    _refreshables["refresh_table"] = refresh_table

    # -- row operations ------------------------------------------------------

    def delete_row(row_id: int):
        if st.de is None:
            return
        df = st.de.expense_df.with_row_index("_idx")
        st.de.expense_df = df.filter(pl.col("_idx") != row_id).drop("_idx")
        st.de.expense_df.write_parquet(st.de.expense_df_path)
        st.de.update_all_summary_tables()
        refresh_table()
        ui.notify("Expense deleted", type="positive")

    def save_edit(row_id: int, updates: dict):
        if st.de is None:
            return
        df = st.de.expense_df.with_row_index("_idx")
        for col, val in updates.items():
            if col == "expense_date":
                val = date.fromisoformat(val) if isinstance(val, str) else val
            df = df.with_columns(
                pl.when(pl.col("_idx") == row_id)
                .then(pl.lit(val))
                .otherwise(pl.col(col))
                .alias(col)
            )
        st.de.expense_df = df.drop("_idx")
        st.de.expense_df.write_parquet(st.de.expense_df_path)
        refresh_table()
        ui.notify("Expense updated", type="positive")

    # -- dialogs -------------------------------------------------------------

    def open_edit_dialog(row: dict):
        row_id = int(row["id"])
        with ui.dialog() as dlg, ui.card().classes("w-96"):
            ui.label("Edit Expense").classes("text-lg font-bold mb-2")
            inp_name = ui.input("Name", value=row.get("expense_name", ""))
            inp_date = ui.input("Date (YYYY-MM-DD)", value=row.get("expense_date", ""))
            inp_amount = ui.input("Amount", value=str(row.get("expense_amount", 0)))
            inp_cur = ui.input("Currency", value=row.get("currency", "E"))
            inp_pri = ui.input(
                "Primary Category", value=row.get("primary_category", "")
            )
            inp_sec = ui.input(
                "Secondary Category", value=row.get("secondary_category", "")
            )

            def do_save():
                if not inp_amount.value:
                    ui.notify("Amount is required", type="warning")
                    return
                try:
                    amount = _safe_eval_expr(str(inp_amount.value))
                    save_edit(
                        row_id,
                        {
                            "expense_name": inp_name.value,
                            "expense_date": inp_date.value,
                            "expense_amount": amount,
                            "currency": inp_cur.value,
                            "expense_in_ref_currency": amount,
                            "primary_category": normalize_category_value(inp_pri.value),
                            "secondary_category": normalize_category_value(
                                inp_sec.value
                            ),
                        },
                    )
                    dlg.close()
                except Exception as exc:
                    ui.notify(str(exc), type="negative")

            with ui.row().classes("mt-2"):
                ui.button("Save", on_click=do_save)
                ui.button("Cancel", on_click=dlg.close).props("flat")
        dlg.open()

    def open_add_dialog():
        today = date.today()

        if st.de is not None:
            pri_cats = sorted(
                {v for v in st.de.expense_df["primary_category"].drop_nulls().to_list() if v}
            )
            sec_cats = sorted(
                {v for v in st.de.expense_df["secondary_category"].drop_nulls().to_list() if v}
            )
        else:
            pri_cats, sec_cats = [], []

        with ui.dialog() as dlg, ui.card().classes("w-80 items-center"):
            ui.label("Add Expense").classes("text-lg font-bold mb-2")
            inp_name = ui.input("Expense Name").classes("w-64")
            inp_day = ui.input("Day of Month", value=str(today.day)).classes("w-64")
            inp_amount = ui.input("Amount", value="").classes("w-64")
            inp_cur = ui.input("Currency", value="E").classes("w-64")
            inp_pri = ui.select(
                options=pri_cats,
                with_input=True,
                label="Primary Category",
                new_value_mode="add",
            ).classes("w-64")
            inp_sec = ui.select(
                options=sec_cats,
                with_input=True,
                label="Secondary Category (optional)",
                new_value_mode="add",
            ).classes("w-64")

            def on_name_blur():
                mapping = get_mapping(inp_name.value)
                if mapping:
                    pri = normalize_category_value(mapping["primary_category"])
                    sec = normalize_category_value(mapping["secondary_category"])
                    if pri and pri not in inp_pri.options:
                        inp_pri.options.append(pri)
                    if sec and sec not in inp_sec.options:
                        inp_sec.options.append(sec)
                    inp_pri.value = pri
                    inp_sec.value = sec
                    inp_pri.update()
                    inp_sec.update()
                    ui.notify(f"Auto-mapped to {pri}", type="info")

            inp_name.on("blur", on_name_blur)

            def do_add():
                if st.de is None:
                    ui.notify("No data loaded", type="negative")
                    return
                if not inp_name.value:
                    ui.notify("Expense name is required", type="warning")
                    return
                if not inp_day.value or not inp_amount.value:
                    ui.notify("Day and amount are required", type="warning")
                    return
                try:
                    st.de.add_row(
                        expense_name=inp_name.value,
                        expense_day=int(inp_day.value),
                        expense_amount=_safe_eval_expr(str(inp_amount.value)),
                        currency=inp_cur.value,
                        primary_category=inp_pri.value or None,
                        secondary_category=inp_sec.value or None,
                    )
                    refresh_table()
                    dlg.close()
                    ui.notify("Expense added", type="positive")
                except Exception as exc:
                    ui.notify(str(exc), type="negative")

            with ui.row().classes("mt-2"):
                ui.button("Add", on_click=do_add)
                ui.button("Cancel", on_click=dlg.close).props("flat")
        dlg.open()

    def confirm_delete(row: dict):
        name = row.get("expense_name", "")
        amount = row.get("expense_amount", "")
        with ui.dialog() as dlg, ui.card():
            ui.label(f'Delete "{name}" ({amount})?').classes("text-base")
            with ui.row().classes("mt-2"):
                ui.button(
                    "Delete",
                    color="negative",
                    on_click=lambda: (delete_row(int(row["id"])), dlg.close()),
                )
                ui.button("Cancel", on_click=dlg.close).props("flat")
        dlg.open()

    # ========================================================================
    # BUILD UI
    # ========================================================================

    with ui.tabs().classes("w-full") as exp_subtabs:
        ui.tab("Detailed expenses").props("no-caps").classes("text-xl")
        ui.tab("Summary").props("no-caps").classes("text-xl")
        ui.tab("Mappings expense-categories").props("no-caps").classes("text-xl")

    with ui.tab_panels(exp_subtabs, value="Detailed expenses").classes("w-full"):
        with ui.tab_panel("Detailed expenses"):
            with ui.row().classes("w-full items-end gap-4 mb-4"):
                ui.input(
                    "Search name",
                    on_change=lambda e: (
                        setattr(st, "filter_name", e.value or ""),
                        refresh_table(),
                    ),
                ).classes("w-48")
                ui.input(
                    "Filter category",
                    on_change=lambda e: (
                        setattr(st, "filter_category", e.value or ""),
                        refresh_table(),
                    ),
                ).classes("w-48")
                ui.number(
                    "Min amount",
                    on_change=lambda e: (
                        setattr(st, "filter_amount_min", e.value),
                        refresh_table(),
                    ),
                ).classes("w-32")
                ui.number(
                    "Max amount",
                    on_change=lambda e: (
                        setattr(st, "filter_amount_max", e.value),
                        refresh_table(),
                    ),
                ).classes("w-32")
                ui.button("Add Expense", icon="add", on_click=open_add_dialog)

            expenses_table = ui.table(
                columns=_EXPENSE_COLUMNS,
                rows=[],
                row_key="id",
                pagination={"rowsPerPage": 25},
            ).classes("w-full text-lg")

            expenses_table.add_slot(
                "body-cell-actions",
                """
                <q-td :props="props">
                    <q-btn flat dense icon="edit" color="primary"
                        @click="$parent.$emit('edit', props.row)" />
                    <q-btn flat dense icon="delete" color="negative"
                        @click="$parent.$emit('delete', props.row)" />
                </q-td>
                """,
            )
            expenses_table.on("edit", lambda e: open_edit_dialog(e.args))
            expenses_table.on("delete", lambda e: confirm_delete(e.args))

        # ===================== SUMMARY TAB ==================================
        with ui.tab_panel("Summary"):
            summary_kind = ui.toggle(["Primary", "Secondary"], value="Primary")

            @ui.refreshable
            def summary_content():
                if st.de is None:
                    return
                kind = (
                    "primary"
                    if summary_kind.value == "Primary"
                    else "secondary"
                )
                cat_col = f"{kind}_category"

                # -- monthly summary for selected month --
                monthly = st.de.create_expenses_summary_table(cat_col)
                ui.label(
                    f"Monthly \u2014 {_MONTH_NAMES[st.month]} {st.year}"
                ).classes("text-lg font-bold mt-4")
                if monthly.height > 0:
                    cols = [
                        {
                            "name": c,
                            "label": c.replace("_", " ").title(),
                            "field": c,
                            "align": "left" if i == 0 else "right",
                            "sortable": True,
                        }
                        for i, c in enumerate(monthly.columns)
                    ]
                    with ui.row().classes("w-full items-start gap-8"):
                        with ui.column().classes("flex-1"):
                            ui.table(
                                columns=cols, rows=_df_to_rows(monthly), row_key="id"
                            ).classes("w-full text-lg")
                        with ui.column().classes("flex-1"):
                            render_monthly_expenses_pie(st.de, kind)
                else:
                    ui.label("No data for this month.").classes("text-gray-500")

                # -- cumulative year summary (if exists) --
                fn = (
                    PRIMARIES_FILENAME
                    if kind == "primary"
                    else SECONDARIES_FILENAME
                )
                path = get_year_summary_path(st.year, fn)
                if path.exists():
                    ui.label(f"Cumulative \u2014 {st.year}").classes(
                        "text-lg font-bold mt-6"
                    )
                    cum = pl.read_parquet(str(path))

                    def _col_label(c: str) -> str:
                        if "_" in c:
                            return c.replace("_", " ").title()
                        # Convert "YYYY-MM" to month name
                        parts = c.split("-")
                        if len(parts) == 2 and parts[1].isdigit():
                            m = int(parts[1])
                            if 1 <= m <= 12:
                                return calendar.month_name[m]
                        return c

                    cols = [
                        {
                            "name": c,
                            "label": _col_label(c),
                            "field": c,
                            "align": "left" if i == 0 else "right",
                            "sortable": True,
                        }
                        for i, c in enumerate(cum.columns)
                    ]
                    with ui.row().classes("w-full items-start gap-8"):
                        with ui.column().classes("flex-1"):
                            ui.table(
                                columns=cols, rows=_df_to_rows(cum), row_key="id"
                            ).classes("w-full text-lg")
                        with ui.column().classes("flex-1"):
                            render_cumulative_expenses_pie(st.year, kind)

                    # -- bar chart: compare up to 3 months --
                    ui.label("Monthly Comparison Chart").classes(
                        "text-lg font-bold mt-6 mb-2"
                    )
                    # Determine available months from the parquet columns
                    available_months = {
                        int(c.split("-")[1]): _MONTH_NAMES[int(c.split("-")[1])]
                        for c in cum.columns
                        if "-" in c and c.split("-")[1].isdigit()
                    }
                    # Default: select the current month (if available)
                    default_sel = (
                        [st.month] if st.month in available_months else
                        list(available_months.keys())[:1]
                    )

                    chart_months_select = ui.select(
                        options=available_months,
                        value=default_sel,
                        label="Months to compare (max 3)",
                        multiple=True,
                    ).classes("w-72 mb-2").props('use-chips')

                    chart_container = ui.column().classes("w-full")

                    def _render_chart():
                        chart_container.clear()
                        selected = chart_months_select.value or []
                        sel = sorted(selected)[:3]
                        with chart_container:
                            render_monthly_expenses_chart(
                                year=st.year,
                                months=sel,
                                kind=kind,
                            )

                    chart_months_select.on_value_change(lambda _: _render_chart())
                    _render_chart()

                    # -- line chart: compare categories over months --
                    ui.label("Compare Expenses").classes(
                        "text-lg font-bold mt-8 mb-2"
                    )
                    all_categories = [
                        c for c in cum[cat_col].to_list()
                        if c != "Total"
                    ]
                    default_cats = all_categories[:1]

                    cat_line_select = ui.select(
                        options=all_categories,
                        value=default_cats,
                        label="Categories to compare (max 3)",
                        multiple=True,
                    ).classes("w-80 mb-2").props("use-chips")

                    line_chart_container = ui.column().classes("w-full")

                    def _render_line_chart():
                        line_chart_container.clear()
                        selected_cats = cat_line_select.value or []
                        sel = selected_cats[:3]
                        with line_chart_container:
                            render_category_expenses_chart(
                                year=st.year,
                                categories=sel,
                                kind=kind,
                            )

                    cat_line_select.on_value_change(lambda _: _render_line_chart())
                    _render_line_chart()

            summary_content()
            _refreshables["summary_content"] = summary_content

            summary_kind.on_value_change(lambda _: summary_content.refresh())

            def update_summaries():
                if st.de is None:
                    return
                st.de.update_all_summary_tables()
                Cashflow(year=st.year).recompute()
                summary_content.refresh()
                _refreshables["cashflow_content"].refresh()
                ui.notify("Summary tables updated", type="positive")

            ui.button(
                "Regenerate Summaries",
                icon="refresh",
                on_click=update_summaries,
            ).classes("mt-4")

        # ===================== MAPPINGS TAB =================================
        with ui.tab_panel("Mappings expense-categories"):

            @ui.refreshable
            def mappings_content():
                mappings = get_all_mappings()

                with ui.row().classes("items-end gap-4 mb-4"):
                    new_name = ui.input("Expense Name").classes("w-48")
                    new_pri = ui.input("Primary Category").classes("w-48")
                    new_sec = ui.input("Secondary Category").classes("w-48")

                    def do_add_mapping():
                        if not new_name.value or not new_pri.value:
                            ui.notify(
                                "Name and primary category are required",
                                type="warning",
                            )
                            return
                        try:
                            config_add_mapping(
                                new_name.value,
                                new_pri.value,
                                new_sec.value or "",
                            )
                            ui.notify(
                                f'Mapping added for "{new_name.value}"',
                                type="positive",
                            )
                            mappings_content.refresh()
                        except ValueError as exc:
                            ui.notify(str(exc), type="negative")

                    ui.button(
                        "Add Mapping", icon="add", on_click=do_add_mapping
                    )

                if mappings:
                    mcols = [
                        {
                            "name": "expense_name",
                            "label": "Expense Name",
                            "field": "expense_name",
                            "align": "left",
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
                        {
                            "name": "actions",
                            "label": "",
                            "field": "actions",
                            "align": "center",
                        },
                    ]
                    mrows = [
                        {"id": i, "expense_name": name, **m}
                        for i, (name, m) in enumerate(mappings.items())
                    ]
                    mt = ui.table(
                        columns=mcols, rows=mrows, row_key="id"
                    ).classes("w-full text-lg")
                    mt.add_slot(
                        "body-cell-actions",
                        """
                        <q-td :props="props">
                            <q-btn flat dense icon="delete" color="negative"
                                @click="$parent.$emit('delete', props.row)" />
                        </q-td>
                        """,
                    )

                    def do_delete_mapping(e):
                        config_remove_mapping(e.args["expense_name"])
                        ui.notify("Mapping removed", type="positive")
                        mappings_content.refresh()

                    mt.on("delete", do_delete_mapping)
                else:
                    ui.label("No mappings configured yet.").classes(
                        "text-gray-500"
                    )

            mappings_content()

    exp_subtabs.on_value_change(
        lambda e: summary_content.refresh() if e.value == "Summary" else None
    )
