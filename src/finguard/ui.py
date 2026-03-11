"""NiceGUI web interface for Finguard."""

from __future__ import annotations

from datetime import date

from nicegui import ui

from finguard.df_operations import DetailedExpenses
from finguard.ui_cashflow import build_cashflow_tab
from finguard.ui_expenses import build_expenses_tab
from finguard.ui_helpers import _MONTH_NAMES, _discover_years
from finguard.ui_networth import build_networth_tab


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

    # -- year / month handlers -----------------------------------------------

    def on_year_change(e):
        st.year = e.value
        load_data()
        _refreshables["refresh_table"]()
        _refreshables["summary_content"].refresh()
        _refreshables["cashflow_content"].refresh()
        _refreshables["investment_content"].refresh()
        _refreshables["liquidity_credits_debts_content"].refresh()
        if "total_networth_content" in _refreshables:
            _refreshables["total_networth_content"].refresh()

    def on_month_change(e):
        st.month = e.value
        load_data()
        _refreshables["refresh_table"]()
        _refreshables["summary_content"].refresh()
        _refreshables["investment_content"].refresh()
        _refreshables["liquidity_credits_debts_content"].refresh()
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
        ui.tab("Expenses").props("no-caps").classes("text-2xl")
        ui.tab("Cashflow").props("no-caps").classes("text-2xl")
        ui.tab("NetWorth").props("no-caps").classes("text-2xl")

    with ui.tab_panels(tabs, value="Expenses").classes("w-full"):
        # ===================== EXPENSES TAB =================================
        with ui.tab_panel("Expenses"):
            build_expenses_tab(st, _refreshables)

        # ===================== CASHFLOW TAB =================================
        with ui.tab_panel("Cashflow"):
            build_cashflow_tab(st, _refreshables)

        # ===================== NETWORTH TAB =================================
        with ui.tab_panel("NetWorth"):
            build_networth_tab(st, _refreshables)

    # -- refresh when switching tabs ----------------------------------------
    def _on_tab_change(e):
        if e.value == "Expenses":
            _refreshables["summary_content"].refresh()
        elif e.value == "Cashflow":
            _refreshables["cashflow_content"].refresh()
        elif e.value == "NetWorth":
            _refreshables["investment_content"].refresh()
            _refreshables["liquidity_credits_debts_content"].refresh()
            _refreshables["total_networth_content"].refresh()

    tabs.on_value_change(_on_tab_change)

    # -- initial data load ---------------------------------------------------
    load_data()
    _refreshables["refresh_table"]()
    _refreshables["summary_content"].refresh()


def main():
    """Entry point for the ``finguard-ui`` command.
    Optionally specify a port for the UI server (default: 8765).
    """
    import sys
    import argparse
    import os
    parser = argparse.ArgumentParser(description="Run Finguard UI server.")
    parser.add_argument("--port", type=int, default=8765, help="Port to run the UI server on (default: 8765)")
    parser.add_argument("--host", default=os.environ.get("FINGUARD_HOST", "127.0.0.1"), help="Host to bind to (default: 127.0.0.1, set FINGUARD_HOST=0.0.0.0 for Docker)")
    args = parser.parse_args(sys.argv[1:])
    ui.run(title="Finguard", host=args.host, port=args.port, reload=False)
