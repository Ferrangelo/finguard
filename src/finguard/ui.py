"""NiceGUI web interface for Finguard."""

from __future__ import annotations

import calendar
import re
from datetime import date

import polars as pl
from nicegui import ui

from finguard.config import (
    add_mapping as config_add_mapping,
    get_all_mappings,
    get_mapping,
    remove_mapping as config_remove_mapping,
)
from finguard.df_operations import (
    DetailedExpenses,
    normalize_category_value,
)
from finguard.paths import (
    PRIMARIES_FILENAME,
    SECONDARIES_FILENAME,
    get_dbs_root,
    get_year_summary_path,
)

_MONTH_NAMES: dict[int, str] = {i: calendar.month_name[i] for i in range(1, 13)}

_EXPENSE_COLUMNS = [
    {"name": "expense_name", "label": "Name", "field": "expense_name", "align": "left", "sortable": True},
    {"name": "expense_date", "label": "Date", "field": "expense_date", "align": "left", "sortable": True},
    {"name": "expense_amount", "label": "Amount", "field": "expense_amount", "align": "right", "sortable": True},
    {"name": "currency", "label": "Cur", "field": "currency", "align": "center"},
    {"name": "expense_in_ref_currency", "label": "Ref Amount", "field": "expense_in_ref_currency", "align": "right", "sortable": True},
    {"name": "primary_category", "label": "Primary", "field": "primary_category", "align": "left", "sortable": True},
    {"name": "secondary_category", "label": "Secondary", "field": "secondary_category", "align": "left", "sortable": True},
    {"name": "actions", "label": "", "field": "actions", "align": "center"},
]


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
    return rows


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@ui.page("/")
def index():
    today = date.today()

    # -- mutable state shared across closures --------------------------------
    class State:
        year: int = today.year
        month: int = today.month
        de: DetailedExpenses | None = None
        filter_name: str = ""
        filter_category: str = ""
        filter_amount_min: float | None = None
        filter_amount_max: float | None = None

    st = State()

    # -- data helpers --------------------------------------------------------

    def load_data():
        st.de = DetailedExpenses(year=st.year, month=st.month)

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
        return _df_to_rows(df)

    def refresh_table():
        expenses_table.rows = _filtered_rows()
        expenses_table.update()

    # -- row operations ------------------------------------------------------

    def delete_row(row_id: int):
        if st.de is None:
            return
        df = st.de.expense_df.with_row_index("_idx")
        st.de.expense_df = df.filter(pl.col("_idx") != row_id).drop("_idx")
        st.de.expense_df.write_parquet(st.de.expense_df_path)
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
            inp_amount = ui.number("Amount", value=row.get("expense_amount", 0))
            inp_cur = ui.input("Currency", value=row.get("currency", "E"))
            inp_pri = ui.input("Primary Category", value=row.get("primary_category", ""))
            inp_sec = ui.input("Secondary Category", value=row.get("secondary_category", ""))

            def do_save():
                save_edit(row_id, {
                    "expense_name": inp_name.value,
                    "expense_date": inp_date.value,
                    "expense_amount": float(inp_amount.value),
                    "currency": inp_cur.value,
                    "expense_in_ref_currency": float(inp_amount.value),
                    "primary_category": normalize_category_value(inp_pri.value),
                    "secondary_category": normalize_category_value(inp_sec.value),
                })
                dlg.close()

            with ui.row().classes("mt-2"):
                ui.button("Save", on_click=do_save)
                ui.button("Cancel", on_click=dlg.close).props("flat")
        dlg.open()

    def open_add_dialog():
        with ui.dialog() as dlg, ui.card().classes("w-96"):
            ui.label("Add Expense").classes("text-lg font-bold mb-2")
            inp_name = ui.input("Expense Name")
            inp_day = ui.number("Day of Month", value=today.day, min=1, max=31)
            inp_amount = ui.number("Amount", value=0.0)
            inp_cur = ui.input("Currency", value="E")
            inp_pri = ui.input("Primary Category (optional if mapped)")
            inp_sec = ui.input("Secondary Category (optional)")

            def on_name_blur():
                mapping = get_mapping(inp_name.value)
                if mapping:
                    inp_pri.value = normalize_category_value(mapping["primary_category"])
                    inp_sec.value = normalize_category_value(mapping["secondary_category"])
                    inp_pri.update()
                    inp_sec.update()
                    ui.notify(f"Auto-mapped to {inp_pri.value}", type="info")

            inp_name.on("blur", on_name_blur)

            def do_add():
                if st.de is None:
                    return
                try:
                    st.de.add_row(
                        expense_name=inp_name.value,
                        expense_day=int(inp_day.value),
                        expense_amount=float(inp_amount.value),
                        currency=inp_cur.value,
                        primary_category=inp_pri.value or None,
                        secondary_category=inp_sec.value or None,
                    )
                    refresh_table()
                    dlg.close()
                    ui.notify("Expense added", type="positive")
                except ValueError as exc:
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

    # -- year / month handlers -----------------------------------------------

    def on_year_change(e):
        st.year = e.value
        load_data()
        refresh_table()

    def on_month_change(e):
        st.month = e.value
        load_data()
        refresh_table()

    # ========================================================================
    # BUILD PAGE
    # ========================================================================

    ui.dark_mode(True)

    # -- header --------------------------------------------------------------
    with ui.header().classes("items-center gap-4"):
        ui.icon("account_balance_wallet").classes("text-2xl")
        ui.label("Finguard").classes("text-xl font-bold")
        ui.select(
            options=_discover_years(),
            value=st.year,
            label="Year",
            on_change=on_year_change,
        ).classes("w-28")
        ui.select(
            options=_MONTH_NAMES,
            value=st.month,
            label="Month",
            on_change=on_month_change,
        ).classes("w-36")

    # -- tabs ----------------------------------------------------------------
    with ui.tabs().classes("w-full") as tabs:
        ui.tab("Expenses")
        ui.tab("Summary")
        ui.tab("Mappings")

    with ui.tab_panels(tabs, value="Expenses").classes("w-full"):

        # ===================== EXPENSES TAB =================================
        with ui.tab_panel("Expenses"):
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
            ).classes("w-full")

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
                kind = "primary" if summary_kind.value == "Primary" else "secondary"
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
                    ui.table(
                        columns=cols, rows=_df_to_rows(monthly), row_key="id"
                    ).classes("w-full")
                else:
                    ui.label("No data for this month.").classes("text-gray-500")

                # -- cumulative year summary (if exists) --
                fn = PRIMARIES_FILENAME if kind == "primary" else SECONDARIES_FILENAME
                path = get_year_summary_path(st.year, fn)
                if path.exists():
                    ui.label(f"Cumulative \u2014 {st.year}").classes(
                        "text-lg font-bold mt-6"
                    )
                    cum = pl.read_parquet(str(path))
                    cols = [
                        {
                            "name": c,
                            "label": c.replace("_", " ").title() if "_" in c else c,
                            "field": c,
                            "align": "left" if i == 0 else "right",
                            "sortable": True,
                        }
                        for i, c in enumerate(cum.columns)
                    ]
                    ui.table(
                        columns=cols, rows=_df_to_rows(cum), row_key="id"
                    ).classes("w-full")

            summary_content()

            summary_kind.on_value_change(lambda _: summary_content.refresh())

            def update_summaries():
                if st.de is None:
                    return
                st.de.update_all_summary_tables()
                summary_content.refresh()
                ui.notify("Summary tables updated", type="positive")

            ui.button(
                "Regenerate Summaries", icon="refresh", on_click=update_summaries
            ).classes("mt-4")

        # ===================== MAPPINGS TAB =================================
        with ui.tab_panel("Mappings"):

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
                                new_name.value, new_pri.value, new_sec.value or ""
                            )
                            ui.notify(
                                f'Mapping added for "{new_name.value}"',
                                type="positive",
                            )
                            mappings_content.refresh()
                        except ValueError as exc:
                            ui.notify(str(exc), type="negative")

                    ui.button("Add Mapping", icon="add", on_click=do_add_mapping)

                if mappings:
                    mcols = [
                        {"name": "expense_name", "label": "Expense Name", "field": "expense_name", "align": "left", "sortable": True},
                        {"name": "primary_category", "label": "Primary", "field": "primary_category", "align": "left", "sortable": True},
                        {"name": "secondary_category", "label": "Secondary", "field": "secondary_category", "align": "left", "sortable": True},
                        {"name": "actions", "label": "", "field": "actions", "align": "center"},
                    ]
                    mrows = [
                        {"id": i, "expense_name": name, **m}
                        for i, (name, m) in enumerate(mappings.items())
                    ]
                    mt = ui.table(
                        columns=mcols, rows=mrows, row_key="id"
                    ).classes("w-full")
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
                    ui.label("No mappings configured yet.").classes("text-gray-500")

            mappings_content()

    # -- refresh summary when switching to that tab --------------------------
    tabs.on_value_change(
        lambda e: summary_content.refresh() if e.value == "Summary" else None
    )

    # -- initial data load ---------------------------------------------------
    load_data()
    refresh_table()


def main():
    """Entry point for the ``finguard-ui`` command."""
    ui.run(title="Finguard", port=8080, reload=False)
