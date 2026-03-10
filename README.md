# Finguard

A personal finance tracker with an interactive web dashboard.
Track expenses, cashflow, investments, liquidity, and net worth — all stored locally as Parquet files with zero cloud dependencies.

It follows the scheme of the old [Mr Rip spreadsheets](), which I used to track expenses in the past. I built this tool because I have little familiarity 
with spreadsheets and don't like complex nested formulas hidden in cells and displayed in one bar. Here the same job is done with simple operations on dataframes instead.

Everything uses [Polars](https://pola.rs/) for data processing and Parquet for storage, simply because I am familiar with both.

I wrote the core logic from scratch, but the UI was almost entirely vibe-coded with an AI assistant (which also authored most comments and docstrings). As a result the UI interface is functional but not polished.

## Features

- **Expense Tracking** — Add, edit, delete, and filter monthly expenses. Auto-categorize via configurable name-to-category mappings.
- **Summary Dashboards** — Monthly and cumulative expense breakdowns by primary/secondary category with interactive pie, bar, and line charts.
- **Cashflow** — Track salary, interest, dividends, and other income alongside spending. Automatically computes savings and savings rate.
- **Net Worth** — Monitor investments (stocks/ETFs, commodities, bonds), liquidity (bank accounts, cash), and credits/debts over time.
- **Local-First** — All data lives on your machine in Parquet files. Configuration stored in XDG-compliant paths.

## Requirements

- **Python ≥ 3.14**
- [uv](https://docs.astral.sh/uv/)

## Installation

### Option A: Docker

```bash
git clone https://github.com/YOUR_USERNAME/finguard.git
cd finguard

# Using docker compose (data persists in host directories)
docker compose up -d

# Or build and run manually
docker build -t finguard .
docker run -d --name finguard \
  --network host \
  -e FINGUARD_PORT=8080 \
  -v ~/.local/share/docker/finguard:/data \
  -v ~/.local/share/docker/finguard/config:/data/config \
  finguard
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

## Usage

### Start the web UI

First activate the python environment on which finguard was installed and then run

```bash
finguard-ui              # starts on http://localhost:8080
finguard-ui --port 3000  # custom port
```

With Docker the UI is available at `http://localhost:8080` as soon as the container starts.

### Docker container commands

```bash
# Docker Compose
docker compose up -d      # start
docker compose down       # stop and remove

# Plain Docker
docker start finguard     # start existing container
docker stop finguard      # stop (close) container
```

### Navigate the dashboard

The interface has three main tabs:

| Tab | What it does |
|-----|-------------|
| **Expenses** | View, add, edit, delete, and filter detailed monthly expenses. Switch to the *Summary* sub-tab for category breakdowns and charts. The *Mappings* sub-tab lets you define automatic expense-name --> category rules. |
| **Cashflow** | Enter monthly income by category (salary, interest, dividends, other). Spending and savings are auto-calculated from expense data. |
| **Net Worth** | Track investment holdings and prices, bank/broker liquidity, and credits/debts. View allocation pie charts and evolution over time. |

Use the **year** and **month** selectors at the top to switch between periods. All data refreshes automatically.

### Data storage

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


## Limitations

- **No currency exchange** — all amounts are assumed to be in a single currency.
- **No automatic price updates** — investment prices must be entered manually each month.
- **No authentication or multi-user support**
- **No data import/export** — no CSV, bank-statement, or spreadsheet import; no export functionality (however the parquet files are always saved to disk).
- **No recurring transactions** — every expense must be entered individually; no templates or schedules.
- **Limited mobile experience**

## Tech Stack

- **[NiceGUI](https://nicegui.io/)** — Python web framework (Quasar/Vue 3 under the hood)
- **[Polars](https://pola.rs/)** — Fast DataFrame library for data processing
- **[Apache ECharts](https://echarts.apache.org/)** — Interactive charts (via NiceGUI)
- **[Matplotlib](https://matplotlib.org/)** — Additional plotting support
- **Parquet** — Efficient columnar storage for all financial data

## License

MIT