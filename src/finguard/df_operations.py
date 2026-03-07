from datetime import date
from pathlib import Path
from typing import Literal, Optional

import polars as pl

from finguard.config import get_mapping
from finguard.paths import (
    PRIMARIES_FILENAME,
    SECONDARIES_FILENAME,
    get_monthly_parquet_path,
    get_year_summary_path,
    month_from_parquet_path,
    year_from_parquet_path,
)

# Special-case category name mappings (lowercase key → canonical display value).
_SPECIAL_CASES: dict[str, str] = {
    "tv": "TV",
    "otherexpenses": "OtherExpenses",
    "mrstuff": "MrStuff",
    "techdonations": "TechDonations",
    "othergroceries": "OtherGroceries",
    "condofee": "CondoFee",
    "takeaway": "TakeAway",
    "mrclothing": "MrClothing",
    "mrbooks": "MrBooks",
    "mrleisure": "MrLeisure",
    "mrlearning": "MrLearning",
    "otherleisure": "OtherLeisure",
    "otherfees": "OtherFees",
    "unatantum": "Unatantum",
    "charityenv": "CharityEnv",
    "charityhum": "CharityHum",
    "patreon-like": "Patreon-Like",
}


def normalize_category_value(value: str) -> str:
    """Return the canonical casing for a category string."""
    lower = value.lower()
    if lower in _SPECIAL_CASES:
        return _SPECIAL_CASES[lower]
    return lower[0].upper() + lower[1:] if lower else lower


# Canonical display order for primary categories.
_PRIMARY_CATEGORY_ORDER = [
    "Housing",
    "Health",
    "Groceries",
    "Transport",
    "Lunchbreak",
    "Out",
    "Travel",
    "Baby",
    "Clothing",
    "Leisure",
    "Gifts",
    "Fees",
    "OtherExpenses",
    "Missioni",
]

# Schema for the detailed-expenses dataframes.  Used when creating an empty
# dataframe for a month that has no data yet.
_SCHEMA = {
    "expense_name": pl.Utf8,
    "expense_date": pl.Int64,
    "expense_amount": pl.Float64,
    "currency": pl.Utf8,
    "expense_in_ref_currency": pl.Float64,
    "primary_category": pl.Utf8,
    "secondary_category": pl.Utf8,
}


class DetailedExpenses:
    """Class to manage a monthly detailed-expenses parquet file.

    The file is located at the standard XDG data path:
    ``$XDG_DATA_HOME/finguard/dbs/<year>/MM_detailed_expenses.parquet``

    Parameters
    ----------
    year:
        Calendar year (e.g. 2026).  Mutually exclusive with *expense_df_path*.
    month:
        Month number (1–12).  Required when *year* is given.
    expense_df_path:
        Explicit path to an existing parquet file.  When provided, *year*
        and *month* are inferred from the path.  Mutually exclusive with
        *year*/*month*.
    """

    def __init__(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
        expense_df_path: Optional[str] = None,
    ):
        if expense_df_path is not None and (year is not None or month is not None):
            raise ValueError(
                "Provide either 'expense_df_path' or 'year'/'month', not both."
            )

        if expense_df_path is not None:
            self.expense_df_path = str(expense_df_path)
            self.year = year_from_parquet_path(self.expense_df_path)
            self.month = month_from_parquet_path(self.expense_df_path)
        elif year is not None and month is not None:
            path = get_monthly_parquet_path(year, month)
            self.expense_df_path = str(path)
            self.year = year
            self.month = month
        else:
            raise ValueError(
                "You must provide either 'year' and 'month', or 'expense_df_path'."
            )

        if Path(self.expense_df_path).exists():
            self.expense_df = pl.read_parquet(self.expense_df_path)
        else:
            self.expense_df = pl.DataFrame(schema=_SCHEMA)

    # ------------------------------------------------------------------
    # Row operations
    # ------------------------------------------------------------------

    def add_row(
        self,
        expense_name: str,
        expense_day: int,
        expense_amount: float,
        primary_category: Optional[str] = None,
        currency: str = "E",
        secondary_category: Optional[str] = None,
    ):
        """Append an expense row and save the updated dataframe.

        If *primary_category* or *secondary_category* are not provided, the
        method tries to resolve them from the category-mappings config file.
        A ``ValueError`` is raised when *primary_category* cannot be resolved.
        """
        if primary_category is None or secondary_category is None:
            mapping = get_mapping(expense_name)
            if mapping is not None:
                if primary_category is None:
                    primary_category = mapping["primary_category"]
                if secondary_category is None:
                    secondary_category = mapping["secondary_category"]
            else:
                if primary_category is None:
                    raise ValueError(
                        f"No category mapping found for '{expense_name}' and "
                        "no primary_category was provided. Either add a mapping "
                        "via config.add_mapping() or pass primary_category explicitly."
                    )
                if secondary_category is None:
                    secondary_category = ""

        expense_in_ref_currency: float = self._convert_in_ref_currency(
            amount=expense_amount
        )

        new_row = pl.DataFrame(
            {
                "expense_name": [expense_name],
                "expense_date": [date(self.year, self.month, expense_day)],
                "expense_amount": [expense_amount],
                "currency": [currency],
                "expense_in_ref_currency": [expense_in_ref_currency],
                "primary_category": [normalize_category_value(primary_category)],
                "secondary_category": [normalize_category_value(secondary_category)],
            }
        )
        self.expense_df = pl.concat([self.expense_df, new_row], how="diagonal")
        self.expense_df.write_parquet(self.expense_df_path)

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------
    #
    def create_expenses_summary_table(self, category_col: str) -> pl.DataFrame:
        """Return a summary grouped by the specified category column."""
        if category_col not in {"primary_category", "secondary_category"}:
            raise ValueError(
                f"category_col must be 'primary_category' or 'secondary_category', "
                f"got '{category_col}'"
            )

        return self.expense_df.group_by(category_col).agg(
            pl.col("expense_in_ref_currency")
            .sum()
            .alias("total_expense_in_ref_currency")
        )

    # ------------------------------------------------------------------
    # Cumulative summary tables
    # ------------------------------------------------------------------

    def _month_label(self) -> str:
        """Return the current month as a ``YYYY-MM`` string, e.g. ``2026-03``."""
        return f"{self.year}-{self.month:02d}"

    def _update_summary_table(
        self, kind: Literal["primary", "secondary"]
    ) -> pl.DataFrame:
        """Core logic for updating a cumulative wide summary table.

        Loads (or initialises) the summary parquet for *kind*, adds/updates
        the column for the current month. If new categories are added they are
        backfilled with ``0.0``. Then save the result.

        Parameters
        ----------
        kind:
            ``"primary"`` → groups by ``primary_category``,
            ``"secondary"`` → groups by ``secondary_category``.

        Returns
        -------
        pl.DataFrame
            The updated wide summary table.
        """
        category_col = f"{kind}_category"
        filename = PRIMARIES_FILENAME if kind == "primary" else SECONDARIES_FILENAME
        summary_path = get_year_summary_path(self.year, filename)
        month_label = self._month_label()

        # current month totals (long format)
        monthly = self.expense_df.group_by(category_col).agg(
            pl.col("expense_in_ref_currency").sum().alias(month_label)
        )

        # load or initialise the summary table
        if summary_path.exists():
            summary = pl.read_parquet(str(summary_path))

            # Drop the month column if it already exists so we recompute it.
            if month_label in summary.columns:
                summary = summary.drop(month_label)

            # Outer join: align by category key, bring in new month column.
            summary = summary.join(monthly, on=category_col, how="full", coalesce=True)
        else:
            summary = monthly

        # fill all month columns with 0.0 where null
        month_cols = [c for c in summary.columns if c != category_col]
        summary = summary.with_columns([pl.col(c).fill_null(0.0) for c in month_cols])

        # sort columns: category first, then months chronologically
        ordered_cols = [category_col] + sorted(month_cols)  # YYYY-MM
        summary = summary.select(ordered_cols)

        # Add totals row (strip any pre-existing Total rows first)
        sorted_month_cols = sorted(month_cols)
        summary = summary.filter(pl.col(category_col) != "Total")
        totals = ["Total"] + [summary[c].sum() for c in sorted_month_cols]
        summary = pl.concat([
            summary,
            pl.DataFrame({col: [val] for col, val in zip(ordered_cols, totals)})
        ], how="diagonal")

        # sort rows by canonical category order (primary only)
        if kind == "primary":
            order_df = pl.DataFrame({
                category_col: _PRIMARY_CATEGORY_ORDER + ["Total"],
                "_order": list(range(len(_PRIMARY_CATEGORY_ORDER) + 1)),
            })
            summary = (
                summary
                .join(order_df, on=category_col, how="left")
                .sort("_order", nulls_last=True)
                .drop("_order")
            )

        summary.write_parquet(str(summary_path))
        return summary

    def update_primaries_summary_table(self) -> pl.DataFrame:
        """Update and save the cumulative primaries summary table.

        Adds (or updates) a ``YYYY-MM`` column for the current month in
        ``<summary_dir>/primaries.parquet``.  Missing values are filled with
        ``0.0``.

        Returns
        -------
        pl.DataFrame
            Wide summary table: one row per primary category, one column per
            recorded month.
        """
        return self._update_summary_table("primary")

    def update_secondaries_summary_table(self) -> pl.DataFrame:
        """Update and save the cumulative secondaries summary table.

        Adds (or updates) a ``YYYY-MM`` column for the current month in
        ``<summary_dir>/secondaries.parquet``.  Missing values are filled with
        ``0.0``.

        Returns
        -------
        pl.DataFrame
            Wide summary table: one row per secondary category, one column per
            recorded month.
        """
        return self._update_summary_table("secondary")

    def update_all_summary_tables(self) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Update both summary tables in one call.

        Returns
        -------
        tuple[pl.DataFrame, pl.DataFrame]
            ``(primaries_summary, secondaries_summary)``
        """
        return (
            self.update_primaries_summary_table(),
            self.update_secondaries_summary_table(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _convert_in_ref_currency(self, amount: float) -> float:
        # In the future implement exchange rate retrieval and conversion here.
        # For now everything is in one currency.
        change = 1.0
        return amount * change
