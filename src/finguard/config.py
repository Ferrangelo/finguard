"""Manage expense-name → category mappings stored in a JSON config file.

The config file lives at ``$XDG_CONFIG_HOME/finguard/category_mappings.json``.
If ``XDG_CONFIG_HOME`` is not set, it defaults to ``$HOME/.config``.

File format
-----------
```json
{
    "pam":    {"primary_category": "groceries", "secondary_category": "supermarket"},
    "nowtv":  {"primary_category": "housing",   "secondary_category": "tv"}
}
```

Keys are expense names (lower-cased for consistent look-ups).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR_NAME = "finguard"
CONFIG_FILE_NAME = "category_mappings.json"


def _get_config_dir() -> Path:
    """Return the finguard config directory, creating it if necessary."""
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        base = Path(xdg_config_home)
    else:
        base = Path.home() / ".config"

    config_dir = base / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _get_config_path() -> Path:
    """Return the full path to the category-mappings JSON file."""
    return _get_config_dir() / CONFIG_FILE_NAME


def _load_mappings() -> dict[str, dict[str, str]]:
    """Load the mappings file from disk.  Returns an empty dict if the file
    does not exist yet."""
    path = _get_config_path()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_mappings(mappings: dict[str, dict[str, str]]) -> None:
    """Persist *mappings* to disk (pretty-printed for easy hand-editing)."""
    path = _get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=4, ensure_ascii=False)


# ------------------------------------------------------------------
# Public functions
# ------------------------------------------------------------------


def add_mapping(
    expense_name: str,
    primary_category: str,
    secondary_category: str = "",
    *,
    overwrite: bool = False,
) -> None:
    """Add (or update) a mapping from *expense_name* to a category pair.

    Parameters
    ----------
    expense_name:
        The expense name to map (will be stored lower-cased).
    primary_category:
        Primary category string.
    secondary_category:
        Optional secondary category string.
    overwrite:
        If ``False`` (default) and the key already exists, a
        ``ValueError`` is raised.  Set to ``True`` to silently replace
        an existing entry.
    """
    key = expense_name.strip().lower()
    mappings = _load_mappings()

    if key in mappings and not overwrite:
        raise ValueError(
            f"Mapping for '{key}' already exists: {mappings[key]}. "
            "Pass overwrite=True to replace it."
        )

    mappings[key] = {
        "primary_category": primary_category.strip().lower(),
        "secondary_category": secondary_category.strip().lower(),
    }
    _save_mappings(mappings)


def remove_mapping(expense_name: str) -> dict[str, str]:
    """Remove the mapping for *expense_name* and return the deleted entry.

    Raises ``KeyError`` if the name is not found.
    """
    key = expense_name.strip().lower()
    mappings = _load_mappings()

    if key not in mappings:
        raise KeyError(f"No mapping found for '{key}'.")

    removed = mappings.pop(key)
    _save_mappings(mappings)
    return removed


def get_mapping(expense_name: str) -> Optional[dict[str, str]]:
    """Look up the category mapping for *expense_name*.

    Returns ``None`` if no mapping exists.
    """
    key = expense_name.strip().lower()
    return _load_mappings().get(key)


def get_all_mappings() -> dict[str, dict[str, str]]:
    """Return a copy of every stored mapping."""
    return _load_mappings()


def clear_all_mappings() -> None:
    """Delete **all** mappings (the file is kept but emptied)."""
    _save_mappings({})
