import unittest
from datetime import date

from workdays import business_days_between


def d(text):
    return date.fromisoformat(text)


class HiddenAcceptanceTest(unittest.TestCase):
    def test_counts(self):  # AC-1〜AC-14
        cases = [
            ("2024-01-01", "2024-01-05", 4),
            ("2024-01-03", "2024-01-03", 0),
            ("2024-01-06", "2024-01-06", 0),
            ("2024-01-05", "2024-01-08", 1),
            ("2024-01-05", "2024-01-06", 0),
            ("2024-01-06", "2024-01-07", 0),
            ("2024-01-06", "2024-01-08", 1),
            ("2024-01-07", "2024-01-13", 5),
            ("2024-01-01", "2024-01-15", 10),
            ("2024-01-31", "2024-02-02", 2),
            ("2024-02-28", "2024-03-01", 2),
            ("2023-02-28", "2023-03-01", 1),
            ("2023-12-29", "2024-01-02", 2),
            ("2024-01-01", "2024-12-31", 261),
        ]
        for start, end, want in cases:
            with self.subTest(start=start, end=end):
                got = business_days_between(d(start), d(end))
                self.assertEqual(got, want)
                self.assertIsInstance(got, int)

    def test_start_after_end(self):  # AC-15
        with self.assertRaises(ValueError):
            business_days_between(d("2024-01-08"), d("2024-01-05"))

    def test_version_kept(self):  # 守るべき既存挙動
        import workdays
        self.assertEqual(workdays.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
