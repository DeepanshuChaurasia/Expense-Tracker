"""Presentation-independent reporting helpers shared by the CLI and the Streamlit app."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from .db import Expense, ExpenseDB
from .formatting import format_inr


def current_month(today: Optional[date] = None) -> str:
    return (today or date.today()).strftime("%Y-%m")


def previous_month(month: str) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year - 1}-12" if mon == 1 else f"{year}-{mon - 1:02d}"


def available_months(db: ExpenseDB, today: Optional[date] = None) -> List[str]:
    """Months that have data plus the current month, newest first."""
    months = {m for m, _, _ in db.monthly_summary()}
    months.add(current_month(today))
    return sorted(months, reverse=True)


@dataclass(frozen=True)
class MonthOverview:
    month: str
    total_paise: int
    count: int
    previous_month: str
    previous_total_paise: int
    top_category: Optional[Tuple[str, int]]  # (category, total_paise)

    @property
    def delta_paise(self) -> int:
        return self.total_paise - self.previous_total_paise


def month_overview(db: ExpenseDB, month: str) -> MonthOverview:
    total, count = db.total(month=month)
    prev = previous_month(month)
    prev_total, _ = db.total(month=prev)
    summary = db.category_summary(month)
    top = (summary[0][0], summary[0][2]) if summary else None
    return MonthOverview(month, total, count, prev, prev_total, top)


def budget_alerts(db: ExpenseDB, category: str, month: str) -> List[str]:
    """Human-readable warnings if `category` is near or over its budget for `month`."""
    messages = []
    for s in db.budget_status(month, category):
        if s.exceeded:
            messages.append(
                f"Warning: '{s.category}' is {format_inr(-s.remaining_paise)} over its "
                f"{format_inr(s.limit_paise)} budget for {month}."
            )
        elif s.spent_paise * 100 >= s.limit_paise * 80:
            messages.append(
                f"Heads up: '{s.category}' has used {s.spent_paise * 100 // s.limit_paise}% "
                f"of its budget for {month}."
            )
    return messages


def expense_rows(expenses: Sequence[Expense]) -> List[Dict[str, object]]:
    """Rows ready for a table widget. Amount is a number (rupees) so columns sort correctly."""
    return [
        {
            "ID": e.id,
            "Date": e.spent_on,
            "Category": e.category,
            "Description": e.description,
            "Amount (₹)": e.amount_paise / 100,
        }
        for e in expenses
    ]
