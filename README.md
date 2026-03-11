# Finguard

A personal finance tracker with an interactive web dashboard.
Track expenses, cashflow, investments, liquidity, and net worth. All stored locally as Parquet files with zero cloud dependencies.

It follows a scheme similar to the old [Mr Rip spreadsheets](https://retireinprogress.com/how-i-track-my-finances-using-spreadsheets-part-1-why-and-what/). 

Everything uses [Polars](https://pola.rs/) for data processing and Parquet for storage, simply because I am familiar with both.

I wrote the core logic from scratch, but the UI was almost entirely vibe-coded with an AI assistant (which also authored most comments and docstrings). As a result the UI interface is functional but not polished.

## Features

<details>
<summary>Expand</summary>

- **Expense Tracking**: add, edit, delete, and filter monthly expenses. Auto-categorize via configurable name-to-category mappings.
- **Summary Dashboards**: monthly and cumulative expense breakdowns by primary/secondary category with interactive pie, bar, and line charts.
- **Cashflow**: track salary, interest, dividends, and other income alongside spending. Automatically computes savings and savings rate.
- **Net Worth**: monitor investments (stocks/ETFs, commodities, bonds), liquidity (bank accounts, cash), and credits/debts over time.
- **Local-First**: all data lives on your machine in Parquet files. Configuration stored in XDG-compliant paths.

</details>

## Installation

<details>
<summary>Expand</summary>

### Option A: Docker

```bash
git clone https://github.com/YOUR_USERNAME/finguard.git
cd finguard

# Using docker compose (data persists in host directories)
docker compose up -d
```

### Option B: Install with uv/pip

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/finguard.git
cd finguard

# Create a virtual environment and install (pick one)
uv venv
source .venv/bin/activate   # Linux/macOS
uv pip install .
# pip install .
```

</details>

## Usage

<details>
<summary>Expand</summary>

### Start the web UI

First activate the python environment on which finguard was installed and then run

```bash
finguard-ui              # starts on http://localhost:8765
finguard-ui --port 3000  # custom port
```

With Docker the UI is available at `http://localhost:8765` as soon as the container starts.

### Docker commands

```bash
# Docker Compose
docker compose up -d      # start
docker compose down       # stop and remove
```

### Navigate the dashboard

The interface has three main tabs:

| Tab | What it does |
|-----|-------------|
| **Expenses** | View, add, edit, delete, and filter detailed monthly expenses. Switch to the *Summary* sub-tab for category breakdowns and charts. The *Mappings* sub-tab lets you define automatic expense-name --> category rules. |
| **Cashflow** | Enter monthly income by category (salary, interest, dividends, other). Spending and savings are auto-calculated from expense data. |
| **Net Worth** | Track investment holdings and prices, bank/broker liquidity, and credits/debts. View allocation pie charts and evolution over time. |

Use the **year** and **month** selectors at the top to switch between periods. All data refreshes automatically.
</details>

## Data storage
<details>
<summary>Expand</summary>

Data is stored in two local XDG-compliant directories:

- **Expense & financial data** — `$XDG_DATA_HOME/finguard/` (default: `~/.local/share/finguard/`)
- **Category mappings** — `$XDG_CONFIG_HOME/finguard/` (default: `~/.config/finguard/`)

With Docker Compose, the data directory is bind-mounted to `~/.local/share/docker/finguard/`.

| What | Path |
|------|------|
| Expense & financial data | `$XDG_DATA_HOME/finguard/dbs/` (default: `~/.local/share/finguard/dbs/`) |
| Category mappings | `$XDG_CONFIG_HOME/finguard/category_mappings.json` (default: `~/.config/finguard/category_mappings.json`) |

Directory layout per year:

```
dbs/
└── 2026/
    ├── 01_detailed_expenses.parquet   # January expenses
    ├── 02_detailed_expenses.parquet   # February expenses
    ├── ...
    ├── primaries.parquet              # Cumulative primary category summary
    ├── secondaries.parquet            # Cumulative secondary category summary
    ├── cashflow.parquet               # Monthly income/spending/savings
    ├── investments.parquet            # Investments holdings
    ├── investments_prices.parquet     # Investment prices
    ├── liquidity.parquet              # Bank accounts & cash
    └── credits_debts.parquet          # Credits/debts
```

</details>

## Limitations

<details>
<summary>Expand</summary>

- **No currency exchange** — all amounts are assumed to be in a single currency.
- **No automatic price updates** — investment prices must be entered manually each month.
- **No authentication or multi-user support**
- **No data import/export** — no CSV, bank-statement, or spreadsheet import; no export functionality (however the parquet files are always saved to disk).
- **No recurring transactions** — every expense must be entered individually; no templates or schedules.
- **Limited mobile experience**

</details>

## Tech Stack

<details>
<summary>Expand</summary>

- **[NiceGUI](https://nicegui.io/)**: python web framework
- **[Polars](https://pola.rs/)**: fast DataFrame library for data processing
- **[Apache ECharts](https://echarts.apache.org/)**: interactive charts
- **[Matplotlib](https://matplotlib.org/)**
- **Parquet**: efficient columnar storage for all financial data

</details>

## License

MIT