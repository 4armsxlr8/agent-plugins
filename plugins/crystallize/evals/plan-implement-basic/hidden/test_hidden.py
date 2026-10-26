import unittest

from durations import parse_duration


class HiddenAcceptanceTest(unittest.TestCase):
    def test_valid(self):
        cases = {"1h30m": 5400, "45s": 45, "1h1m1s": 3661, "90m": 5400, "0s": 0, "2h": 7200, "1h5s": 3605}
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_duration(text), want)
                self.assertIsInstance(parse_duration(text), int)

    def test_invalid(self):
        for text in ["", "10", "5d", "30m1h", "1m2m", "h", "-5s"]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_duration(text)

    def test_version_kept(self):
        import durations
        self.assertEqual(durations.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
