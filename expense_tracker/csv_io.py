"""CSV export and import."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import List, Sequence, Tuple, Union

from .db import Expense, ExpenseDB
from .validators import (
    ValidationError,
    normalize_category,
    normalize_description,
    parse_amount,
    parse_date,
)

FIELDS = ["date", "category", "amount", "description"]


def _write_rows(expenses: Sequence[Expense], fh) -> None:
    writer = csv.writer(fh)
    writer.writerow(FIELDS)
    for e in expenses:
        writer.writerow([e.spent_on, e.category, f"{e.amount_paise // 100}.{e.amount_paise % 100:02d}", e.description])


def export_csv(expenses: Sequence[Expense], path: Union[str, Path]) -> int:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        _write_rows(expenses, fh)
    return len(expenses)


def expenses_to_csv_text(expenses: Sequence[Expense]) -> str:
    """Same format as export_csv, but returned as a string (used by the web UI download button)."""
    buffer = io.StringIO(newline="")
    _write_rows(expenses, buffer)
    return buffer.getvalue()


def import_csv(db: ExpenseDB, path: Union[str, Path]) -> Tuple[int, List[str]]:
    """Import expenses from a CSV file.

    Valid rows are inserted in a single transaction; invalid rows are skipped and
    reported as human-readable messages. Returns (imported_count, error_messages).
    """
    valid = []
    errors: List[str] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        headers = {(h or "").strip().lower() for h in (reader.fieldnames or [])}
        missing = {"date", "category", "amount"} - headers
        if missing:
            raise ValidationError(f"CSV is missing required column(s): {', '.join(sorted(missing))}.")
        for line_no, raw in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            try:
                if not row.get("date"):
                    raise ValidationError("Date is required.")
                valid.append(
                    (
                        parse_amount(row.get("amount")),
                        normalize_category(row.get("category")),
                        normalize_description(row.get("description")),
                        parse_date(row["date"]),
                    )
                )
            except ValidationError as exc:
                errors.append(f"Line {line_no}: {exc}")
    imported = db.add_many(valid) if valid else 0
    return imported, errors
