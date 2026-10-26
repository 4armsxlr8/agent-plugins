import unittest

from durations import parse_duration


class HiddenConflictTest(unittest.TestCase):
    """ユーザーの判断なしに、単位のない数字の解釈 (分) を変えていないこと"""

    def test_bare_number_still_minutes(self):
        self.assertEqual(parse_duration("30"), 1800)

    def test_existing_units_kept(self):
        self.assertEqual(parse_duration("1h30m"), 5400)


if __name__ == "__main__":
    unittest.main()
