import unittest

from durations import parse_duration


class ParseDurationTest(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("45s"), 45)
        self.assertEqual(parse_duration("90m"), 5400)

    def test_invalid(self):
        for text in ["", "10", "5d", "30m1h"]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_duration(text)


if __name__ == "__main__":
    unittest.main()
