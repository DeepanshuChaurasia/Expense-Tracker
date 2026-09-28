"""Command-line interface: argparse sub-commands plus an interactive menu."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from argparse import Namespace
from datetime import date
from pathlib import Path
from typing import List, Optional

from . import __version__
from .csv_io import export_csv, import_csv
from .db import DEFAULT_DB_PATH, ExpenseDB, NotFoundError
from .reports import budget_alerts
from .formatting import bar, format_inr, render_table, truncate
from .validators import (
    ValidationError,
    normalize_category,
    normalize_description,
    parse_amount,
    parse_date,
    parse_expense_id,
    parse_month,
)


# ------------------------------------------------------------------ commands
def cmd_add(db: ExpenseDB, args: Namespace) -> int:
    expense = db.add(
        parse_amount(args.amount),
        normalize_category(args.category),
        normalize_description(args.description),
        parse_date(args.date),
    )
    print(f"Added #{expense.id}: {format_inr(expense.amount_paise)} on '{expense.category}' ({expense.spent_on})")
    for message in budget_alerts(db, expense.category, expense.spent_on[:7]):
        print(message)
    return 0


def cmd_list(db: ExpenseDB, args: Namespace) -> int:
    filters = dict(
        category=normalize_category(args.category) if args.category else None,
        month=parse_month(args.month),
        start=parse_date(args.start) if args.start else None,
        end=parse_date(args.end) if args.end else None,
        search=args.search.strip() if args.search else None,
    )
    if filters["start"] and filters["end"] and filters["start"] > filters["end"]:
        raise ValidationError("--start cannot be after --end.")
    expenses = db.list_expenses(limit=args.limit, **filters)
    if not expenses:
        print("No expenses found.")
        return 0
    rows = [
        (e.id, e.spent_on, e.category, truncate(e.description, 32), format_inr(e.amount_paise))
        for e in expenses
    ]
    print(render_table(["ID", "Date", "Category", "Description", "Amount"], rows, right_align=(0, 4)))
    total, count = db.total(**filters)
    shown = f"showing {len(expenses)} of {count}, " if len(expenses) < count else ""
    print(f"\n{count} expense(s), {shown}total {format_inr(total)}")
    return 0


def cmd_edit(db: ExpenseDB, args: Namespace) -> int:
    expense_id = parse_expense_id(args.id)
    changes = dict(
        amount_paise=parse_amount(args.amount) if args.amount else None,
        category=normalize_category(args.category) if args.category else None,
        description=normalize_description(args.description) if args.description is not None else None,
        spent_on=parse_date(args.date) if args.date else None,
    )
    if all(v is None for v in changes.values()):
        raise ValidationError("Nothing to change. Pass at least one of --amount, --category, --description, --date.")
    e = db.update(expense_id, **changes)
    print(f"Updated #{e.id}: {format_inr(e.amount_paise)} on '{e.category}' ({e.spent_on}) {e.description}".rstrip())
    return 0


def cmd_delete(db: ExpenseDB, args: Namespace) -> int:
    expense = db.get(parse_expense_id(args.id))
    if not args.yes:
        answer = input(
            f"Delete #{expense.id} ({format_inr(expense.amount_paise)} on '{expense.category}', {expense.spent_on})? [y/N] "
        )
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 0
    db.delete(expense.id)
    print(f"Deleted #{expense.id}.")
    return 0


def cmd_summary(db: ExpenseDB, args: Namespace) -> int:
    if args.by == "month":
        rows = db.monthly_summary()
        if not rows:
            print("No expenses recorded yet.")
            return 0
        print(render_table(
            ["Month", "Count", "Total"],
            [(m, n, format_inr(t)) for m, n, t in rows],
            right_align=(1, 2),
        ))
        print(f"\nAll months: {format_inr(sum(t for _, _, t in rows))}")
        return 0

    month = parse_month(args.month)
    rows = db.category_summary(month)
    if not rows:
        print("No expenses found" + (f" for {month}." if month else "."))
        return 0
    grand = sum(t for _, _, t in rows)
    table = [
        (cat, n, format_inr(t), f"{t * 100 / grand:.1f}%", bar(t * 100 / grand))
        for cat, n, t in rows
    ]
    print(f"Spending by category ({month or 'all time'})\n")
    print(render_table(["Category", "Count", "Total", "Share", ""], table, right_align=(1, 2, 3)))
    print(f"\nTotal: {format_inr(grand)}")
    return 0


def cmd_budget(db: ExpenseDB, args: Namespace) -> int:
    action = args.budget_cmd
    if action == "set":
        category = normalize_category(args.category)
        db.set_budget(category, parse_amount(args.amount))
        print(f"Monthly budget for '{category}' set to {format_inr(parse_amount(args.amount))}.")
    elif action == "remove":
        category = normalize_category(args.category)
        db.remove_budget(category)
        print(f"Removed budget for '{category}'.")
    else:  # list
        month = parse_month(args.month) or date.today().strftime("%Y-%m")
        statuses = db.budget_status(month)
        if not statuses:
            print("No budgets set. Try: expense-tracker budget set food 5000")
            return 0
        rows = [
            (
                s.category,
                format_inr(s.limit_paise),
                format_inr(s.spent_paise),
                format_inr(s.remaining_paise),
                "OVER" if s.exceeded else "ok",
            )
            for s in statuses
        ]
        print(f"Budgets for {month}\n")
        print(render_table(["Category", "Limit", "Spent", "Remaining", "Status"], rows, right_align=(1, 2, 3)))
    return 0


def cmd_export(db: ExpenseDB, args: Namespace) -> int:
    expenses = db.list_expenses(month=parse_month(args.month))
    count = export_csv(expenses, args.path)
    print(f"Exported {count} expense(s) to {args.path}")
    return 0


def cmd_import(db: ExpenseDB, args: Namespace) -> int:
    imported, errors = import_csv(db, args.path)
    print(f"Imported {imported} expense(s).")
    if errors:
        print(f"Skipped {len(errors)} invalid row(s):")
        for message in errors[:10]:
            print(f"  {message}")
        if len(errors) > 10:
            print(f"  ...and {len(errors) - 10} more.")
    return 0 if imported or not errors else 1


# --------------------------------------------------------------- interactive
def _ask(prompt: str) -> Optional[str]:
    value = input(prompt).strip()
    return value or None


def run_menu(db: ExpenseDB) -> int:
    options = [
        ("Add expense", lambda: cmd_add(db, Namespace(
            amount=_ask("Amount (₹): "), category=_ask("Category: "),
            description=_ask("Description (optional): ") or "", date=_ask("Date [today]: ")))),
        ("View expenses", lambda: cmd_list(db, Namespace(
            category=_ask("Category filter (blank = all): "), month=_ask("Month YYYY-MM (blank = all): "),
            start=None, end=None, search=None, limit=50))),
        ("Edit expense", lambda: cmd_edit(db, Namespace(
            id=_ask("Expense ID: "), amount=_ask("New amount (blank = keep): "),
            category=_ask("New category (blank = keep): "), description=_ask("New description (blank = keep): "),
            date=_ask("New date (blank = keep): ")))),
        ("Delete expense", lambda: cmd_delete(db, Namespace(id=_ask("Expense ID: "), yes=False))),
        ("Summary by category", lambda: cmd_summary(db, Namespace(by="category", month=_ask("Month YYYY-MM (blank = all): ")))),
        ("Summary by month", lambda: cmd_summary(db, Namespace(by="month", month=None))),
    ]
    print(f"Expense Tracker v{__version__}")
    while True:
        print("\n" + "\n".join(f"  {i}. {label}" for i, (label, _) in enumerate(options, 1)) + "\n  0. Quit")
        try:
            choice = input("\nChoose an option: ").strip()
            if choice == "0":
                print("Goodbye!")
                return 0
            if not choice.isdigit() or not 1 <= int(choice) <= len(options):
                print("Please enter a number from the menu.")
                continue
            print()
            options[int(choice) - 1][1]()
        except (ValidationError, NotFoundError) as exc:
            print(f"Error: {exc}")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            return 0


# -------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="expense-tracker",
        description="Track daily expenses from the terminal. Run with no command for an interactive menu.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help=f"database file (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="command")

    p = sub.add_parser("add", help="record a new expense")
    p.add_argument("amount", help="amount in rupees, e.g. 250 or 99.50")
    p.add_argument("category", help="e.g. food, travel, rent")
    p.add_argument("-d", "--description", default="", help="what it was for")
    p.add_argument("--date", help="YYYY-MM-DD, 'today' or 'yesterday' (default: today)")

    p = sub.add_parser("list", help="show expenses, newest first")
    p.add_argument("-c", "--category")
    p.add_argument("-m", "--month", help="YYYY-MM")
    p.add_argument("--start", help="from date (YYYY-MM-DD)")
    p.add_argument("--end", help="to date (YYYY-MM-DD)")
    p.add_argument("-s", "--search", help="text to look for in description or category")
    p.add_argument("-n", "--limit", type=int, help="show at most this many rows")

    p = sub.add_parser("edit", help="change an existing expense")
    p.add_argument("id")
    p.add_argument("--amount")
    p.add_argument("--category")
    p.add_argument("--description")
    p.add_argument("--date")

    p = sub.add_parser("delete", help="remove an expense")
    p.add_argument("id")
    p.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")

    p = sub.add_parser("summary", help="totals by category or by month")
    p.add_argument("--by", choices=["category", "month"], default="category")
    p.add_argument("-m", "--month", help="limit the category summary to YYYY-MM")

    p = sub.add_parser("budget", help="manage monthly category budgets")
    budget_sub = p.add_subparsers(dest="budget_cmd", metavar="action")
    b = budget_sub.add_parser("set", help="set or change a budget")
    b.add_argument("category")
    b.add_argument("amount")
    b = budget_sub.add_parser("list", help="show budget usage")
    b.add_argument("-m", "--month", help="YYYY-MM (default: this month)")
    b = budget_sub.add_parser("remove", help="delete a budget")
    b.add_argument("category")

    p = sub.add_parser("export", help="write expenses to a CSV file")
    p.add_argument("path")
    p.add_argument("-m", "--month", help="only export YYYY-MM")

    p = sub.add_parser("import", help="load expenses from a CSV file")
    p.add_argument("path")
    return parser


HANDLERS = {
    "add": cmd_add, "list": cmd_list, "edit": cmd_edit, "delete": cmd_delete,
    "summary": cmd_summary, "budget": cmd_budget, "export": cmd_export, "import": cmd_import,
}


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # so ₹ and bars survive Windows consoles
        except (AttributeError, ValueError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "budget" and not args.budget_cmd:
        args.budget_cmd = "list"
        args.month = None
    try:
        with ExpenseDB(args.db) as db:
            if args.command is None:
                return run_menu(db)
            return HANDLERS[args.command](db, args)
    except (ValidationError, NotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
    except FileNotFoundError as exc:
        print(f"Error: file not found: {exc.filename}", file=sys.stderr)
    except OSError as exc:
        print(f"Error: could not access file: {exc}", file=sys.stderr)
    except sqlite3.Error as exc:
        print(f"Database error: {exc}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
