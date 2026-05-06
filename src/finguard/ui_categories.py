"""Categories management tab for Finguard.

Lets the user manually add or remove primary/secondary categories that
appear in the expense-entry dropdown menus.

Rules
-----
* **Add**: the category is written to ``known_categories.json``; it will
  appear in every dropdown immediately.
* **Delete**: allowed only when the category's cumulative total across
  every year-summary parquet file is **0.0**.  If the category has any
  recorded expenses the delete button is disabled and an error message
  is shown as a safety net.  When deletion is confirmed the category is
  removed from both ``known_categories.json`` and from any
  ``primaries.parquet`` / ``secondaries.parquet`` files that contain it.
"""

from __future__ import annotations

from nicegui import ui

from finguard.config import (
    add_known_category as config_add_known_category,
)
from finguard.config import (
    get_known_categories,
)
from finguard.config import (
    remove_known_category as config_remove_known_category,
)
from finguard.df_operations import (
    get_category_totals_across_all_years,
    normalize_category_value,
    remove_category_from_all_summaries,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TABLE_COLS = [
    {
        "name": "name",
        "label": "Category",
        "field": "name",
        "align": "left",
        "sortable": True,
    },
    {
        "name": "total",
        "label": "Total (ref €)",
        "field": "total",
        "align": "right",
        "sortable": True,
    },
    {
        "name": "actions",
        "label": "",
        "field": "actions",
        "align": "center",
        "style": "width: 60px",
    },
]

_DELETE_SLOT = """
<q-td :props="props">
    <q-btn
        flat dense icon="delete" color="negative"
        :disable="props.row.total !== 0"
        :title="props.row.total !== 0
            ? 'Cannot delete: category has existing expenses'
            : 'Delete category'"
        @click="$parent.$emit('delete_cat', props.row)"
    />
</q-td>
"""


def _build_rows(kind: str) -> list[dict]:
    """Merge known-config categories with those found in parquet summaries."""
    known_set = set(get_known_categories().get(kind, []))
    totals = get_category_totals_across_all_years(kind)
    all_names = known_set | set(totals.keys())
    return sorted(
        [
            {
                "id": name,
                "name": name,
                "total": round(totals.get(name, 0.0), 2),
            }
            for name in all_names
        ],
        key=lambda r: r["name"].lower(),
    )


# ---------------------------------------------------------------------------
# Tab builder
# ---------------------------------------------------------------------------


def build_categories_tab() -> None:
    """Render the Categories tab content (add/remove primary & secondary)."""

    @ui.refreshable
    def categories_content() -> None:
        with ui.row().classes("w-full gap-10 items-start"):
            for kind, label in [
                ("primary", "Primary"),
                ("secondary", "Secondary"),
            ]:
                with ui.column().classes("flex-1 min-w-80"):
                    ui.label(f"{label} Categories").classes("text-xl font-bold mb-2")

                    # ---- add form ------------------------------------------
                    with ui.row().classes("items-end gap-3 mb-4"):
                        new_cat = ui.input(f"New {label} Category").classes("w-52")

                        def _do_add(*, _kind: str = kind, _inp=new_cat) -> None:
                            val = _inp.value.strip()
                            if not val:
                                ui.notify(
                                    "Category name is required",
                                    type="warning",
                                )
                                return
                            normalized = normalize_category_value(val)
                            try:
                                config_add_known_category(normalized, _kind)
                                ui.notify(
                                    f'"{normalized}" added to {_kind} categories',
                                    type="positive",
                                )
                                _inp.value = ""
                                categories_content.refresh()
                            except ValueError as exc:
                                ui.notify(str(exc), type="negative")

                        ui.button("Add", icon="add", on_click=_do_add)

                    # ---- category table ------------------------------------
                    rows = _build_rows(kind)

                    if not rows:
                        ui.label("No categories yet.").classes("text-gray-500 italic")
                    else:
                        t = ui.table(
                            columns=_TABLE_COLS,
                            rows=rows,
                            row_key="id",
                        ).classes("w-full text-lg")

                        t.add_slot("body-cell-actions", _DELETE_SLOT)

                        def _do_delete(e, *, _kind: str = kind) -> None:
                            cat_name = e.args["name"]
                            total = float(e.args.get("total", 0))

                            # Server-side guard (mirrors the disabled button).
                            if total != 0:
                                ui.notify(
                                    f'Cannot delete "{cat_name}": it still has '
                                    f"{total:.2f} in existing expenses. "
                                    "Remove or re-categorise all linked expenses first.",
                                    type="negative",
                                )
                                return

                            try:
                                # Remove from config (ignore if not present).
                                try:
                                    config_remove_known_category(cat_name, _kind)
                                except KeyError:
                                    pass

                                # Remove from all summary parquets.
                                remove_category_from_all_summaries(cat_name, _kind)
                                ui.notify(f'"{cat_name}" removed', type="positive")
                                categories_content.refresh()
                            except Exception as exc:
                                ui.notify(str(exc), type="negative")

                        t.on("delete_cat", _do_delete)

    categories_content()
