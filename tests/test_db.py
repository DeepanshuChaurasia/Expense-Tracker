import unittest

from expense_tracker.db import ExpenseDB, NotFoundError
from expense_tracker.formatting import format_inr


class DBTests(unittest.TestCase):
    def setUp(self):
        self.db = ExpenseDB(":memory:")
        self.db.add(25000, "food", "lunch", "2026-09-01")
        self.db.add(50000, "travel", "cab", "2026-09-15")
        self.db.add(10000, "food", "tea 100%_off", "2026-08-20")

    def tearDown(self):
        self.db.close()

    def test_add_and_get(self):
        e = self.db.add(999, "misc", "", "2026-09-02")
        self.assertEqual(self.db.get(e.id).amount_paise, 999)

    def test_get_missing_raises(self):
        with self.assertRaises(NotFoundError):
            self.db.get(999)

    def test_list_newest_first_and_filters(self):
        rows = self.db.list_expenses()
        self.assertEqual([r.spent_on for r in rows], ["2026-09-15", "2026-09-01", "2026-08-20"])
        self.assertEqual(len(self.db.list_expenses(category="food")), 2)
        self.assertEqual(len(self.db.list_expenses(month="2026-09")), 2)
        self.assertEqual(len(self.db.list_expenses(start="2026-09-01", end="2026-09-10")), 1)
        self.assertEqual(len(self.db.list_expenses(limit=1)), 1)

    def test_search_escapes_wildcards(self):
        self.assertEqual(len(self.db.list_expenses(search="100%_off")), 1)
        self.assertEqual(len(self.db.list_expenses(search="%")), 1)

    def test_sql_injection_is_inert(self):
        self.db.add(100, "x", "'; DROP TABLE expenses; --", "2026-09-03")
        self.assertEqual(len(self.db.list_expenses(search="'; DROP TABLE expenses; --")), 1)
        self.assertEqual(self.db.total()[1], 4)

    def test_update(self):
        e = self.db.update(1, amount_paise=30000, description="")
        self.assertEqual((e.amount_paise, e.description, e.category), (30000, "", "food"))
        with self.assertRaises(ValueError):
            self.db.update(1)
        with self.assertRaises(NotFoundError):
            self.db.update(999, category="x")

    def test_delete(self):
        self.db.delete(1)
        with self.assertRaises(NotFoundError):
            self.db.get(1)
        with self.assertRaises(NotFoundError):
            self.db.delete(1)

    def test_summaries(self):
        self.assertEqual(self.db.category_summary(), [("travel", 1, 50000), ("food", 2, 35000)])
        self.assertEqual(self.db.category_summary("2026-09"), [("travel", 1, 50000), ("food", 1, 25000)])
        self.assertEqual(self.db.monthly_summary(), [("2026-08", 1, 10000), ("2026-09", 2, 75000)])
        self.assertEqual(self.db.total(), (85000, 3))

    def test_budgets(self):
        self.db.set_budget("food", 20000)
        (status,) = self.db.budget_status("2026-09")
        self.assertEqual((status.spent_paise, status.remaining_paise, status.exceeded), (25000, -5000, True))
        self.db.set_budget("food", 100000)  # replace
        self.assertFalse(self.db.budget_status("2026-09", "food")[0].exceeded)
        self.db.remove_budget("food")
        with self.assertRaises(NotFoundError):
            self.db.remove_budget("food")

    def test_check_constraint_blocks_zero(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add(0, "x", "", "2026-09-01")


class FormatTests(unittest.TestCase):
    def test_inr_grouping(self):
        self.assertEqual(format_inr(0), "₹0.00")
        self.assertEqual(format_inr(99900), "₹999.00")
        self.assertEqual(format_inr(123456), "₹1,234.56")
        self.assertEqual(format_inr(123456789), "₹12,34,567.89")
        self.assertEqual(format_inr(-5000), "-₹50.00")


if __name__ == "__main__":
    unittest.main()
