"""SQLite data layer.

All SQL lives in this module and every query is parameterised, so user input
is never concatenated into a statement. Money is stored as integer paise.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

DEFAULT_DB_PATH = Path.home() / ".expense_tracker" / "expenses.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
    category     TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    spent_on     TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_expenses_spent_on ON expenses(spent_on);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);

CREATE TABLE IF NOT EXISTS budgets (
    category            TEXT PRIMARY KEY,
    monthly_limit_paise INTEGER NOT NULL CHECK (monthly_limit_paise > 0)
);
"""


class NotFoundError(LookupError):
    """Raised when a requested expense or budget does not exist."""


@dataclass(frozen=True)
class Expense:
    id: int
    amount_paise: int
    category: str
    description: str
    spent_on: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Expense":
        return cls(row["id"], row["amount_paise"], row["category"], row["description"], row["spent_on"])


@dataclass(frozen=True)
class BudgetStatus:
    category: str
    limit_paise: int
    spent_paise: int

    @property
    def remaining_paise(self) -> int:
        return self.limit_paise - self.spent_paise

    @property
    def exceeded(self) -> bool:
        return self.spent_paise > self.limit_paise


class ExpenseDB:
    def __init__(self, path: Union[str, Path] = DEFAULT_DB_PATH) -> None:
        path_str = str(path)
        if path_str != ":memory:":
            resolved = Path(path_str).expanduser()
            resolved.parent.mkdir(parents=True, exist_ok=True)
            path_str = str(resolved)
        self.conn = sqlite3.connect(path_str)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ExpenseDB":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- CRUD
    def add(self, amount_paise: int, category: str, description: str, spent_on: str) -> Expense:
        with self.conn:  # commits on success, rolls back on error
            cur = self.conn.execute(
                "INSERT INTO expenses (amount_paise, category, description, spent_on) VALUES (?, ?, ?, ?)",
                (amount_paise, category, description, spent_on),
            )
        return self.get(cur.lastrowid)

    def add_many(self, rows: Iterable[Tuple[int, str, str, str]]) -> int:
        """Insert many (amount_paise, category, description, spent_on) rows atomically."""
        rows = list(rows)
        with self.conn:
            self.conn.executemany(
                "INSERT INTO expenses (amount_paise, category, description, spent_on) VALUES (?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def get(self, expense_id: int) -> Expense:
        row = self.conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"No expense found with ID {expense_id}.")
        return Expense.from_row(row)

    def update(
        self,
        expense_id: int,
        *,
        amount_paise: Optional[int] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        spent_on: Optional[str] = None,
    ) -> Expense:
        candidates = {
            "amount_paise": amount_paise,
            "category": category,
            "description": description,
            "spent_on": spent_on,
        }
        changes = {k: v for k, v in candidates.items() if v is not None}
        if not changes:
            raise ValueError("Nothing to update.")
        self.get(expense_id)  # raises NotFoundError if missing
        # Column names come from the fixed whitelist above, never from user input.
        assignments = ", ".join(f"{col} = ?" for col in changes)
        with self.conn:
            self.conn.execute(
                f"UPDATE expenses SET {assignments} WHERE id = ?",
                (*changes.values(), expense_id),
            )
        return self.get(expense_id)

    def delete(self, expense_id: int) -> None:
        with self.conn:
            cur = self.conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        if cur.rowcount == 0:
            raise NotFoundError(f"No expense found with ID {expense_id}.")

    # -------------------------------------------------------------- queries
    @staticmethod
    def _where(
        category: Optional[str],
        month: Optional[str],
        start: Optional[str],
        end: Optional[str],
        search: Optional[str],
    ) -> Tuple[str, List[object]]:
        clauses: List[str] = []
        params: List[object] = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if month:
            clauses.append("strftime('%Y-%m', spent_on) = ?")
            params.append(month)
        if start:
            clauses.append("spent_on >= ?")
            params.append(start)
        if end:
            clauses.append("spent_on <= ?")
            params.append(end)
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            like = f"%{escaped}%"
            clauses.append("(description LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\')")
            params.extend([like, like])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return where, params

    def list_expenses(
        self,
        *,
        category: Optional[str] = None,
        month: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Expense]:
        where, params = self._where(category, month, start, end, search)
        sql = f"SELECT * FROM expenses{where} ORDER BY spent_on DESC, id DESC"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [Expense.from_row(r) for r in self.conn.execute(sql, params)]

    def total(
        self,
        *,
        category: Optional[str] = None,
        month: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[int, int]:
        """Return (total_paise, count) for the given filters."""
        where, params = self._where(category, month, start, end, search)
        row = self.conn.execute(
            f"SELECT COALESCE(SUM(amount_paise), 0) AS total, COUNT(*) AS n FROM expenses{where}",
            params,
        ).fetchone()
        return row["total"], row["n"]

    def category_summary(self, month: Optional[str] = None) -> List[Tuple[str, int, int]]:
        """Return (category, count, total_paise) rows, biggest spend first."""
        where, params = self._where(None, month, None, None, None)
        rows = self.conn.execute(
            f"""SELECT category, COUNT(*) AS n, SUM(amount_paise) AS total
                FROM expenses{where} GROUP BY category ORDER BY total DESC, category""",
            params,
        )
        return [(r["category"], r["n"], r["total"]) for r in rows]

    def monthly_summary(self) -> List[Tuple[str, int, int]]:
        """Return (YYYY-MM, count, total_paise) rows in chronological order."""
        rows = self.conn.execute(
            """SELECT strftime('%Y-%m', spent_on) AS month, COUNT(*) AS n, SUM(amount_paise) AS total
               FROM expenses GROUP BY month ORDER BY month"""
        )
        return [(r["month"], r["n"], r["total"]) for r in rows]

    # -------------------------------------------------------------- budgets
    def set_budget(self, category: str, limit_paise: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO budgets (category, monthly_limit_paise) VALUES (?, ?)",
                (category, limit_paise),
            )

    def remove_budget(self, category: str) -> None:
        with self.conn:
            cur = self.conn.execute("DELETE FROM budgets WHERE category = ?", (category,))
        if cur.rowcount == 0:
            raise NotFoundError(f"No budget set for '{category}'.")

    def budget_status(self, month: str, category: Optional[str] = None) -> List[BudgetStatus]:
        sql = """SELECT b.category AS category,
                        b.monthly_limit_paise AS limit_paise,
                        COALESCE(SUM(e.amount_paise), 0) AS spent_paise
                 FROM budgets b
                 LEFT JOIN expenses e
                        ON e.category = b.category AND strftime('%Y-%m', e.spent_on) = ?"""
        params: List[object] = [month]
        if category:
            sql += " WHERE b.category = ?"
            params.append(category)
        sql += " GROUP BY b.category ORDER BY b.category"
        return [
            BudgetStatus(r["category"], r["limit_paise"], r["spent_paise"])
            for r in self.conn.execute(sql, params)
        ]
