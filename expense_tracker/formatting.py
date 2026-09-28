"""Helpers for printing money, tables and simple bar charts."""
from __future__ import annotations

from typing import Iterable, Sequence


def format_inr(paise: int) -> str:
    """Format paise as rupees with Indian digit grouping, e.g. 123456789 -> ₹12,34,567.89."""
    sign = "-" if paise < 0 else ""
    rupees, ps = divmod(abs(paise), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{sign}₹{digits}.{ps:02d}"


def truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def render_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    right_align: Sequence[int] = (),
) -> str:
    rows = [[str(c) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: Sequence[str]) -> str:
        parts = [
            c.rjust(widths[i]) if i in right_align else c.ljust(widths[i])
            for i, c in enumerate(cells)
        ]
        return "  ".join(parts).rstrip()

    lines = [fmt(list(headers)), "  ".join("-" * w for w in widths)]
    lines.extend(fmt(r) for r in rows)
    return "\n".join(lines)


def bar(share_percent: float, width: int = 20) -> str:
    filled = round(share_percent / 100 * width)
    return "█" * filled
