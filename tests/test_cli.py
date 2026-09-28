import contextlib
import io
import os
import tempfile
import unittest

from expense_tracker.cli import main


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "t.db")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--db", self.db, *argv])
        return code, out.getvalue(), err.getvalue()

    def test_full_workflow(self):
        code, out, _ = self.run_cli("add", "250", "Food", "-d", "lunch", "--date", "2026-09-01")
        self.assertEqual(code, 0)
        self.assertIn("Added #1", out)
        self.run_cli("add", "1,000", "travel", "--date", "2026-09-02")

        code, out, _ = self.run_cli("list")
        self.assertIn("lunch", out)
        self.assertIn("₹1,250.00", out)

        code, out, _ = self.run_cli("edit", "1", "--amount", "300")
        self.assertEqual(code, 0)
        self.assertIn("₹300.00", out)

        code, out, _ = self.run_cli("summary")
        self.assertIn("travel", out)
        self.assertIn("76.9%", out)

        code, out, _ = self.run_cli("summary", "--by", "month")
        self.assertIn("2026-09", out)

        code, out, _ = self.run_cli("delete", "1", "-y")
        self.assertIn("Deleted #1", out)
        self.assertIn("Error", self.run_cli("delete", "1", "-y")[2])

    def test_validation_errors_exit_nonzero(self):
        for argv in (["add", "abc", "food"], ["add", "10", "food", "--date", "2999-01-01"],
                     ["edit", "1"], ["list", "--month", "2026-99"], ["edit", "x", "--amount", "5"]):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertIn("Error", err)

    def test_budget_warning(self):
        self.run_cli("budget", "set", "food", "500")
        code, out, _ = self.run_cli("add", "600", "food", "--date", "2026-09-01")
        self.assertIn("over", out)
        _, out, _ = self.run_cli("budget", "list", "--month", "2026-09")
        self.assertIn("OVER", out)

    def test_csv_round_trip(self):
        self.run_cli("add", "250", "food", "-d", "lunch, with comma", "--date", "2026-09-01")
        path = os.path.join(self.tmp.name, "out.csv")
        self.assertEqual(self.run_cli("export", path)[0], 0)
        self.db = os.path.join(self.tmp.name, "other.db")
        code, out, _ = self.run_cli("import", path)
        self.assertIn("Imported 1", out)
        self.assertIn("lunch, with comma", self.run_cli("list")[1])

    def test_import_reports_bad_rows(self):
        path = os.path.join(self.tmp.name, "bad.csv")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("date,category,amount,description\n2026-09-01,food,100,ok\nnot-a-date,food,50,x\n2026-09-02,food,-5,y\n")
        code, out, _ = self.run_cli("import", path)
        self.assertIn("Imported 1", out)
        self.assertIn("Skipped 2", out)

    def test_import_missing_file(self):
        code, _, err = self.run_cli("import", os.path.join(self.tmp.name, "nope.csv"))
        self.assertEqual(code, 1)
        self.assertIn("file not found", err)


if __name__ == "__main__":
    unittest.main()
