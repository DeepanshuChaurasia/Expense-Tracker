import unittest
from datetime import date

from expense_tracker.validators import (
    ValidationError, normalize_category, parse_amount, parse_date, parse_expense_id, parse_month,
)


class AmountTests(unittest.TestCase):
    def test_valid_amounts(self):
        self.assertEqual(parse_amount("250"), 25000)
        self.assertEqual(parse_amount("99.5"), 9950)
        self.assertEqual(parse_amount("1,250.75"), 125075)
        self.assertEqual(parse_amount("₹10"), 1000)
        self.assertEqual(parse_amount("Rs. 10.05"), 1005)

    def test_no_float_rounding_errors(self):
        self.assertEqual(parse_amount("0.29"), 29)
        self.assertEqual(parse_amount("1.15"), 115)

    def test_invalid_amounts(self):
        for bad in ["", "abc", "-5", "0", "0.00", "1.234", "nan", "inf", "1e5", "10,,", None, "999999999"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    parse_amount(bad)


class DateTests(unittest.TestCase):
    TODAY = date(2026, 9, 28)

    def test_keywords_and_blank(self):
        self.assertEqual(parse_date("", self.TODAY), "2026-09-28")
        self.assertEqual(parse_date(None, self.TODAY), "2026-09-28")
        self.assertEqual(parse_date("Yesterday", self.TODAY), "2026-09-27")

    def test_explicit_dates(self):
        self.assertEqual(parse_date("2026-01-05", self.TODAY), "2026-01-05")

    def test_rejects_bad_and_future_dates(self):
        for bad in ["2026-13-01", "28/09/2026", "2026-02-30", "2026-09-29", "tomorrow"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    parse_date(bad, self.TODAY)


class MiscTests(unittest.TestCase):
    def test_category_normalisation(self):
        self.assertEqual(normalize_category("  Food   Court "), "food court")

    def test_bad_categories(self):
        for bad in ["", "   ", "x" * 31, "food;drop", "_x"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    normalize_category(bad)

    def test_month(self):
        self.assertEqual(parse_month("2026-09"), "2026-09")
        self.assertIsNone(parse_month(None))
        with self.assertRaises(ValidationError):
            parse_month("2026-13")

    def test_expense_id(self):
        self.assertEqual(parse_expense_id("7"), 7)
        for bad in ["x", "0", "-1", "1.5"]:
            with self.assertRaises(ValidationError):
                parse_expense_id(bad)


if __name__ == "__main__":
    unittest.main()
