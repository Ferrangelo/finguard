"""Reusable month-columned HTML table builders."""

from __future__ import annotations

import polars as pl
from nicegui import ui

from finguard.df_operations import _INVESTMENT_CATEGORIES, InvestmentHoldings
from finguard.ui_helpers import _safe_eval_expr


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

                                def _make_edit_asset(
                                    _inv=inv,
                                    _asset=asset,
                                    _cat=cat,
                                    _link=link,
                                    _refresh=refresh_fn,
                                ):
                                    def open_dlg():
                                        with (
                                            ui.dialog() as dlg,
                                            ui.card().classes("w-96"),
                                        ):
                                            ui.label(f"Edit {_asset}").classes(
                                                "text-sm font-semibold mb-2"
                                            )
                                            inp_name = ui.input(
                                                "Name", value=_asset
                                            ).classes("w-full")
                                            inp_cat = ui.select(
                                                options=_INVESTMENT_CATEGORIES,
                                                label="Category",
                                                value=_cat,
                                            ).classes("w-full")
                                            inp_url = ui.input(
                                                "Link URL", value=_link
                                            ).classes("w-full")

                                            def save_changes():
                                                new_name = inp_name.value.strip()
                                                new_cat = inp_cat.value
                                                new_link = inp_url.value.strip()
                                                if not new_name:
                                                    ui.notify(
                                                        "Name cannot be empty",
                                                        type="warning",
                                                    )
                                                    return
                                                try:
                                                    if new_name != _asset:
                                                        _inv.rename_asset(
                                                            _asset, new_name
                                                        )
                                                    if new_cat != _cat:
                                                        _inv.set_category(
                                                            new_name, new_cat
                                                        )
                                                    if new_link != _link:
                                                        _inv.set_link(
                                                            new_name, new_link
                                                        )
                                                except ValueError as exc:
                                                    ui.notify(
                                                        str(exc), type="negative"
                                                    )
                                                    return
                                                dlg.close()
                                                if _refresh:
                                                    _refresh()

                                            with ui.row().classes("mt-2"):
                                                ui.button(
                                                    "Save", on_click=save_changes
                                                )
                                                ui.button(
                                                    "Cancel", on_click=dlg.close
                                                ).props("flat")
                                        dlg.open()

                                    return open_dlg

                                ui.button(
                                    icon="edit",
                                    on_click=_make_edit_asset(),
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
                                                _safe_eval_expr(str(e.sender.value))
                                                if e.sender.value not in (None, "")
                                                else 0.0
                                            )
                                        except (ValueError, TypeError, ZeroDivisionError, SyntaxError):
                                            return
                                        e.sender.value = str(v) if v != 0.0 else ""
                                        e.sender.update()
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
                                        'dense borderless'
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
    rename_fn=None,
    set_category_fn=None,
    categories: list[str] | None = None,
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
                        with ui.row().classes("items-center gap-1 flex-nowrap"):
                            ui.label(row_name)

                            if rename_fn is not None:

                                def _make_edit_name(
                                    _rename_fn=rename_fn,
                                    _name=row_name,
                                    _type_col=type_col,
                                    _cur_cat=row_dict.get(type_col, "") if type_col else None,
                                    _set_category_fn=set_category_fn,
                                    _categories=categories,
                                    _refresh=refresh_fn,
                                    _on_cell_change=on_cell_change,
                                ):
                                    def open_dlg():
                                        with (
                                            ui.dialog() as dlg,
                                            ui.card().classes("w-96"),
                                        ):
                                            ui.label(f"Edit {_name}").classes(
                                                "text-sm font-semibold mb-2"
                                            )
                                            inp_name = ui.input(
                                                "Name", value=_name
                                            ).classes("w-full")
                                            inp_cat = None
                                            if (
                                                _set_category_fn is not None
                                                and _categories is not None
                                            ):
                                                inp_cat = ui.select(
                                                    options=_categories,
                                                    label="Category",
                                                    value=_cur_cat,
                                                ).classes("w-full")

                                            def save_changes():
                                                new_name = inp_name.value.strip()
                                                if not new_name:
                                                    ui.notify(
                                                        "Name cannot be empty",
                                                        type="warning",
                                                    )
                                                    return
                                                try:
                                                    if new_name != _name:
                                                        _rename_fn(_name, new_name)
                                                    if (
                                                        inp_cat is not None
                                                        and inp_cat.value != _cur_cat
                                                    ):
                                                        _set_category_fn(
                                                            new_name, inp_cat.value
                                                        )
                                                except ValueError as exc:
                                                    ui.notify(
                                                        str(exc), type="negative"
                                                    )
                                                    return
                                                dlg.close()
                                                if _refresh:
                                                    _refresh()
                                                if _on_cell_change:
                                                    _on_cell_change()

                                            with ui.row().classes("mt-2"):
                                                ui.button(
                                                    "Save", on_click=save_changes
                                                )
                                                ui.button(
                                                    "Cancel", on_click=dlg.close
                                                ).props("flat")
                                        dlg.open()

                                    return open_dlg

                                ui.button(
                                    icon="edit",
                                    on_click=_make_edit_name(),
                                ).props("flat dense").classes("text-gray-400 ml-1")
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
                                            _safe_eval_expr(str(e.sender.value))
                                            if e.sender.value not in (None, "")
                                            else 0.0
                                        )
                                    except (ValueError, TypeError, ZeroDivisionError, SyntaxError):
                                        return
                                    e.sender.value = str(v) if v != 0.0 else ""
                                    e.sender.update()
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
                                    'dense borderless'
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
