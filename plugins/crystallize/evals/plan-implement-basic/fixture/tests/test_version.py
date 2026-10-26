import unittest

import durations


class VersionTest(unittest.TestCase):
    def test_version_is_string(self):
        self.assertIsInstance(durations.__version__, str)


if __name__ == "__main__":
    unittest.main()
