"""Path functions for finguard data files.

Data files are stored in ``$XDG_DATA_HOME/finguard/dbs/`` (defaulting to
``$HOME/.local/share/finguard/dbs/`` when ``XDG_DATA_HOME`` is not set).

Directory layout
----------------
::

    $XDG_DATA_HOME/
    └── finguard/
        └── dbs/
            ├── 2025/
            │   ├── 01_detailed_expenses.parquet
            │   ├── 02_detailed_expenses.parquet
            │   └── ...
            │   ├── primaries.parquet
            │   └── secondaries.parquet
            ├── 2026/
            │   ├── 01_detailed_expenses.parquet
            │   ├── ...
            │   ├── primaries.parquet
            │   └── secondaries.parquet
            └── ...

Naming convention: monthly parquet files are named ``MM_detailed_expenses.parquet``
where ``MM`` is the zero-padded month number (01–12).

Summary files are named ``primaries.parquet`` and ``secondaries.parquet`` and
are stored in the year directory they summarise (e.g. ``dbs/2026/``).
"""

from __future__ import annotations

import os
from pathlib import Path

_APP_DIR_NAME = "finguard"
_DBS_DIR_NAME = "dbs"
_PARQUET_SUFFIX = "_detailed_expenses.parquet"
PRIMARIES_FILENAME = "primaries.parquet"
SECONDARIES_FILENAME = "secondaries.parquet"


def _get_data_home() -> Path:
    """Return the XDG data home directory (``$XDG_DATA_HOME`` or
    ``$HOME/.local/share``)."""
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home)
    return Path.home() / ".local" / "share"


def get_dbs_root() -> Path:
    """Return ``<XDG_DATA_HOME>/finguard/dbs``, creating it if necessary."""
    dbs_root = _get_data_home() / _APP_DIR_NAME / _DBS_DIR_NAME
    dbs_root.mkdir(parents=True, exist_ok=True)
    return dbs_root


def get_year_summary_path(year: int, filename: str) -> Path:
    """Return the path for a summary parquet file inside the given year directory.

    Parameters
        year: Calendar year (e.g. 2026).
        filename: The filename, e.g. ``PRIMARIES_FILENAME`` or ``SECONDARIES_FILENAME``.

    Returns
        Path e.g. ``~/.local/share/finguard/dbs/2026/primaries.parquet``
    """
    return get_year_dir(year) / filename


def get_year_dir(year: int) -> Path:
    """Return ``<dbs_root>/<year>/``, creating it if necessary.

    Parameters
        year: Calendar year (e.g. 2026).
    """
    year_dir = get_dbs_root() / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)
    return year_dir


def get_monthly_parquet_path(year: int, month: int) -> Path:
    """Return the full path for a monthly detailed-expenses parquet file.
    The parent directories are created if they do not already exist.

    Parameters
        year: Calendar year (e.g. 2026).
        month: Month number (1–12).

    Returns Path
        e.g. ``~/.local/share/finguard/dbs/2026/03_detailed_expenses.parquet``

    Raises ValueError
        If *month* is not in the range 1–12.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be between 1 and 12, got {month}")

    filename = f"{month:02d}{_PARQUET_SUFFIX}"
    return get_year_dir(year) / filename


def month_from_parquet_path(path: str | Path) -> int:
    """Extract the month number from a parquet file path.

    Parameters
        path: A path whose **filename** follows the ``MM_detailed_expenses.parquet`` convention.

    Returns int
        The month number (1–12).

    Raises ValueError
        If the filename does not match the expected naming convention.
    """
    name = Path(path).name
    if not name.endswith(_PARQUET_SUFFIX):
        raise ValueError(
            f"Filename '{name}' does not match the expected pattern "
            f"'MM{_PARQUET_SUFFIX}'."
        )

    month_str = name[: -len(_PARQUET_SUFFIX)]
    try:
        month = int(month_str)
    except ValueError:
        raise ValueError(
            f"Could not parse month from filename '{name}'. "
            f"Expected the first two characters to be a zero-padded month number."
        )

    if not 1 <= month <= 12:
        raise ValueError(f"Parsed month {month} from '{name}' is out of range (1–12).")

    return month


def year_from_parquet_path(path: str | Path) -> int:
    """Extract the year from a parquet file path.

    Assumes the file sits directly inside a directory named after the year,
    e.g. ``…/2026/03_detailed_expenses.parquet``.

    Parameters
    ----------
    path:
        A path whose **parent directory** is named after the year.

    Returns
    -------
    int
        The year.

    Raises
    ------
    ValueError
        If the parent directory name is not a valid year.
    """
    parent_name = Path(path).parent.name
    try:
        return int(parent_name)
    except ValueError:
        raise ValueError(
            f"Could not parse year from parent directory '{parent_name}'. "
            "Expected the parquet file to sit inside a directory named after "
            "the year (e.g. '2026/')."
        )


def year_month_from_parquet_path(path: str | Path) -> tuple[int, int]:
    """Extract both year and month from a parquet file path.

    Parameters
    ----------
    path:
        A path following the ``<year>/MM_detailed_expenses.parquet`` convention.

    Returns
    -------
    tuple[int, int]
        ``(year, month)``
    """
    return year_from_parquet_path(path), month_from_parquet_path(path)
