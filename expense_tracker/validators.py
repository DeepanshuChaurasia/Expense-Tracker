"""Input validation and normalisation.

Every piece of user input passes through one of these functions before it
gets anywhere near the database. Amounts are converted to integer paise so
that money is never stored as a floating point number.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional


class ValidationError(ValueError):
    """Raised when user input is invalid. The message is safe to show to the user."""


MAX_AMOUNT_PAISE = 10_000_000 * 100  # Rs 1 crore per expense is a sane upper bound
MAX_CATEGORY_LEN = 30
MAX_DESCRIPTION_LEN = 100

_AMOUNT_RE = re.compile(r"^\d+(,\d+)*(\.\d{1,2})?$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9 &.\-]*$")


def parse_amount(text: object) -> int:
    """Parse a rupee amount such as '250', '1,250.50' or '₹99.9' into paise."""
    if text is None:
        raise ValidationError("Amount is required.")
    cleaned = str(text).strip().lower().replace("₹", "")
    if cleaned.startswith("rs."):
        cleaned = cleaned[3:]
    elif cleaned.startswith("rs"):
        cleaned = cleaned[2:]
    cleaned = cleaned.strip()
    if not _AMOUNT_RE.match(cleaned):
        raise ValidationError(
            f"Invalid amount '{text}'. Use a positive number with at most 2 decimals, e.g. 250 or 99.50."
        )
    paise = int(Decimal(cleaned.replace(",", "")) * 100)
    if paise <= 0:
        raise ValidationError("Amount must be greater than zero.")
    if paise > MAX_AMOUNT_PAISE:
        raise ValidationError("Amount is too large (maximum is ₹1,00,00,000).")
    return paise


def parse_date(text: Optional[str], today: Optional[date] = None) -> str:
    """Return an ISO date string. Accepts YYYY-MM-DD, 'today' or 'yesterday'.

    A blank value means today. Dates in the future are rejected.
    """
    today = today or date.today()
    value = (text or "").strip().lower()
    if value in ("", "today"):
        return today.isoformat()
    if value == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(
            f"Invalid date '{text}'. Use YYYY-MM-DD, 'today' or 'yesterday'."
        ) from None
    if parsed > today:
        raise ValidationError("Date cannot be in the future.")
    return parsed.isoformat()


def parse_month(text: Optional[str]) -> Optional[str]:
    """Validate a YYYY-MM month filter. Returns None when no month is given."""
    if text is None or not str(text).strip():
        return None
    value = str(text).strip()
    match = _MONTH_RE.match(value)
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise ValidationError(f"Invalid month '{text}'. Use YYYY-MM, e.g. 2026-09.")
    return value


def normalize_category(text: Optional[str]) -> str:
    """Lower-case, trim and collapse whitespace so 'Food ' and 'food' match."""
    value = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not value:
        raise ValidationError("Category is required.")
    if len(value) > MAX_CATEGORY_LEN:
        raise ValidationError(f"Category must be at most {MAX_CATEGORY_LEN} characters.")
    if not _CATEGORY_RE.match(value):
        raise ValidationError(
            "Category may contain only letters, numbers, spaces, '&', '.' and '-'."
        )
    return value


def normalize_description(text: Optional[str]) -> str:
    value = re.sub(r"\s+", " ", (text or "").strip())
    if len(value) > MAX_DESCRIPTION_LEN:
        raise ValidationError(f"Description must be at most {MAX_DESCRIPTION_LEN} characters.")
    return value


def parse_expense_id(text: object) -> int:
    try:
        value = int(str(text).strip())
    except ValueError:
        raise ValidationError(f"Invalid expense ID '{text}'. It must be a whole number.") from None
    if value <= 0:
        raise ValidationError("Expense ID must be a positive number.")
    return value
