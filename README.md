# Expense Tracker

An expense manager written in Python with SQLite, with two interfaces that share one database: a **command-line app** and a **Streamlit web GUI**. Record daily expenses, edit or delete them, filter and search, see category-wise and monthly summaries, set monthly budgets, and move data in and out with CSV.

The command-line app uses only the Python standard library. The GUI additionally needs `streamlit` (see below).

## Features

- **Add, view, edit and delete** expenses, from sub-commands or an interactive menu
- **Summaries** by category (with share % and a text bar chart) and by month
- **Filters and search** by category, month, date range or text
- **Monthly budgets** per category, with a warning when you go over
- **CSV export and import**, where invalid rows are skipped and reported rather than crashing the import
- **Input validation** for amounts, dates, months, categories and IDs, with clear error messages and non-zero exit codes
- **Streamlit dashboard** with metrics, charts, budget progress bars, forms for add/edit/delete, and CSV upload/download
- **Indian rupee formatting** with lakh/crore grouping, e.g. `₹12,34,567.89`

## Web GUI (Streamlit)

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Your browser opens at `http://localhost:8501` with five pages:

| Page | What it does |
|---|---|
| Dashboard | Month picker, total spent vs last month, top category, category and monthly charts, budget progress bars, recent expenses |
| Add expense | Validated form with existing or new categories and a date picker |
| Manage expenses | Filter by month, category or text; edit or delete any expense (delete needs confirmation) |
| Budgets | Set, update and remove monthly category budgets; see spent vs limit |
| Import / Export | Download a CSV (all or one month), upload a CSV with per-row error reporting |

The GUI and CLI use the same database (`~/.expense_tracker/expenses.db`), so an expense added in one shows up in the other. Set the `EXPENSE_TRACKER_DB` environment variable to use a different file.

## Command-line quick start

```bash
git clone <your-repo-url>
cd expense-tracker

python -m expense_tracker add 250 food -d "Lunch" --date yesterday
python -m expense_tracker add 1200 travel -d "Metro recharge"
python -m expense_tracker list
python -m expense_tracker summary
```

Run with no command to get the interactive menu:

```bash
python -m expense_tracker
```

Optional: `pip install .` gives you an `expense-tracker` command.

## Commands

| Command | Example |
|---|---|
| Add | `add 99.50 food -d "Chai" --date 2026-09-10` |
| List | `list -c food -m 2026-09 -s chai -n 20` |
| Edit | `edit 3 --amount 120 --description "Corrected"` |
| Delete | `delete 3` (asks first; `-y` skips the prompt) |
| Summary | `summary`, `summary -m 2026-09`, `summary --by month` |
| Budgets | `budget set food 5000`, `budget list`, `budget remove food` |
| Export | `export expenses.csv -m 2026-09` |
| Import | `import expenses.csv` (columns: `date,category,amount,description`) |

The database lives at `~/.expense_tracker/expenses.db`. Use `--db path/to/file.db` to point somewhere else.

## Sample output

```
$ python -m expense_tracker summary
Spending by category (all time)

Category  Count      Total  Share
--------  -----  ---------  -----  --------------
rent          1  ₹4,500.50  72.3%  ██████████████
travel        1  ₹1,200.00  19.3%  ████
food          3    ₹520.00   8.4%  ██

Total: ₹6,220.50
```

## Design decisions

- **Money is stored as integer paise**, not floats, so `0.1 + 0.2` style rounding errors cannot creep into totals. Amounts are parsed with `Decimal` and validated with a strict pattern.
- **Every SQL statement is parameterised.** User text is never concatenated into a query, and search input has `LIKE` wildcards escaped. There is a test that tries an injection string.
- **Database constraints back up the validation.** A `CHECK (amount_paise > 0)` on the table means bad data is rejected even if application code has a bug.
- **Layered modules:** `validators` (input rules), `db` (all SQL), `csv_io`, `reports`, `formatting`, then `cli` and `streamlit_app` as thin front ends. The database layer never prints and the interfaces never write SQL, so the same logic serves both and is testable without a UI.
- **Transactions:** writes use `with conn:` so they commit on success and roll back on error. CSV import inserts all valid rows in one transaction.

## Project layout

```
expense_tracker/
    cli.py          argparse sub-commands and interactive menu
    db.py           SQLite schema and queries
    validators.py   input parsing and validation
    csv_io.py       CSV export/import
    reports.py      month overviews and budget alerts shared by CLI and GUI
    formatting.py   rupee formatting, tables, bars
streamlit_app.py    Streamlit web interface
tests/              unit, end-to-end and GUI smoke tests
```

## Running the tests

```bash
python -m unittest discover -s tests -t .
```

The suite has 34 tests covering validation edge cases, database behaviour (including SQL injection and wildcard escaping), budgets, reports, CSV round-trips, full CLI workflows against a temporary database, and a smoke test that renders every Streamlit page (skipped automatically if Streamlit is not installed).

## Ideas for the future

- Recurring expenses
- Deploying the Streamlit app (e.g. Streamlit Community Cloud) with a hosted database
- Multiple currencies

## License

MIT
