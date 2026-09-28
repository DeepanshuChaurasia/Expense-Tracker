"""Streamlit web interface for Expense Tracker.

Run with:  streamlit run streamlit_app.py

It reuses the same database, validation and reporting code as the command-line
app, so both interfaces always agree and share the same data.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from datetime import date

import streamlit as st

from expense_tracker.csv_io import FIELDS, expenses_to_csv_text, import_csv
from expense_tracker.db import DEFAULT_DB_PATH, ExpenseDB, NotFoundError
from expense_tracker.formatting import format_inr
from expense_tracker.reports import (
    available_months,
    budget_alerts,
    expense_rows,
    month_overview,
)
from expense_tracker.validators import (
    ValidationError,
    normalize_category,
    normalize_description,
    parse_amount,
    parse_month,
)

st.set_page_config(page_title="Expense Tracker", page_icon="💰", layout="wide")

DB_PATH = os.environ.get("EXPENSE_TRACKER_DB", str(DEFAULT_DB_PATH))
NEW_CATEGORY = "➕ New category…"
ALL = "All"


# ------------------------------------------------------------------ helpers
@contextmanager
def open_db():
    """Open a fresh connection per script run (Streamlit runs scripts in worker threads)."""
    db = ExpenseDB(DB_PATH)
    try:
        yield db
    finally:
        db.close()


def flash(kind: str, message: str) -> None:
    """Queue a message to show after the next rerun (kind: success/error/warning/info)."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flash() -> None:
    for kind, message in st.session_state.pop("_flash", []):
        getattr(st, kind)(message)


def counter(name: str) -> int:
    """A per-form counter used in widget keys; bumping it resets the form's fields."""
    return st.session_state.setdefault(name, 0)


def amount_text(paise: int) -> str:
    return f"{paise // 100}.{paise % 100:02d}"


def category_options(db: ExpenseDB) -> list:
    return [c for c, _, _ in db.category_summary()]


# -------------------------------------------------------------------- pages
def page_dashboard(db: ExpenseDB) -> None:
    st.title("📊 Dashboard")
    if db.total()[1] == 0:
        st.info("No expenses yet. Head to **Add expense** to record your first one.")
        return

    month = st.selectbox("Month", available_months(db))
    ov = month_overview(db, month)

    c1, c2, c3 = st.columns(3)
    delta = None
    if ov.delta_paise != 0:
        sign = "+" if ov.delta_paise > 0 else ""
        delta = f"{sign}{format_inr(ov.delta_paise)} vs {ov.previous_month}"
    c1.metric("Total spent", format_inr(ov.total_paise), delta=delta, delta_color="inverse")
    c2.metric("Expenses", ov.count)
    if ov.top_category:
        c3.metric("Top category", ov.top_category[0].title(), format_inr(ov.top_category[1]), delta_color="off")
    else:
        c3.metric("Top category", "—")

    left, right = st.columns(2)
    with left:
        st.subheader("Spending by category")
        rows = db.category_summary(month)
        if rows:
            st.bar_chart(
                [{"Category": c, "Total (₹)": t / 100} for c, _, t in rows],
                x="Category",
                y="Total (₹)",
            )
        else:
            st.caption("Nothing recorded for this month.")
    with right:
        st.subheader("Monthly trend")
        st.bar_chart(
            [{"Month": m, "Total (₹)": t / 100} for m, _, t in db.monthly_summary()],
            x="Month",
            y="Total (₹)",
        )

    statuses = db.budget_status(month)
    if statuses:
        st.subheader("Budgets")
        for s in statuses:
            used = s.spent_paise / s.limit_paise
            label = f"{s.category.title()}: {format_inr(s.spent_paise)} of {format_inr(s.limit_paise)} ({used:.0%})"
            if s.exceeded:
                label += "  ⚠️ OVER BUDGET"
            st.progress(min(used, 1.0), text=label)

    st.subheader("Recent expenses")
    recent = db.list_expenses(month=month, limit=10)
    if recent:
        st.dataframe(expense_rows(recent), hide_index=True)
    else:
        st.caption("Nothing recorded for this month.")


def page_add(db: ExpenseDB) -> None:
    st.title("➕ Add expense")
    show_flash()
    n = counter("add_n")
    existing = category_options(db)
    options = existing + [NEW_CATEGORY]

    with st.form(f"add_form_{n}"):
        amount = st.text_input("Amount (₹)", placeholder="e.g. 250 or 99.50", key=f"add_amount_{n}")
        picked = st.selectbox("Category", options, key=f"add_cat_{n}")
        new_cat = st.text_input(
            "New category name",
            help="Only used if you picked “New category…” above.",
            key=f"add_newcat_{n}",
        )
        spent_on = st.date_input("Date", value=date.today(), max_value=date.today(), key=f"add_date_{n}")
        description = st.text_input("Description (optional)", max_chars=100, key=f"add_desc_{n}")
        submitted = st.form_submit_button("Add expense")

    if submitted:
        try:
            amount_paise = parse_amount(amount)
            category = normalize_category(new_cat if picked == NEW_CATEGORY else picked)
            expense = db.add(
                amount_paise,
                category,
                normalize_description(description),
                spent_on.isoformat(),
            )
        except ValidationError as exc:
            st.error(str(exc))
            return
        flash("success", f"Added #{expense.id}: {format_inr(expense.amount_paise)} on '{expense.category}' ({expense.spent_on}).")
        for message in budget_alerts(db, expense.category, expense.spent_on[:7]):
            flash("warning", message)
        st.session_state["add_n"] = n + 1  # fresh, empty form on the next run
        st.rerun()


def page_manage(db: ExpenseDB) -> None:
    st.title("🧾 Manage expenses")
    show_flash()
    if db.total()[1] == 0:
        st.info("No expenses yet. Add one from the **Add expense** page.")
        return

    f1, f2, f3 = st.columns(3)
    month = f1.selectbox("Month", [ALL] + available_months(db))
    category = f2.selectbox("Category", [ALL] + category_options(db))
    search = f3.text_input("Search description")
    filters = dict(
        month=None if month == ALL else month,
        category=None if category == ALL else category,
        search=search.strip() or None,
    )
    expenses = db.list_expenses(**filters)
    total, count = db.total(**filters)
    st.caption(f"{count} expense(s) · total {format_inr(total)}")
    if not expenses:
        st.info("No expenses match these filters.")
        return
    st.dataframe(expense_rows(expenses), hide_index=True)

    st.divider()
    st.subheader("Edit or delete")
    labels = {
        e.id: f"#{e.id} · {e.spent_on} · {e.category} · {format_inr(e.amount_paise)}" for e in expenses
    }
    chosen = st.selectbox("Pick an expense", list(labels), format_func=labels.get)
    exp = db.get(chosen)
    edit_tab, delete_tab = st.tabs(["✏️ Edit", "🗑️ Delete"])

    with edit_tab:
        with st.form(f"edit_form_{exp.id}"):
            amount = st.text_input("Amount (₹)", value=amount_text(exp.amount_paise))
            cat = st.text_input("Category", value=exp.category)
            when = st.date_input("Date", value=date.fromisoformat(exp.spent_on), max_value=date.today())
            desc = st.text_input("Description", value=exp.description, max_chars=100)
            saved = st.form_submit_button("Save changes")
        if saved:
            try:
                updated = db.update(
                    exp.id,
                    amount_paise=parse_amount(amount),
                    category=normalize_category(cat),
                    description=normalize_description(desc),
                    spent_on=when.isoformat(),
                )
            except (ValidationError, NotFoundError) as exc:
                st.error(str(exc))
            else:
                flash("success", f"Updated #{updated.id}.")
                for message in budget_alerts(db, updated.category, updated.spent_on[:7]):
                    flash("warning", message)
                st.rerun()

    with delete_tab:
        st.warning(f"This will permanently delete {labels[exp.id]}.")
        confirm = st.checkbox("Yes, delete it", key=f"confirm_delete_{exp.id}")
        if st.button("Delete expense", disabled=not confirm, key=f"delete_{exp.id}"):
            try:
                db.delete(exp.id)
            except NotFoundError as exc:
                st.error(str(exc))
            else:
                flash("success", f"Deleted #{exp.id}.")
                st.rerun()


def page_budgets(db: ExpenseDB) -> None:
    st.title("🎯 Budgets")
    show_flash()
    month = st.selectbox("Month", available_months(db))
    statuses = db.budget_status(month)
    if statuses:
        st.dataframe(
            [
                {
                    "Category": s.category,
                    "Limit (₹)": s.limit_paise / 100,
                    "Spent (₹)": s.spent_paise / 100,
                    "Remaining (₹)": s.remaining_paise / 100,
                    "Status": "OVER" if s.exceeded else "OK",
                }
                for s in statuses
            ],
            hide_index=True,
        )
    else:
        st.info("No budgets set yet. Create one below.")

    n = counter("budget_n")
    st.subheader("Set or update a budget")
    known = ", ".join(category_options(db))
    with st.form(f"budget_form_{n}"):
        category = st.text_input("Category", help=f"Existing categories: {known}" if known else None, key=f"bud_cat_{n}")
        limit = st.text_input("Monthly limit (₹)", placeholder="e.g. 5000", key=f"bud_limit_{n}")
        submitted = st.form_submit_button("Save budget")
    if submitted:
        try:
            cat = normalize_category(category)
            paise = parse_amount(limit)
            db.set_budget(cat, paise)
        except ValidationError as exc:
            st.error(str(exc))
        else:
            flash("success", f"Monthly budget for '{cat}' set to {format_inr(paise)}.")
            st.session_state["budget_n"] = n + 1
            st.rerun()

    if statuses:
        st.subheader("Remove a budget")
        to_remove = st.selectbox("Budget", [s.category for s in statuses], key="remove_budget_pick")
        if st.button("Remove budget"):
            try:
                db.remove_budget(to_remove)
            except NotFoundError as exc:
                st.error(str(exc))
            else:
                flash("success", f"Removed budget for '{to_remove}'.")
                st.rerun()


def page_import_export(db: ExpenseDB) -> None:
    st.title("📁 Import / Export")
    show_flash()

    st.subheader("Export to CSV")
    month = st.selectbox("Which month?", [ALL] + available_months(db), key="export_month")
    expenses = db.list_expenses(month=None if month == ALL else parse_month(month))
    st.caption(f"{len(expenses)} expense(s) will be exported.")
    st.download_button(
        "Download CSV",
        data=expenses_to_csv_text(expenses),
        file_name=f"expenses_{'all' if month == ALL else month}.csv",
        mime="text/csv",
        disabled=not expenses,
    )

    st.divider()
    st.subheader("Import from CSV")
    st.caption(f"Required columns: {', '.join(FIELDS[:3])}. Optional: {FIELDS[3]}. Dates must be YYYY-MM-DD.")
    st.download_button(
        "Download a blank template",
        data=",".join(FIELDS) + "\n2026-09-01,food,250.00,Lunch\n",
        file_name="expenses_template.csv",
        mime="text/csv",
    )
    n = counter("import_n")
    uploaded = st.file_uploader("Choose a CSV file", type="csv", key=f"upload_{n}")
    if uploaded is not None and st.button("Import expenses"):
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = tmp.name
            imported, errors = import_csv(db, tmp_path)
        except ValidationError as exc:
            st.error(str(exc))
        except UnicodeDecodeError:
            st.error("Could not read the file. Please save it as a UTF-8 CSV.")
        else:
            flash("success" if imported else "info", f"Imported {imported} expense(s).")
            if errors:
                flash("warning", f"Skipped {len(errors)} invalid row(s):\n\n" + "\n".join(f"- {e}" for e in errors[:10]))
            st.session_state["import_n"] = n + 1
            st.rerun()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


PAGES = {
    "📊 Dashboard": page_dashboard,
    "➕ Add expense": page_add,
    "🧾 Manage expenses": page_manage,
    "🎯 Budgets": page_budgets,
    "📁 Import / Export": page_import_export,
}


def main() -> None:
    st.sidebar.title("💰 Expense Tracker")
    choice = st.sidebar.radio("Go to", list(PAGES), label_visibility="collapsed")
    st.sidebar.caption(f"Data file: {DB_PATH}")
    with open_db() as db:
        PAGES[choice](db)


main()
