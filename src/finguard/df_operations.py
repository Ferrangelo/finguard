from datetime import date
from pathlib import Path
from typing import Literal, Optional

import polars as pl

from finguard.config import get_mapping
from finguard.paths import (
    CASHFLOW_FILENAME,
    CREDITS_DEBTS_FILENAME,
    INVESTMENTS_FILENAME,
    INVESTMENTS_PRICES_FILENAME,
    LIQUIDITY_FILENAME,
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


def resolve_category(value: str, existing: set[str]) -> str:
    """Match *value* case-insensitively against *existing* categories.

    If a match is found the existing spelling is returned; otherwise falls
    back to :func:`normalize_category_value`.
    """
    if not value:
        return value
    lookup = {c.lower(): c for c in existing}
    return lookup.get(value.lower(), normalize_category_value(value))


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
    "expense_date": pl.Date,
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
            # Ensure expense_date is Date (older files may store it as Int64).
            if (
                "expense_date" in self.expense_df.columns
                and self.expense_df["expense_date"].dtype != pl.Date
            ):
                self.expense_df = self.expense_df.with_columns(
                    pl.col("expense_date").cast(pl.Date)
                )
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
        self.update_all_summary_tables()

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
        summary = pl.concat(
            [
                summary,
                pl.DataFrame({col: [val] for col, val in zip(ordered_cols, totals)}),
            ],
            how="diagonal",
        )

        # sort rows by canonical category order (primary only)
        if kind == "primary":
            order_df = pl.DataFrame(
                {
                    category_col: _PRIMARY_CATEGORY_ORDER + ["Total"],
                    "_order": list(range(len(_PRIMARY_CATEGORY_ORDER) + 1)),
                }
            )
            summary = (
                summary.join(order_df, on=category_col, how="left")
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


# ======================================================================
# Cashflow
# ======================================================================

# Row labels for the income categories (user-editable values).
_INCOME_CATEGORIES = [
    "Salary",
    "Interests Bank account",
    "Dividendi e Cedole",
    "Other",
]

# Row labels for the derived (computed) categories.
_DERIVED_CATEGORIES = [
    "Income",
    "Spending",
    "Saving",
    "Saving %",
]

_ALL_CASHFLOW_CATEGORIES = _INCOME_CATEGORIES + _DERIVED_CATEGORIES

# Month column labels used in the wide cashflow table.
_MONTH_LABELS = [f"{m:02d}" for m in range(1, 13)]


class Cashflow:
    """Yearly cashflow dataframe.

    Layout (wide format)::

        category                | 01    | 02    | … | 12
        Salary               | …     | …     |   | …
        Interests Bank account  | …     | …     |   | …
        Dividendi e Cedole      | …     | …     |   | …
        Other                   | …     | …     |   | …
        Income                  | (sum) | (sum) |   | (sum)
        Spending                | (tot) | (tot) |   | (tot)
        Saving                  | I-S   | I-S   |   | I-S
        Saving %                | %     | %     |   | %

    Income rows are set manually via :meth:`set_income`.
    Derived rows are recomputed by :meth:`recompute`.

    Parameters
    ----------
    year:
        Calendar year (e.g. 2026).
    """

    def __init__(self, year: int):
        self.year = year
        self._path = get_year_summary_path(year, CASHFLOW_FILENAME)

        if self._path.exists():
            self.df = pl.read_parquet(str(self._path))
        else:
            self.df = pl.DataFrame(
                {"category": _ALL_CASHFLOW_CATEGORIES}
                | {m: [0.0] * len(_ALL_CASHFLOW_CATEGORIES) for m in _MONTH_LABELS}
            )

    # ------------------------------------------------------------------
    # Internal functions
    # ------------------------------------------------------------------

    def set_income(self, month: int, category: str, value: float) -> None:
        """Set an income-category value for a given month.

        Parameters
        ----------
        month:
            Month number (1-12).
        category:
            One of the income categories (e.g. ``"Salary"``).
        value:
            The amount.
        """
        if category not in _INCOME_CATEGORIES:
            raise ValueError(
                f"'{category}' is not a valid income category. "
                f"Choose from: {_INCOME_CATEGORIES}"
            )
        if not 1 <= month <= 12:
            raise ValueError(f"month must be between 1 and 12, got {month}")

        col = f"{month:02d}"
        mask = self.df["category"] == category
        self.df = self.df.with_columns(
            pl.when(mask).then(pl.lit(value)).otherwise(pl.col(col)).alias(col)
        )
        self.recompute()

    def recompute(self) -> None:
        """Recompute all derived rows from income values and primaries.parquet,
        then save."""
        primaries_path = get_year_summary_path(self.year, PRIMARIES_FILENAME)
        primaries: pl.DataFrame | None = None
        if primaries_path.exists():
            primaries = pl.read_parquet(str(primaries_path))

        for month in range(1, 13):
            col = f"{month:02d}"
            month_label = f"{self.year}-{month:02d}"

            # Income = sum of income categories
            income = sum(self._get_value(cat, col) for cat in _INCOME_CATEGORIES)
            self._set_value("Income", col, income)

            # Spending = "Total" row from primaries.parquet for this month
            spending = 0.0
            if primaries is not None and month_label in primaries.columns:
                total_rows = primaries.filter(pl.col("primary_category") == "Total")
                if total_rows.height > 0:
                    spending = total_rows[month_label][0]
            self._set_value("Spending", col, spending)

            saving = income - spending
            self._set_value("Saving", col, saving)

            # Saving percentage
            saving_pct = (100.0 * saving / income) if income != 0 else 0.0
            self._set_value("Saving %", col, saving_pct)

        self.save()

    def save(self) -> None:
        """Write the cashflow dataframe to disk."""
        self.df.write_parquet(str(self._path))

    # ------------------------------------------------------------------
    # Internal functions
    # ------------------------------------------------------------------

    def _get_value(self, category: str, col: str) -> float:
        row = self.df.filter(pl.col("category") == category)
        if row.height == 0:
            return 0.0
        return row[col][0]

    def _set_value(self, category: str, col: str, value: float) -> None:
        mask = self.df["category"] == category
        self.df = self.df.with_columns(
            pl.when(mask).then(pl.lit(value)).otherwise(pl.col(col)).alias(col)
        )


# ======================================================================
# InvestmentHoldings
# ======================================================================

_INVESTMENT_CATEGORIES = ["Stocks/ETF", "Commodities", "Bonds"]

# Schema columns (non-month)
_INV_META_COLS = ["asset_name", "category", "link"]


class InvestmentHoldings:
    """Yearly investment holdings dataframe.

    Layout (wide format)::

        asset_name | category    | 01  | 02  | … | 12
        VWCE       | Stocks/ETF  | 10  | 10  |   | 12
        Gold       | Commodities | 2   | 2   |   | 3

    Each monthly cell contains the *quantity* (number of units) owned.

    Parameters
    ----------
    year:
        Calendar year (e.g. 2026).
    """

    def __init__(self, year: int):
        self.year = year
        self._path = get_year_summary_path(year, INVESTMENTS_FILENAME)
        self._path_prices = get_year_summary_path(year, INVESTMENTS_PRICES_FILENAME)

        self._path_dict = {
            "holdings": get_year_summary_path(year, INVESTMENTS_FILENAME),
            "prices": get_year_summary_path(year, INVESTMENTS_PRICES_FILENAME),
        }

        for filetype, filepath in self._path_dict.items():
            if filepath.exists():
                df = pl.read_parquet(str(filepath))
                if "link" not in df.columns:
                    df = df.with_columns(pl.lit("").alias("link"))
            else:
                df = pl.DataFrame(
                    schema={
                        "asset_name": pl.Utf8,
                        "category": pl.Utf8,
                        "link": pl.Utf8,
                        **{f"{m:02d}": pl.Float64 for m in range(1, 13)},
                    }
                )

            if filetype == "prices":
                self.df_prices = df
            else:
                self.df = df

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_asset(self, asset_name: str, category: str, link: str = "") -> None:
        """Add a new asset row (all monthly quantities initialised to 0).

        Raises ``ValueError`` if the asset already exists or the category
        is invalid.
        """
        if category not in _INVESTMENT_CATEGORIES:
            raise ValueError(
                f"'{category}' is not a valid category. "
                f"Choose from: {_INVESTMENT_CATEGORIES}"
            )
        if asset_name in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{asset_name}' already exists.")

        new_row = pl.DataFrame(
            {
                "asset_name": [asset_name],
                "category": [category],
                "link": [link],
                **{f"{m:02d}": [0.0] for m in range(1, 13)},
            }
        )
        self.df = pl.concat([self.df, new_row], how="diagonal")
        self.df_prices = pl.concat([self.df_prices, new_row], how="diagonal")
        self.save()

    def remove_asset(self, asset_name: str) -> None:
        """Remove an asset row by name."""
        self.df = self.df.filter(pl.col("asset_name") != asset_name)
        self.df_prices = self.df_prices.filter(pl.col("asset_name") != asset_name)
        self.save()

    def rename_asset(self, old_name: str, new_name: str) -> None:
        """Rename an asset row."""
        if old_name not in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{old_name}' not found.")
        if new_name != old_name and new_name in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{new_name}' already exists.")
        mask = self.df["asset_name"] == old_name
        self.df = self.df.with_columns(
            pl.when(mask)
            .then(pl.lit(new_name))
            .otherwise(pl.col("asset_name"))
            .alias("asset_name")
        )
        self.df_prices = self.df_prices.with_columns(
            pl.when(self.df_prices["asset_name"] == old_name)
            .then(pl.lit(new_name))
            .otherwise(pl.col("asset_name"))
            .alias("asset_name")
        )
        self.save()

    def set_category(self, asset_name: str, category: str) -> None:
        """Update the category for an asset."""
        if asset_name not in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{asset_name}' not found.")
        if category not in _INVESTMENT_CATEGORIES:
            raise ValueError(
                f"'{category}' is not a valid category. "
                f"Choose from: {_INVESTMENT_CATEGORIES}"
            )
        mask = self.df["asset_name"] == asset_name
        self.df = self.df.with_columns(
            pl.when(mask)
            .then(pl.lit(category))
            .otherwise(pl.col("category"))
            .alias("category")
        )
        self.df_prices = self.df_prices.with_columns(
            pl.when(self.df_prices["asset_name"] == asset_name)
            .then(pl.lit(category))
            .otherwise(pl.col("category"))
            .alias("category")
        )
        self.save()

    def set_link(self, asset_name: str, link: str) -> None:
        """Update the link URL for an asset."""
        if asset_name not in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{asset_name}' not found.")
        mask = self.df["asset_name"] == asset_name
        self.df = self.df.with_columns(
            pl.when(mask).then(pl.lit(link)).otherwise(pl.col("link")).alias("link")
        )
        self.df_prices = self.df_prices.with_columns(
            pl.when(mask).then(pl.lit(link)).otherwise(pl.col("link")).alias("link")
        )
        self.save()

    def set_quantity_or_price(
        self,
        asset_name: str,
        month: int,
        quantity: float,
        quant_or_price: str = "quantity",
    ) -> None:
        """Set the quantity for an asset in a given month.

        Parameters
        ----------
        asset_name:
            Name of the asset.
        month:
            Month number (1-12).
        quantity:
            Number of units owned.
        """
        if not 1 <= month <= 12:
            raise ValueError(f"month must be between 1 and 12, got {month}")
        if asset_name not in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{asset_name}' not found.")

        col = f"{month:02d}"
        mask = self.df["asset_name"] == asset_name
        if quant_or_price == "quantity":
            self.df = self.df.with_columns(
                pl.when(mask).then(pl.lit(quantity)).otherwise(pl.col(col)).alias(col)
            )
            self.save_df()
        elif quant_or_price == "price":
            self.df_prices = self.df_prices.with_columns(
                pl.when(mask).then(pl.lit(quantity)).otherwise(pl.col(col)).alias(col)
            )
            self.save_df_prices()
        else:
            raise ValueError(
                f"quant_or_price must be 'quantity' or 'price', got '{quant_or_price}'"
            )

    def set_quantity(self, asset_name: str, month: int, quantity: float) -> None:
        """Set the quantity for an asset in a given month."""
        self.set_quantity_or_price(
            asset_name=asset_name,
            month=month,
            quantity=quantity,
            quant_or_price="quantity",
        )

    def set_price(self, asset_name: str, month: int, price: float) -> None:
        """Set the price for an asset in a given month."""
        self.set_quantity_or_price(
            asset_name=asset_name,
            month=month,
            quantity=price,
            quant_or_price="price",
        )

    @property
    def df_value(self) -> pl.DataFrame:
        """Return a dataframe of quantity x price for each asset and month.

        The result has the same shape as ``df`` (asset_name, category, link,
        01..12) but each monthly cell contains ``quantity * price``.
        """
        mcols = [f"{m:02d}" for m in range(1, 13)]
        prices = self.df_prices.select(
            "asset_name",
            *[pl.col(c).alias(f"{c}_price") for c in mcols],
        )
        value = self.df.join(prices, on="asset_name", how="left")
        for c in mcols:
            value = value.with_columns(
                (pl.col(c) * pl.col(f"{c}_price")).alias(c)
            ).drop(f"{c}_price")
        return value

    def save_df(self) -> None:
        """Write the holdings dataframe to disk."""
        self.df.write_parquet(str(self._path))

    def save_df_prices(self) -> None:
        """Write the prices dataframe to disk."""
        self.df_prices.write_parquet(str(self._path_prices))

    def save(self) -> None:
        """Write the holdings dataframe to disk."""
        self.save_df()
        self.save_df_prices()


# ======================================================================
# Liquidity
# ======================================================================

_LIQUIDITY_CATEGORIES = ["Bank/Broker account", "Cash", "Other"]

_LIQ_META_COLS = ["asset_name", "category", "currency"]


class Liquidity:
    """Yearly liquidity dataframe.

    Layout (wide format)::

        asset_name      | category      | currency | 01    | 02    | … | 12
        Main account    | Bank account  | E        | 5000  | 5200  |   | …
        Savings account | Bank account  | E        | 10000 | 10000 |   | …

    Each monthly cell contains the *value* (amount of money) held in
    the given currency.

    Parameters
    ----------
    year:
        Calendar year (e.g. 2026).
    """

    def __init__(self, year: int):
        self.year = year
        self._path = get_year_summary_path(year, LIQUIDITY_FILENAME)

        if self._path.exists():
            self.df = pl.read_parquet(str(self._path))
            if "currency" not in self.df.columns:
                self.df = self.df.with_columns(pl.lit("E").alias("currency"))
        else:
            self.df = pl.DataFrame(
                schema={
                    "asset_name": pl.Utf8,
                    "category": pl.Utf8,
                    "currency": pl.Utf8,
                    **{f"{m:02d}": pl.Float64 for m in range(1, 13)},
                }
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_asset(self, asset_name: str, category: str, currency: str = "E") -> None:
        """Add a new liquidity asset row (all monthly values initialised to 0)."""
        if category not in _LIQUIDITY_CATEGORIES:
            raise ValueError(
                f"'{category}' is not a valid category. "
                f"Choose from: {_LIQUIDITY_CATEGORIES}"
            )
        if asset_name in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{asset_name}' already exists.")

        new_row = pl.DataFrame(
            {
                "asset_name": [asset_name],
                "category": [category],
                "currency": [currency],
                **{f"{m:02d}": [0.0] for m in range(1, 13)},
            }
        )
        self.df = pl.concat([self.df, new_row], how="diagonal")
        self.save()

    def remove_asset(self, asset_name: str) -> None:
        """Remove a liquidity asset row by name."""
        self.df = self.df.filter(pl.col("asset_name") != asset_name)
        self.save()

    def rename_asset(self, old_name: str, new_name: str) -> None:
        """Rename a liquidity asset row."""
        if old_name not in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{old_name}' not found.")
        if new_name != old_name and new_name in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{new_name}' already exists.")
        mask = self.df["asset_name"] == old_name
        self.df = self.df.with_columns(
            pl.when(mask)
            .then(pl.lit(new_name))
            .otherwise(pl.col("asset_name"))
            .alias("asset_name")
        )
        self.save()

    def set_category(self, asset_name: str, category: str) -> None:
        """Update the category for a liquidity asset."""
        if asset_name not in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{asset_name}' not found.")
        if category not in _LIQUIDITY_CATEGORIES:
            raise ValueError(
                f"'{category}' is not a valid category. "
                f"Choose from: {_LIQUIDITY_CATEGORIES}"
            )
        mask = self.df["asset_name"] == asset_name
        self.df = self.df.with_columns(
            pl.when(mask)
            .then(pl.lit(category))
            .otherwise(pl.col("category"))
            .alias("category")
        )
        self.save()

    def set_value(self, asset_name: str, month: int, value: float) -> None:
        """Set the value for an asset in a given month."""
        if not 1 <= month <= 12:
            raise ValueError(f"month must be between 1 and 12, got {month}")
        if asset_name not in self.df["asset_name"].to_list():
            raise ValueError(f"Asset '{asset_name}' not found.")

        col = f"{month:02d}"
        mask = self.df["asset_name"] == asset_name
        self.df = self.df.with_columns(
            pl.when(mask).then(pl.lit(value)).otherwise(pl.col(col)).alias(col)
        )
        self.save()

    def save(self) -> None:
        """Write the liquidity dataframe to disk."""
        self.df.write_parquet(str(self._path))


# ======================================================================
# CreditsDebts
# ======================================================================


class CreditsDebts:
    """Yearly credits & debts dataframe.

    Layout (wide format)::

        name            | currency | 01    | 02    | … | 12
        Loan to friend  | E        | 500   | 500   |   | 0
        Car loan        | E        | -8000 | -7500 |   | …

    Each monthly cell contains the outstanding amount.  Positive values
    represent credits (money owed to the user) and negative values
    represent debts (money the user owes).

    Parameters
    ----------
    year:
        Calendar year (e.g. 2026).
    """

    def __init__(self, year: int):
        self.year = year
        self._path = get_year_summary_path(year, CREDITS_DEBTS_FILENAME)

        if self._path.exists():
            self.df = pl.read_parquet(str(self._path))
            if "currency" not in self.df.columns:
                self.df = self.df.with_columns(pl.lit("E").alias("currency"))
            # Migration: drop legacy "type" column if present
            if "type" in self.df.columns:
                self.df = self.df.drop("type")
        else:
            self.df = pl.DataFrame(
                schema={
                    "name": pl.Utf8,
                    "currency": pl.Utf8,
                    **{f"{m:02d}": pl.Float64 for m in range(1, 13)},
                }
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_entry(self, name: str, currency: str = "E") -> None:
        """Add a new credit/debt row (all monthly values initialised to 0).

        Positive values entered later represent credits; negative values
        represent debts.
        """
        if name in self.df["name"].to_list():
            raise ValueError(f"Entry '{name}' already exists.")

        new_row = pl.DataFrame(
            {
                "name": [name],
                "currency": [currency],
                **{f"{m:02d}": [0.0] for m in range(1, 13)},
            }
        )
        self.df = pl.concat([self.df, new_row], how="diagonal")
        self.save()

    def remove_entry(self, name: str) -> None:
        """Remove a credit/debt row by name."""
        self.df = self.df.filter(pl.col("name") != name)
        self.save()

    def rename_entry(self, old_name: str, new_name: str) -> None:
        """Rename a credit/debt row."""
        if old_name not in self.df["name"].to_list():
            raise ValueError(f"Entry '{old_name}' not found.")
        if new_name != old_name and new_name in self.df["name"].to_list():
            raise ValueError(f"Entry '{new_name}' already exists.")
        mask = self.df["name"] == old_name
        self.df = self.df.with_columns(
            pl.when(mask)
            .then(pl.lit(new_name))
            .otherwise(pl.col("name"))
            .alias("name")
        )
        self.save()

    def set_value(self, name: str, month: int, value: float) -> None:
        """Set the outstanding amount for an entry in a given month."""
        if not 1 <= month <= 12:
            raise ValueError(f"month must be between 1 and 12, got {month}")
        if name not in self.df["name"].to_list():
            raise ValueError(f"Entry '{name}' not found.")

        col = f"{month:02d}"
        mask = self.df["name"] == name
        self.df = self.df.with_columns(
            pl.when(mask).then(pl.lit(value)).otherwise(pl.col(col)).alias(col)
        )
        self.save()

    def save(self) -> None:
        """Write the credits/debts dataframe to disk."""
        self.df.write_parquet(str(self._path))
