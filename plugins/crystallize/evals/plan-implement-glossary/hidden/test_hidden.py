import unittest
from datetime import date

from tasks.due import days_until_due, is_overdue, parse_due


class HiddenAcceptanceTest(unittest.TestCase):
    def test_parse_due(self):
        self.assertEqual(parse_due("2026-11-01"), date(2026, 11, 1))  # AC-1
        for text in ["2026/11/01", "2026-02-30"]:  # AC-2, AC-3
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_due(text)

    def test_is_overdue(self):
        today = date(2026, 11, 1)
        self.assertIs(is_overdue(date(2026, 10, 31), today), True)  # AC-4
        self.assertIs(is_overdue(date(2026, 11, 1), today), False)  # AC-5
        self.assertIs(is_overdue(None, today), False)  # AC-6

    def test_days_until_due(self):
        today = date(2026, 11, 1)
        self.assertEqual(days_until_due(date(2026, 11, 5), today), 4)  # AC-7
        self.assertEqual(days_until_due(date(2026, 10, 30), today), -2)  # AC-8
        self.assertIsInstance(days_until_due(date(2026, 11, 5), today), int)

    def test_version_kept(self):
        import tasks
        self.assertEqual(tasks.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
