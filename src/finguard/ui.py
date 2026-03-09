"""NiceGUI web interface for Finguard."""

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
    _INCOME_CATEGORIES,
    _INVESTMENT_CATEGORIES,
    _LIQUIDITY_CATEGORIES,
    Cashflow,
    CreditsDebts,
    DetailedExpenses,
    InvestmentHoldings,
    Liquidity,
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


def _build_investment_table(
    *,
    inv: InvestmentHoldings,
    df: pl.DataFrame,
    month_abbrs: list[str],
    editable: bool,
    set_fn,
    value_kwarg: str = "quantity",
    show_delete: bool,
    refresh_fn,
    on_cell_change=None,
) -> None:
    """Render a month-columned investment HTML table.

    Used for holdings (editable), prices (editable) and value (read-only).
    """
    with (
        ui.element("table")
        .classes("w-full border-collapse text-sm")
        .style("border-spacing:0")
    ):
        # Header
        with ui.element("thead"):
            with ui.element("tr"):
                for label, min_w in [("Asset", "160px"), ("Category", "110px")]:
                    with (
                        ui.element("th")
                        .classes("text-left px-2 py-1 border-b border-r")
                        .style(f"min-width:{min_w}")
                    ):
                        ui.label(label).classes("text-xs font-bold")
                for abbr in month_abbrs:
                    with (
                        ui.element("th")
                        .classes("text-right px-2 py-1 border-b border-r")
                        .style("min-width:72px")
                    ):
                        ui.label(abbr).classes("text-xs font-bold")
                if show_delete:
                    ui.element("th").classes("px-2 py-1 border-b").style(
                        "min-width:40px"
                    )

        # Body
        with ui.element("tbody"):
            for row_dict in df.to_dicts():
                asset = row_dict["asset_name"]
                cat = row_dict["category"]
                link = row_dict.get("link", "")

                with ui.element("tr"):
                    # Asset name cell
                    with ui.element("td").classes("px-2 py-1 border-r text-xs"):
                        with ui.row().classes("items-center gap-1 flex-nowrap"):
                            if link:
                                ui.link(asset, link, new_tab=True).classes(
                                    "text-xs text-blue-400 underline"
                                )
                            else:
                                ui.label(asset).classes("text-xs")

                            if editable:

                                def _make_edit_link(
                                    _inv=inv,
                                    _asset=asset,
                                    _link=link,
                                    _refresh=refresh_fn,
                                ):
                                    def open_dlg():
                                        with (
                                            ui.dialog() as dlg,
                                            ui.card().classes("w-96"),
                                        ):
                                            ui.label(f"Link for {_asset}").classes(
                                                "text-sm font-semibold mb-2"
                                            )
                                            inp_url = ui.input(
                                                "URL", value=_link
                                            ).classes("w-full")

                                            def save_link():
                                                _inv.set_link(
                                                    _asset,
                                                    inp_url.value.strip(),
                                                )
                                                dlg.close()
                                                if _refresh:
                                                    _refresh()

                                            with ui.row().classes("mt-2"):
                                                ui.button("Save", on_click=save_link)
                                                ui.button(
                                                    "Cancel", on_click=dlg.close
                                                ).props("flat")
                                        dlg.open()

                                    return open_dlg

                                ui.button(
                                    icon="link",
                                    on_click=_make_edit_link(),
                                ).props("flat dense").classes("text-gray-400 ml-1")

                    # Category cell
                    with ui.element("td").classes("px-2 py-1 border-r text-xs"):
                        ui.label(cat)

                    # Month cells
                    for m in range(1, 13):
                        col = f"{m:02d}"
                        val = row_dict[col]

                        with ui.element("td").classes("px-1 py-0 border-r text-right"):
                            if editable:

                                def _make_cell_handler(
                                    _set_fn=set_fn,
                                    _asset=asset,
                                    _m=m,
                                    _kwarg=value_kwarg,
                                    _on_cell_change=on_cell_change,
                                ):
                                    def handler(e):
                                        try:
                                            v = (
                                                float(e.sender.value)
                                                if e.sender.value not in (None, "")
                                                else 0.0
                                            )
                                        except (ValueError, TypeError):
                                            return
                                        _set_fn(
                                            asset_name=_asset,
                                            month=_m,
                                            **{_kwarg: v},
                                        )
                                        if _on_cell_change:
                                            _on_cell_change()

                                    return handler

                                inp = (
                                    ui.input(
                                        value=str(val) if val != 0.0 else "",
                                    )
                                    .classes("w-20")
                                    .props(
                                        'type="number" step="any" dense borderless'
                                        ' input-class="text-right text-xs"'
                                    )
                                )
                                inp.on("blur", _make_cell_handler())
                            else:
                                # Read-only display
                                txt = f"{val:,.2f}" if val and val != 0.0 else ""
                                ui.label(txt).classes("text-xs")

                    # Delete button
                    if show_delete:
                        with ui.element("td").classes("px-1 py-0 text-center"):

                            def _make_delete_handler(
                                _inv=inv, _asset=asset, _refresh=refresh_fn
                            ):
                                def handler():
                                    _inv.remove_asset(_asset)
                                    if _refresh:
                                        _refresh()
                                    ui.notify(
                                        f"Asset '{_asset}' removed",
                                        type="positive",
                                    )

                                return handler

                            ui.button(
                                icon="delete",
                                on_click=_make_delete_handler(),
                                color="negative",
                            ).props("flat dense")

            # Totals row for read-only tables
            if not editable:
                with ui.element("tr").classes("border-t-2"):
                    with ui.element("td").classes(
                        "px-2 py-1 border-r text-xs font-bold"
                    ):
                        ui.label("Total")
                    with ui.element("td").classes("px-2 py-1 border-r"):
                        pass
                    for m in range(1, 13):
                        col = f"{m:02d}"
                        total = df[col].sum()
                        with ui.element("td").classes("px-1 py-0 border-r text-right"):
                            txt = f"{total:,.2f}" if total else ""
                            ui.label(txt).classes("text-xs font-bold")


def _build_simple_value_table(
    *,
    df: pl.DataFrame,
    name_col: str,
    type_col: str | None,
    month_abbrs: list[str],
    set_fn,
    remove_fn,
    refresh_fn,
    on_cell_change=None,
) -> None:
    """Render an editable month-columned HTML table for Liquidity / CreditsDebts.

    Columns: name, type/category (optional), currency, 12 month cells, delete button.
    """
    with (
        ui.element("table")
        .classes("w-full border-collapse text-sm")
        .style("border-spacing:0")
    ):
        # Header
        with ui.element("thead"):
            with ui.element("tr"):
                header_cols = [("Name", "160px")]
                if type_col is not None:
                    header_cols.append((type_col.replace("_", " ").title(), "110px"))
                header_cols.append(("Cur", "50px"))
                for label, min_w in header_cols:
                    with (
                        ui.element("th")
                        .classes("text-left px-2 py-1 border-b border-r")
                        .style(f"min-width:{min_w}")
                    ):
                        ui.label(label).classes("text-xs font-bold")
                for abbr in month_abbrs:
                    with (
                        ui.element("th")
                        .classes("text-right px-2 py-1 border-b border-r")
                        .style("min-width:72px")
                    ):
                        ui.label(abbr).classes("text-xs font-bold")
                ui.element("th").classes("px-2 py-1 border-b").style("min-width:40px")

        # Body
        with ui.element("tbody"):
            for row_dict in df.to_dicts():
                row_name = row_dict[name_col]
                row_cur = row_dict.get("currency", "E")

                with ui.element("tr"):
                    with ui.element("td").classes("px-2 py-1 border-r text-xs"):
                        ui.label(row_name)
                    if type_col is not None:
                        with ui.element("td").classes("px-2 py-1 border-r text-xs"):
                            ui.label(row_dict[type_col])
                    with ui.element("td").classes(
                        "px-2 py-1 border-r text-xs text-center"
                    ):
                        ui.label(row_cur)

                    # Month cells (editable)
                    for m in range(1, 13):
                        col = f"{m:02d}"
                        val = row_dict[col]

                        with ui.element("td").classes("px-1 py-0 border-r text-right"):

                            def _make_handler(
                                _set_fn=set_fn,
                                _name=row_name,
                                _m=m,
                                _on_cell_change=on_cell_change,
                            ):
                                def handler(e):
                                    try:
                                        v = (
                                            float(e.sender.value)
                                            if e.sender.value not in (None, "")
                                            else 0.0
                                        )
                                    except (ValueError, TypeError):
                                        return
                                    _set_fn(_name, month=_m, value=v)
                                    if _on_cell_change:
                                        _on_cell_change()

                                return handler

                            inp = (
                                ui.input(
                                    value=str(val) if val != 0.0 else "",
                                )
                                .classes("w-20")
                                .props(
                                    'type="number" step="any" dense borderless'
                                    ' input-class="text-right text-xs"'
                                )
                            )
                            inp.on("blur", _make_handler())

                    # Delete button
                    with ui.element("td").classes("px-1 py-0 text-center"):

                        def _make_delete(
                            _remove_fn=remove_fn,
                            _name=row_name,
                            _refresh=refresh_fn,
                            _on_cell_change=on_cell_change,
                        ):
                            def handler():
                                _remove_fn(_name)
                                if _refresh:
                                    _refresh()
                                if _on_cell_change:
                                    _on_cell_change()
                                ui.notify(f"'{_name}' removed", type="positive")

                            return handler

                        ui.button(
                            icon="delete",
                            on_click=_make_delete(),
                            color="negative",
                        ).props("flat dense")

            # Totals row
            with ui.element("tr").classes("border-t-2"):
                with ui.element("td").classes("px-2 py-1 border-r text-xs font-bold"):
                    ui.label("Total")
                if type_col is not None:
                    with ui.element("td").classes("px-2 py-1 border-r"):
                        pass
                with ui.element("td").classes("px-2 py-1 border-r"):
                    pass
                for m in range(1, 13):
                    col = f"{m:02d}"
                    total = df[col].sum()
                    with ui.element("td").classes("px-1 py-0 border-r text-right"):
                        txt = f"{total:,.2f}" if total else ""
                        ui.label(txt).classes("text-xs font-bold")


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

    # Forward-reference holder for refreshable functions defined later.
    # This avoids Python 3.14 NameError on free variables in closures.
    _refreshables: dict = {}

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
            inp_amount = ui.number("Amount", value=row.get("expense_amount", 0))
            inp_cur = ui.input("Currency", value=row.get("currency", "E"))
            inp_pri = ui.input(
                "Primary Category", value=row.get("primary_category", "")
            )
            inp_sec = ui.input(
                "Secondary Category", value=row.get("secondary_category", "")
            )

            def do_save():
                if inp_amount.value is None:
                    ui.notify("Amount is required", type="warning")
                    return
                try:
                    save_edit(
                        row_id,
                        {
                            "expense_name": inp_name.value,
                            "expense_date": inp_date.value,
                            "expense_amount": float(inp_amount.value),
                            "currency": inp_cur.value,
                            "expense_in_ref_currency": float(inp_amount.value),
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
                    inp_pri.value = normalize_category_value(
                        mapping["primary_category"]
                    )
                    inp_sec.value = normalize_category_value(
                        mapping["secondary_category"]
                    )
                    inp_pri.update()
                    inp_sec.update()
                    ui.notify(f"Auto-mapped to {inp_pri.value}", type="info")

            inp_name.on("blur", on_name_blur)

            def do_add():
                if st.de is None:
                    ui.notify("No data loaded", type="negative")
                    return
                if not inp_name.value:
                    ui.notify("Expense name is required", type="warning")
                    return
                if inp_day.value is None or inp_amount.value is None:
                    ui.notify("Day and amount are required", type="warning")
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

    # -- year / month handlers -----------------------------------------------

    def on_year_change(e):
        st.year = e.value
        load_data()
        refresh_table()
        summary_content.refresh()
        cashflow_content.refresh()
        investment_content.refresh()
        liquidity_content.refresh()
        credits_debts_content.refresh()
        if "total_networth_content" in _refreshables:
            _refreshables["total_networth_content"].refresh()

    def on_month_change(e):
        st.month = e.value
        load_data()
        refresh_table()
        summary_content.refresh()
        investment_content.refresh()
        liquidity_content.refresh()
        credits_debts_content.refresh()
        if "total_networth_content" in _refreshables:
            _refreshables["total_networth_content"].refresh()

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
        ui.tab("Expenses").props("no-caps")
        # ui.tab("Summary").props("no-caps")
        ui.tab("Cashflow").props("no-caps")
        ui.tab("NetWorth").props("no-caps")
        # ui.tab("Mappings").props("no-caps")

    with ui.tab_panels(tabs, value="Expenses").classes("w-full"):
        # ===================== EXPENSES TAB =================================
        with ui.tab_panel("Expenses"):
            with ui.tabs().classes("w-full") as exp_subtabs:
                ui.tab("Detailed expenses").props("no-caps")
                ui.tab("Summary").props("no-caps")
                ui.tab("Mappings expense-categories").props("no-caps")
                # Future subtabs for different views/filters could go here

            with ui.tab_panels(exp_subtabs, value="Detailed expenses").classes(
                "w-full"
            ):
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
                            ui.table(
                                columns=cols, rows=_df_to_rows(monthly), row_key="id"
                            ).classes("w-full")
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
                            cols = [
                                {
                                    "name": c,
                                    "label": c.replace("_", " ").title()
                                    if "_" in c
                                    else c,
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
                        Cashflow(year=st.year).recompute()
                        summary_content.refresh()
                        cashflow_content.refresh()
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
                            ui.label("No mappings configured yet.").classes(
                                "text-gray-500"
                            )

                    mappings_content()

            exp_subtabs.on_value_change(
                lambda e: summary_content.refresh() if e.value == "Summary" else None
            )

        # ===================== CASHFLOW TAB =================================
        with ui.tab_panel("Cashflow"):

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
                                                            float(e.value)
                                                            if e.value
                                                            else 0.0
                                                        )
                                                    except (ValueError, TypeError):
                                                        return
                                                    _cf.set_income(
                                                        month=_m,
                                                        category=_cat,
                                                        value=v,
                                                    )
                                                    cashflow_content.refresh()

                                                return handler

                                            ui.number(
                                                value=val if val != 0.0 else None,
                                                on_change=_make_handler(),
                                                format="%.2f",
                                            ).classes("w-20").props(
                                                "dense borderless hide-bottom-space"
                                                ' input-class="text-right text-xs"'
                                                " :hide-spin-buttons=true"
                                            )

            cashflow_content()

        # ===================== NETWORTH TAB =================================
        with ui.tab_panel("NetWorth"):
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
                                refresh_fn=liquidity_content.refresh,
                                on_cell_change=lambda: _refreshables[
                                    "total_networth_content"
                                ].refresh(),
                            )

                    liquidity_content()

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
                                refresh_fn=credits_debts_content.refresh,
                                on_cell_change=lambda: _refreshables[
                                    "total_networth_content"
                                ].refresh(),
                            )

                    credits_debts_content()

                with ui.tab_panel("Total NetWorth"):

                    @ui.refreshable
                    def _total_networth_content():
                        inv = InvestmentHoldings(year=st.year)
                        liq = Liquidity(year=st.year)
                        cd = CreditsDebts(year=st.year)
                        month_abbrs = [calendar.month_abbr[m] for m in range(1, 13)]
                        mcols = [f"{m:02d}" for m in range(1, 13)]

                        # Compute investment totals per month
                        inv_val = inv.df_value
                        inv_totals = [
                            inv_val[c].sum() if inv_val.height else 0.0 for c in mcols
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

                        ui.label(f"Net Worth \u2014 {st.year}").classes(
                            "text-lg font-bold mt-2 mb-4"
                        )

                        rows_data = [
                            ("Investments", inv_totals),
                            ("Liquidity", liq_totals),
                            ("Credits/Debts", cd_totals),
                            ("Net Worth", net_totals),
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
                                                txt = f"{v:,.2f}" if v else ""
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

    # -- refresh when switching tabs ----------------------------------------
    def _on_tab_change(e):
        if e.value == "Expenses":
            summary_content.refresh()
        elif e.value == "Cashflow":
            cashflow_content.refresh()
        elif e.value == "NetWorth":
            investment_content.refresh()
            liquidity_content.refresh()
            credits_debts_content.refresh()
            _refreshables["total_networth_content"].refresh()

    tabs.on_value_change(_on_tab_change)

    # -- initial data load ---------------------------------------------------
    load_data()
    refresh_table()
    summary_content.refresh()


def main():
    """Entry point for the ``finguard-ui`` command."""
    ui.run(title="Finguard", port=8080, reload=False)
