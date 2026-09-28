import unittest
from datetime import date

from expense_tracker.csv_io import expenses_to_csv_text
from expense_tracker.db import ExpenseDB
from expense_tracker.reports import (
    available_months, budget_alerts, current_month, expense_rows, month_overview, previous_month,
)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.db = ExpenseDB(":memory:")
        self.db.add(25000, "food", "lunch", "2026-09-01")
        self.db.add(50000, "travel", "cab", "2026-09-15")
        self.db.add(10000, "food", "tea", "2026-08-20")

    def tearDown(self):
        self.db.close()

    def test_month_helpers(self):
        self.assertEqual(previous_month("2026-09"), "2026-08")
        self.assertEqual(previous_month("2026-01"), "2025-12")
        self.assertEqual(current_month(date(2026, 3, 9)), "2026-03")

    def test_available_months_includes_current_and_is_newest_first(self):
        months = available_months(self.db, today=date(2026, 10, 2))
        self.assertEqual(months, ["2026-10", "2026-09", "2026-08"])

    def test_month_overview(self):
        ov = month_overview(self.db, "2026-09")
        self.assertEqual((ov.total_paise, ov.count), (75000, 2))
        self.assertEqual(ov.previous_total_paise, 10000)
        self.assertEqual(ov.delta_paise, 65000)
        self.assertEqual(ov.top_category, ("travel", 50000))

    def test_month_overview_empty_month(self):
        ov = month_overview(self.db, "2026-01")
        self.assertEqual((ov.total_paise, ov.count, ov.top_category), (0, 0, None))

    def test_budget_alerts(self):
        self.assertEqual(budget_alerts(self.db, "food", "2026-09"), [])
        self.db.set_budget("food", 30000)  # 250 of 300 = 83%
        self.assertIn("Heads up", budget_alerts(self.db, "food", "2026-09")[0])
        self.db.set_budget("food", 20000)
        self.assertIn("over its", budget_alerts(self.db, "food", "2026-09")[0])

    def test_expense_rows_and_csv_text(self):
        rows = expense_rows(self.db.list_expenses(limit=1))
        self.assertEqual(rows[0]["Amount (₹)"], 500.0)
        text = expenses_to_csv_text(self.db.list_expenses(month="2026-08"))
        self.assertEqual(text.splitlines(), ["date,category,amount,description", "2026-08-20,food,100.00,tea"])


if __name__ == "__main__":
    unittest.main()
