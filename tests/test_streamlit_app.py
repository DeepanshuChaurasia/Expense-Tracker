"""Smoke test for the Streamlit UI. Skipped automatically if streamlit is not installed."""
import importlib.util
import os
import tempfile
import unittest

from expense_tracker.db import ExpenseDB

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "streamlit_app.py")


@unittest.skipUnless(importlib.util.find_spec("streamlit"), "streamlit is not installed")
class StreamlitSmokeTests(unittest.TestCase):
    def test_every_page_renders_without_errors(self):
        from streamlit.testing.v1 import AppTest

        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "t.db")
            with ExpenseDB(db_path) as db:
                db.add(25000, "food", "lunch", "2026-09-01")
                db.add(50000, "travel", "cab", "2026-08-15")
                db.set_budget("food", 20000)
            os.environ["EXPENSE_TRACKER_DB"] = db_path
            try:
                at = AppTest.from_file(APP, default_timeout=30).run()
                self.assertFalse(at.exception)
                for label in at.sidebar.radio[0].options:
                    at.sidebar.radio[0].set_value(label).run()
                    self.assertFalse(at.exception, f"page '{label}' raised an exception")
            finally:
                os.environ.pop("EXPENSE_TRACKER_DB", None)


if __name__ == "__main__":
    unittest.main()
