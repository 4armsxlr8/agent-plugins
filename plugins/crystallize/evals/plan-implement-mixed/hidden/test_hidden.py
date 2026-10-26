import re
import unittest
from pathlib import Path


def usage_section():
    """README.md の「## 使い方」見出しから次の「## 」見出しまでを返す"""
    text = Path("README.md").read_text(encoding="utf-8")
    match = re.search(r"^## 使い方[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


class HiddenFormatTest(unittest.TestCase):
    def test_valid(self):  # AC-1〜AC-8, AC-10
        from durations import format_duration
        cases = {5400: "1h30m", 45: "45s", 3661: "1h1m1s", 90: "1m30s", 0: "0s",
                 7200: "2h", 3605: "1h5s", 60: "1m", 90000: "25h"}
        for seconds, want in cases.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(format_duration(seconds), want)
                self.assertIsInstance(format_duration(seconds), str)

    def test_negative(self):  # AC-9
        from durations import format_duration
        with self.assertRaises(ValueError):
            format_duration(-1)


class HiddenReadmeTest(unittest.TestCase):
    def test_usage_has_format_example(self):  # AC-11
        section = usage_section()
        self.assertIn("format_duration(3661)", section)
        self.assertIn("1h1m1s", section)

    def test_usage_keeps_parse_example(self):  # 守るべき既存挙動: README の parse_duration の例
        self.assertIn("parse_duration(", usage_section())


class HiddenKeptTest(unittest.TestCase):
    def test_parse_kept(self):  # 守るべき既存挙動: parse_duration
        from durations import parse_duration
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("45s"), 45)
        with self.assertRaises(ValueError):
            parse_duration("30m1h")

    def test_version_kept(self):  # 守るべき既存挙動: __version__
        import durations
        self.assertEqual(durations.__version__, "0.2.0")


if __name__ == "__main__":
    unittest.main()
