import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "durations.cli", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )


class HiddenCliTest(unittest.TestCase):
    def test_valid(self):
        # AC-1〜AC-3
        for arg, want in [("1h30m", "5400"), ("45s", "45"), ("0s", "0")]:
            with self.subTest(arg=arg):
                proc = run_cli(arg)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.splitlines(), [want])

    def test_invalid_duration(self):
        # AC-4, AC-5
        for arg in ["5d", ""]:
            with self.subTest(arg=arg):
                proc = run_cli(arg)
                self.assertEqual(proc.returncode, 1, proc.stderr)
                self.assertEqual(proc.stdout, "")

    def test_wrong_arg_count(self):
        # AC-6, AC-7
        for args in [(), ("1h", "30m")]:
            with self.subTest(args=args):
                proc = run_cli(*args)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertEqual(proc.stdout, "")

    def test_parse_kept(self):
        # 守るべき既存挙動: parse_duration の解釈は変えない
        from durations import parse_duration
        self.assertEqual(parse_duration("1h30m"), 5400)
        with self.assertRaises(ValueError):
            parse_duration("30m1h")


if __name__ == "__main__":
    unittest.main()
