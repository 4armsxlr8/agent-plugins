import unittest

from durations import parse_duration


class ParseDurationTest(unittest.TestCase):
    def test_hours_and_minutes(self):
        self.assertEqual(parse_duration("1h30m"), 5400)

    def test_bare_number_is_minutes(self):
        self.assertEqual(parse_duration("30"), 1800)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            parse_duration("5d")


if __name__ == "__main__":
    unittest.main()
